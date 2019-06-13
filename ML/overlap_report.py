import time
import datetime
import logging
import argparse
import numpy as np
import pandas as pd
from sql.core import execute_db_query
from utils import logging_utils
from utils import s3_utils
from collections import defaultdict
import boto3
import json
import csv
import itertools

from google.oauth2 import service_account
from apiclient import discovery

# parse args
parser = argparse.ArgumentParser(description="Generate CT Overlap Matrix Report",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--test', action='store_true', help="Output to test Google Doc")
parser.add_argument('--lookback', type=int, default=7, help="Number of days for lookback")
args = parser.parse_args()

#initialize the logging and output file names for S3
logging_utils.setup("ct_overlap_report")
output_prefix = datetime.datetime.today().strftime('%Y%m%d%H')
output_files = []

#create dictionary to hold users for each entity
user_ids_by_entity = defaultdict(set)

# start the script timer
total_starts = time.time()

# give lookback param for report
lookback = args.lookback

# define the sheet name for google sheet to be generated
sheet_title = datetime.datetime.today().strftime('%m-%d') + ' % Overlap - ' + str(lookback) + ' day lookback'

# handy function for lists in a query
def stringify_lists(arr):
    string = ''
    arr_len = len(arr)

    for x in range(arr_len):
        if x != 0 and x != (arr_len - 1):
            string = string + "\t,'" + str(arr[x]) + "'\n"
        elif x == (arr_len - 1):
            string = string + "\t,'" + str(arr[x]) + "'"
        else:
            string = string + "'" + str(arr[x]) + "'\n"
    return string

####pull users first from hotel city sessions by pub_group

sessions_query = f"""

    SELECT ctz_user_id
        , publisher_group_name||'_s' as entity
        , count(1)
    FROM hotel_city_sessions hcs
    LEFT JOIN (

        SELECT publisher_id, publisher_group_name
        FROM metadata_publisher_groups
        WHERE publisher_group_type = 'Integrations Group'

    ) g ON g.publisher_id = hcs.publisher_id
    WHERE date > trunc(convert_timezone('GMT','America/Los_Angeles', getdate() - interval '{lookback} day'))
    AND date < trunc(convert_timezone( 'GMT','America/Los_Angeles', getdate()))
    AND user_browser_id IN (1, 4, 5)
    AND user_device_id_name = 'Desktop'
    GROUP BY 1,2
"""

r1 = execute_db_query(sessions_query, chunksize=10000)

for df in r1:

    agg = df.groupby('entity')['ctz_user_id'].apply(set)
    for entity, idset in agg.iteritems():
        user_ids_by_entity[entity].update(idset)
    del df
    del agg

del r1

####pull users next from pageviews (per alias) if they are not in the blacklist

pv_entity_list = []

# only pull entities with over 100 users per day
pv_min_query = f"""

    SELECT *
    FROM (
    SELECT hotel_city_raw_pageviews.alias
        , count(distinct ctz_user_id) as user_cnt
    FROM
        hotel_city_raw_pageviews
    WHERE
        date > trunc(convert_timezone('GMT','America/Los_Angeles', getdate() - interval '{lookback} day'))
        AND date < trunc(convert_timezone( 'GMT','America/Los_Angeles', getdate()))
        AND user_browser_id IN (1, 4, 5)
        AND user_device_id_name = 'Desktop'
        AND hotel_city_raw_pageviews.alias IS NOT NULL
    GROUP BY 1
    )
    WHERE user_cnt > 100

"""

alias_res = execute_db_query(pv_min_query)
alias_list = alias_res['alias'].unique()
alias_list = alias_list.tolist()

for x in range(lookback):

    # pv query
    pv_query = f"""

        SELECT distinct hotel_city_raw_pageviews.alias||'_pv' as entity
        FROM
            hotel_city_raw_pageviews
        WHERE
            date > trunc(convert_timezone('GMT','America/Los_Angeles', getdate() - interval '{x+1} day'))
            AND date < trunc(convert_timezone( 'GMT','America/Los_Angeles', getdate() - interval '{x} day'))
            AND user_browser_id IN (1, 4, 5)
            AND user_device_id_name = 'Desktop'
            AND hotel_city_raw_pageviews.alias IS NOT NULL
            AND hotel_city_raw_pageviews.alias IN ({stringify_lists(alias_list)})
    """

    # get entity list
    r2 = execute_db_query(pv_query)
    entity_list = r2['entity'].unique()
    entity_list = entity_list.tolist()

    # if x == 0:
    #     pv_entity_list = entity_list
    for entity_ in entity_list:
        pv_entity_list.append(entity_)

    del r2

    # pv query
    pv_query = f"""

        SELECT
            ctz_user_id
            , hotel_city_raw_pageviews.alias||'_pv' as entity
            , count(1)
        FROM
            hotel_city_raw_pageviews
        WHERE
            date > trunc(convert_timezone('GMT','America/Los_Angeles', getdate() - interval '{x+1} day'))
            AND date < trunc(convert_timezone( 'GMT','America/Los_Angeles', getdate() - interval '{x} day'))
            AND user_browser_id IN (1, 4, 5)
            AND user_device_id_name = 'Desktop'
            AND hotel_city_raw_pageviews.alias IS NOT NULL
            AND hotel_city_raw_pageviews.alias IN ({stringify_lists(alias_list)})
        GROUP BY
            1,
            2
    """

    r2 = execute_db_query(pv_query, chunksize=10000)

    for df in r2:

        agg = df.groupby('entity')['ctz_user_id'].apply(set)
        for entity, idset in agg.iteritems():
            user_ids_by_entity[entity].update(idset)
        del df
        del agg

    del r2

# get all unique values for pv_entity_list
pv_entity_list = set(pv_entity_list)
pv_entity_list = sorted(pv_entity_list)

# set of advertisers to pull
# get list of remarketing advertisers for last week
advertiser_query = """
    SELECT distinct advertiser_id
    FROM agg_daily_user_events
    WHERE date > current_date - 7
"""
arr = execute_db_query(advertiser_query)
advertiser_list = np.array(arr['advertiser_id']).tolist()
advertiser_list = sorted(advertiser_list, key=int)
logging.debug(advertiser_list)

# get names of each remarketing advertiser, in order
advertiser_name_query = """
    SELECT id as advertiser_id, name as advertiser_name
    FROM metadata_advertisers
    WHERE id IN (""" + stringify_lists(advertiser_list) + """)
    ORDER BY 1
"""
advertiser_name_df = execute_db_query(advertiser_name_query)

# create an advertiser id-name dictionary
advertisers = {}
for x in range(len(advertiser_name_df)):
    row = advertiser_name_df.loc[x].copy()
    advertiser_id = row['advertiser_id']
    advertiser_name = row['advertiser_name']
    advertisers[advertiser_id] = advertiser_name.replace(" ", "_")

# pull each advertiser, one day at a time
for advertiser_id, advertiser_name in advertisers.items():

    dfr = pd.DataFrame()

    for x in range(lookback):

        query3 = f"""

            with clickers as (
                SELECT distinct ctz_user_id
                FROM v_all_clicks
                WHERE advertiser_id = {advertiser_id}
                AND date > trunc(convert_timezone('GMT', 'America/Los_Angeles', getdate() - interval '{lookback} day'))
                AND date < trunc(convert_timezone('GMT', 'America/Los_Angeles', getdate()))
            )

            SELECT
                ue.ctz_user_id
                , '001_remarketing_'||'{advertiser_name}'||'_rt' as entity
                , count(1)
            FROM user_events ue
            LEFT JOIN clickers c ON c.ctz_user_id = ue.ctz_user_id
            WHERE
              date > trunc(convert_timezone('GMT', 'America/Los_Angeles', getdate() - interval '{x+1} day'))
              AND date < trunc(convert_timezone('GMT', 'America/Los_Angeles', getdate() - interval '{x} day'))
              AND user_browser_id IN (1,4,5)
              AND user_device_id_name ='Desktop'
              AND ue.advertiser_id = {advertiser_id}
              AND c.ctz_user_id IS NULL
            GROUP BY
                1,
                2
        """

        # get df generator
        r3 = execute_db_query(query3, chunksize=10000)

        for df in r3:

            agg = df.groupby('entity')['ctz_user_id'].apply(set)
            for entity, idset in agg.iteritems():
                user_ids_by_entity[entity].update(idset)
            del df
            del agg

        del r3

logging.debug('remarketing queries finished')

now = time.time()
logging.debug("It has taken {0} seconds to run all queries".format(round(now - total_starts)))
entities = list(user_ids_by_entity.keys())

####create CTN row, give it a different name, put it last as an entity zz_ name
keys = user_ids_by_entity.keys()
for i, alias_j in enumerate(entities):

    if alias_j.endswith('_s') and alias_j != 'wetter_s' and alias_j != 'mapquest_s':
        entity_users = user_ids_by_entity[alias_j]
        user_ids_by_entity['zz_ctn_group_s'].update(entity_users)

keys = user_ids_by_entity.keys()

#run overlap calculations
entities = list(user_ids_by_entity.keys())
overlap = np.zeros((len(entities), len(entities)))

for i, alias_i in enumerate(entities):
    for j, alias_j in enumerate(entities):
        u1 = user_ids_by_entity[alias_i]
        u2 = user_ids_by_entity[alias_j]
        overlap[i, j] = len(u1.intersection(u2))
overlap = overlap.astype(int)

# create matrix dataframe
matrix_df = pd.DataFrame(overlap, index=entities, columns=entities)
logging.debug('done creating initial matrix')

del overlap

####CT ALL, CTN and CTR overlap calcs here
# get all users for all entities
ct_all_list = {}
ctr_list = {}
ctn_list = {}
keys = user_ids_by_entity.keys()
keys_ = list(user_ids_by_entity.keys())
for i, alias_j in enumerate(entities):

    # get the stem of each entity name, for filtering purposes
    stem = ''
    if alias_j[-1:] == 's':
        stem = alias_j[:-2]
    elif alias_j[-1:] == 'v':
        stem = alias_j[:-3]

    #CT ALL calcs
    if 'remarketing' not in alias_j and alias_j != 'zz_ctn_group_s':

        #get rid of all pv data sources from overlap
        target_keys = [key for key in keys if key.endswith('_pv')]

        #get rid of mapquest and wetter
        target_keys.extend(['wetter_s','wetter_pv','mapquest_s','mapquest_pv','zz_ctn_group_s'])

        #overcome some exceptions
        if stem == 'bedandbreakfast' or stem == 'bnb':
            target_keys.extend(['bnb_pv', 'bedandbreakfast_s'])
        elif stem == 'amoma':
            target_keys.extend(['amoma_pv','amoma_s','001_remarketing_Amoma_rt'])
        elif stem == 'homeaway' or stem == 'homeaway_intl':
            target_keys.extend(['homeaway_s','homeaway_intl_pv'])
        elif stem == 'sta_travel' or stem == 'statravel':
            target_keys.extend(['sta_travel_s','statravel_pv'])
        elif stem == 'hostels' or stem == 'hostels_com':
            target_keys.extend(['hostels_pv','hostels_com_s'])
        elif stem == 'telegraph' or stem == 'telegraph_rm':
            target_keys.extend(['telegraph_pv','telegraph_rm_pv','telegraph_s'])
        elif stem == 'homelidays' or stem == 'homeaway':
            target_keys.extend(['homelidays_pv','homeaway_s'])
        else:
            more_keys = [key for key in keys if key.startswith(stem)]
            target_keys.extend(more_keys)

        keys_ = list(user_ids_by_entity.keys())
        keys_ = [e for e in keys_ if e not in target_keys]
        overlap = set()
        entity_users = user_ids_by_entity[alias_j]

        #get the overlapping users
        for k in keys_:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

    elif 'remarketing' in alias_j and alias_j != 'zz_ctn_group_s':

        # get all sets except for the target alias
        if 'amoma' in alias_j.lower():

            target_keys = [key for key in keys if key.endswith('_pv')]
            # get rid of mapquest and wetter
            target_keys.extend(['wetter_s', 'wetter_pv', 'mapquest_s', 'mapquest_pv','zz_ctn_group_s'])
            target_keys.extend([alias_j, 'amoma_pv', 'amoma_s'])

            keys_ = [e for e in keys_ if e not in target_keys]

        else:

            # get rid of mapquest and wetter
            target_keys = [key for key in keys if key.endswith('_pv')]
            target_keys.extend(['wetter_s', 'wetter_pv', 'mapquest_s', 'mapquest_pv','zz_ctn_group_s'])
            target_keys.append(alias_j)

            keys_ = list(user_ids_by_entity.keys())
            keys_ = [e for e in keys_ if e not in target_keys]

        overlap = set()
        entity_users = user_ids_by_entity[alias_j]

        for k in keys_:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

    else:

        print(alias_j)

        # get rid of all pv data sources from overlap
        target_keys = [key for key in keys if key.endswith('_pv')]

        # get rid of mapquest and wetter
        target_keys.extend(['wetter_s', 'wetter_pv', 'mapquest_s', 'mapquest_pv'])

        keys_ = list(user_ids_by_entity.keys())
        keys_ = [e for e in keys_ if e not in target_keys]
        overlap = set()

        entity_users = user_ids_by_entity[alias_j]

        # get the overlapping users
        for k in keys_:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

    ct_all_list[alias_j] = len(overlap)

    #CTR calcs
    if 'remarketing' not in alias_j:

        remarketing_keys = [key for key in keys if key.startswith('001_remarketing')]
        if 'amoma' in alias_j:
            remarketing_keys.remove('001_remarketing_Amoma_rt')
        overlap = set()
        entity_users = user_ids_by_entity[alias_j]

        for k in remarketing_keys:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

        ctr_list[alias_j] = len(overlap)

    else:

        remarketing_keys = [key for key in keys if key.startswith('001_remarketing')]
        remarketing_keys.remove(alias_j)

        overlap = set()
        entity_users = user_ids_by_entity[alias_j]

        for k in remarketing_keys:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

        ctr_list[alias_j] = len(overlap)

    #CTN calcs
    if 'remarketing' not in alias_j:

        filter_keys = [key for key in keys if key.startswith(stem)]

        # overcome some exceptions
        if stem == 'bedandbreakfast' or stem == 'bnb':
            filter_keys.extend(['bedandbreakfast_s'])
        elif stem == 'amoma':
            filter_keys.extend(['amoma_s', '001_remarketing_Amoma_rt'])
        elif stem == 'homeaway' or stem == 'homeaway_intl':
            filter_keys.extend(['homeaway_s', ])
        elif stem == 'sta_travel' or stem == 'statravel':
            filter_keys.extend(['sta_travel_s'])
        elif stem == 'hostels' or stem == 'hostels_com':
            filter_keys.extend(['hostels_com_s'])
        elif stem == 'telegraph' or stem == 'telegraph_rm':
            filter_keys.extend(['telegraph_s'])
        elif stem == 'homelidays' or stem == 'homeaway':
            filter_keys.extend(['homeaway_s'])

        filter_keys.extend(['wetter_s', 'mapquest_s','zz_ctn_group_s'])

        #get the remarketing keys
        remarketing_keys = [key for key in keys if key.startswith('001_remarketing')]

        #get the CTN users
        ctn_keys = [key for key in keys if key.endswith('_s')] #get all sessions keys
        ctn_keys = [e for e in ctn_keys if e not in alias_j]
        ctn_keys = [e for e in ctn_keys if e not in filter_keys] #remove the right keys

        overlap = set()
        #get users for the entity
        entity_users = user_ids_by_entity[alias_j]

        #calculate CTN overlap
        for k in ctn_keys:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

        ctn_list[alias_j] = len(overlap)

    else:

        filter_keys = ['wetter_s', 'mapquest_s', 'zz_ctn_group_s']
        if 'Amoma' in alias_j:
            filter_keys.append('amoma_s')

        #get the CTN users
        ctn_keys = [key for key in keys if key.endswith('_s')] #get all sessions keys
        ctn_keys = [e for e in ctn_keys if e not in filter_keys] #remove the right keys

        overlap = set()
        #get users for the entity
        entity_users = user_ids_by_entity[alias_j]

        #calculate CTN overlap
        for k in ctn_keys:
            overlap = overlap.union(entity_users.intersection(user_ids_by_entity[k]))

        ctn_list[alias_j] = len(overlap)

    del overlap

del entities
del user_ids_by_entity

logging.debug('done with matrix CT ALL calcs')

# get all columns
columns = matrix_df.columns

# get columns that are remarketing
remarketing_columns = [col for col in columns if 'remarketing' in col]
len_a = len(remarketing_columns)

# get columns not in remarketing
column_list = columns[:len(columns) - len_a]

# add overall max and entity columns
matrix_df['max'] = matrix_df[columns].max(axis=1)
matrix_df['entity'] = columns

logging.debug('done with matrix CTN calcs')

# do CT ALL calcs
matrix_df['CT_ALL_CNT'] = 0
matrix_df['CTR_CNT'] = 0
matrix_df['CTN_CNT'] = 0

for col in columns:
    matrix_df.loc[matrix_df.entity == col, 'CT_ALL_CNT'] = ct_all_list[col]
    matrix_df.loc[matrix_df.entity == col, 'CTR_CNT'] = ctr_list[col]
    matrix_df.loc[matrix_df.entity == col, 'CTN_CNT'] = ctn_list[col]

###########split the matrix in two, to correct CTN calcs

# save the matrix with counts
csv_filename = '{}_matrix_counts.csv'.format(output_prefix)
matrix_df.to_csv(csv_filename, index=False)
output_files.append(csv_filename)
logging.debug('matrix counts saved to file')

###################### create the final matrix

# get the % overlap
matrix2 = matrix_df[columns].div(matrix_df['max'], axis=0)

# append the new aggregate columns
matrix2['CT_ALL'] = matrix_df['CT_ALL_CNT'] / matrix_df['max']
matrix2['CTR'] = matrix_df['CTR_CNT'] / matrix_df['max']
matrix2['CTN'] = matrix_df['CTN_CNT'] / matrix_df['max']

# add the entity column at the beginning of the dataframe
matrix2.insert(loc=0, column='entity', value=matrix_df['entity'])

# resort the column names
cols = matrix2.columns.tolist()

cols.remove('entity')
cols.remove('CTN')
cols.remove('CTR')
cols.remove('CT_ALL')
cols.remove('zz_ctn_group_s')

# sort the entity columns
cols.sort()

# add columns back in right order
cols.insert(0, 'entity')
cols.insert(1,'CTN')
cols.insert(2,'CTR')
cols.insert(3,'CT_ALL')

# save csv
csv_filename = '{}_matrix.csv'.format(output_prefix)
matrix2[cols].sort_values(by=['entity']).to_csv(csv_filename, index=False)
output_files.append(csv_filename)

logging.debug('matrix saved to file')

#log the time it took to run the script
now = time.time()
logging.debug("It has taken {0} seconds to run script".format(round(now - total_starts)))

#send output files to s3
s3_utils.upload_file_list_to_s3(output_files, 'matrix', 'ct-analytics-scratch')

###################### generate the google sheet

# get Oauth2 authorization
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

s3 = boto3.resource('s3')
content_object = s3.Object('ct-credentials', 'prod_google/overlap-script-google-sheets-service-account-credentials.json')
file_content = content_object.get()['Body'].read().decode('utf-8')
json_content = json.loads(file_content)
creds = service_account.Credentials.from_service_account_info(json_content)

service = discovery.build('sheets', 'v4', credentials=creds)

# spreadsheet we will be editing
spreadsheet_id = '1KR22tRBDhkndGajUgrgGoRGOch9ZknaLc5KtsIZjDd0' if args.test \
    else '1pf4GJpcvr1mHes3jPKClCwxpV3nlJaJkGi_Z-2JOx18'

####import matrix data

# matrix data source specified here
csv_path = csv_filename

# get CSV values and row counts
row_count = 0
values_list = []
with open(csv_path) as f:
    # get the rows of data
    lis = [line.split() for line in f]  # create a list of lists
    for i, x in enumerate(lis):  # print the list items
        if (i == 0):
            values_list.append(str(x).replace("[", "").replace("]", "").replace("\"", "'").replace("'", "").split(','))
        else:
            row = str(x).replace("[", "").replace("]", "").replace("\"", "'").replace("'", "").split(',')
            first_val = row[0]
            next_vals = [float(i) for i in row[1:]]
            next_vals.insert(0, first_val)
            values_list.append(next_vals)
        row_count += 1

# get CSV column count
with open(csv_path) as f:
    reader1, reader2 = itertools.tee(csv.reader(f, delimiter=','))
    column_count = len(next(reader1))

####create a new sheet
requests = []

# request new sheet and give it a new name
requests.append({
    "addSheet": {
        "properties": {
            "title": sheet_title,
            "gridProperties": {
                "rowCount": row_count,
                "columnCount": column_count
            }
        }
    }
})

body = {'requests': requests}
result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

# get ID and name of the sheet just created
sheetId = result['replies'][0]['addSheet']['properties']['sheetId']
sheetName = result['replies'][0]['addSheet']['properties']['title']

# How the input data should be interpreted.
value_input_option = 'RAW'  # TODO: Update placeholder value.

# get the proper range for the update
alphabet = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U',
            'V', 'W', 'X', 'Y', 'Z']
left_letter = alphabet[(round(column_count / 26)) - 1]
right_letter = alphabet[(column_count % 26)]
end_range_str = left_letter + right_letter

# create range and data variables
range_ = sheet_title + '!A1:' + str(end_range_str) + str(row_count)  # TODO: Update placeholder value.
data = {'values': values_list}

# make the request to load the CSV
result = service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=range_,
                                                valueInputOption=value_input_option, body=data).execute()

####below is batchupdate to format the sheet

#find and replace remarketing text and others
requests = []
finds = ['001_remarketing_','zz_','group_s']
replacements = ['','','group']
for num in range(len(finds)):
    requests.append({
        'findReplace': {
            'find': finds[num],
            'replacement': replacements[num],
            'sheetId': sheetId
        }
    })

# bold the top row
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': sheetId,
            'endRowIndex': 1,
        },
        'cell': {
            'userEnteredFormat': {
                'textFormat': {
                    'bold': True
                }
            }
        },
        'fields': 'userEnteredFormat.textFormat.bold'
    }
})

# bold the first column
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': sheetId,
            'endColumnIndex': 1
        },
        'cell': {
            'userEnteredFormat': {
                'textFormat': {
                    'bold': True
                }
            }
        },
        'fields': 'userEnteredFormat.textFormat.bold'
    }
})

# freeze the first row and column
requests.append({
    'updateSheetProperties': {
        'properties': {
            'sheetId': sheetId,
            'gridProperties': {
                'frozenRowCount': 1
            }
        },
        'fields': 'gridProperties.frozenRowCount'
    }
})

requests.append({
    'updateSheetProperties': {
        'properties': {
            'sheetId': sheetId,
            'gridProperties': {
                'frozenColumnCount': 1
            }
        },
        'fields': 'gridProperties.frozenColumnCount'
    }
})

# change numbers to data type percent%
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': sheetId,
            'startRowIndex': 1,
            'startColumnIndex': 1
        },
        'cell': {
            'userEnteredFormat': {
                'numberFormat': {
                    'type': 'PERCENT',
                    'pattern': '0.00%'
                }
            }
        },
        'fields': 'userEnteredFormat.numberFormat'
    }
})

#auto resize the first column
requests.append({
    "autoResizeDimensions": {
        "dimensions": {
          "sheetId": sheetId,
          "dimension": "COLUMNS",
          "startIndex": 0,
          "endIndex": 1
        }
    }
})

# loop through conditional format background rules
format_values = [['0.9999', '1'], ['0.05', '0.9999'], ['.04999', '.01'], ['0.009999', '0.001'], ['.0009999', '.00001']]
format_colors = [{'red': 0.9, 'green': 0.9, 'blue': 0.9, 'alpha': 1}
    , {'red': 0.0, 'green': 1, 'blue': 0.0, 'alpha': 1}
    , {'red': 0.714, 'green': 0.843, 'blue': 0.659, 'alpha': 1}
    , {'red': 1, 'green': 0.898, 'blue': 0.60, 'alpha': 1}
    , {'red': 1, 'green': 0.949, 'blue': 0.80, 'alpha': 1}]

for i in range(len(format_values)):
    requests.append({
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [
                    {
                        'sheetId': sheetId,
                        'startRowIndex': 1,
                        'startColumnIndex': 1
                    }
                ],
                'booleanRule': {
                    'condition': {
                        'type': 'NUMBER_BETWEEN',
                        'values': [{
                            'userEnteredValue': format_values[i][0],
                        },
                            {
                                'userEnteredValue': format_values[i][1]
                            }]
                    },
                    'format': {
                        'backgroundColor': format_colors[i]
                    }
                }
            },
            'index': i
        }
    })

#make the full batchupdate request to reformat the sheet
body = {'requests': requests}
result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

logging.debug('data sent to google sheet, script finished')
