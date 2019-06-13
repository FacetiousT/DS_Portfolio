#imports
from sql.core import execute_db_query
import requests
import argparse
from requests.auth import HTTPBasicAuth
import numpy as np
import pymc3 as pm
import time
import domo_config
import logging
import os
import ast
import json

# import DOMO SDK
# install pydomo first
#import subprocess
#subprocess.check_call(["python", '-m', 'pip', 'install', 'pydomo'])

#import pydomo SDK
from pydomo.datasets import DataSetRequest, Schema, Column, ColumnType, Policy
from pydomo import Domo

# parse args
parser = argparse.ArgumentParser(description="Run pub cannibalization report",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--config_file', default='', type=str, help="name of config file for the pub we are analyzing")
args = parser.parse_args()

# configure logging
logging.basicConfig(level=logging.DEBUG, filename='cannibalization.log', filemode='a',
                    format='%(name)s - %(levelname)s - %(message)s')
logging.info('cannibalization.py running at ' + time.strftime("%m/%d/%Y %H:%M:%S"))

#import config information
config_file_name = 'config_files/'+args.config_file
with open(config_file_name) as file:
    config = ast.literal_eval(file.read())

#get query from file, based on config
#assume you used arguments
query_file = open('queries/'+config['query_file'])
query = query_file.read()
query_file.close()

query_results = execute_db_query(query)

#get results in a list of dataframes
query_results_desk = query_results[query_results['device']=='Desktop']
query_results_tab = query_results[query_results['device']=='Tablet']
query_results_mob = query_results[query_results['device']=='Mobile']

####set parameters/arguments
####change these params whenever a new test starts
cwd = os.getcwd()
output_path_filename = cwd + '/outputs/' + config['output_filename']  # path and filename for the output file

# if new dataset, create one in DOMO and save the ID
if config['output_dataset_id'] == None:
    # Create an instance of the SDK Client
    domo = Domo(domo_config.domo_id, domo_config.domo_secret, api_host="api.domo.com")

    # define the dataset, name, description, schema
    dsr = DataSetRequest()
    dsr.name = config['output_filename'][:-4] + ' Cannibalization Results'
    dsr.description = ''
    # Valid column types are STRING, DECIMAL, LONG, DOUBLE, DATE, DATETIME.
    # cannibalization results schema
    dsr.schema = Schema([Column(ColumnType.DATETIME, 'run_at')
                            , Column(ColumnType.STRING, 'device')
                            , Column(ColumnType.LONG, 'cu')
                            , Column(ColumnType.LONG, 'cc')
                            , Column(ColumnType.LONG, 'ccs')
                            , Column(ColumnType.DECIMAL, 'control_conv')
                            , Column(ColumnType.LONG, 'tu')
                            , Column(ColumnType.LONG, 'tc')
                            , Column(ColumnType.LONG, 'tcs')
                            , Column(ColumnType.DECIMAL, 'test_conv')
                            , Column(ColumnType.DECIMAL, 'prob_cann')
                            , Column(ColumnType.DECIMAL, 'conf_int_l')
                            , Column(ColumnType.DECIMAL, 'conf_int_h')
                            , Column(ColumnType.DATE, 'date_start')
                            , Column(ColumnType.DATE, 'date_end')])

    # specify the datasets endpoint
    datasets = domo.datasets

    # Create a DataSet with the given Schema
    dataset = datasets.create(dsr)
    domo.logger.info("Created DataSet " + dataset['id'])
    logging.info("Created DataSet " + dataset['id'])

    #put dataset id and name into config file
    config['output_dataset_id'] = dataset['id']
    config['output_dataset_name'] = dsr.name

    #dump information back into file
    with open(config_file_name, "w") as fp:
        json.dump(config,fp)

result_dataset_id = config['output_dataset_id']

# if output file does not exist, first_run == true
if os.path.isfile(output_path_filename):
    first_run = False
else:
    first_run = True

logging.info("First Run: "+str(first_run))

# request API token
def get_token():
    # credentials here
    client_id = domo_config.domo_id
    client_secret = domo_config.domo_secret
    url = "https://api.domo.com/oauth/token?grant_type=client_credentials&amp;scope=data"

    # request the token
    r = requests.get(url, auth=HTTPBasicAuth(client_id, client_secret))
    token = r.json()['access_token']
    return token


# put all dataframes in a list
df_list = [query_results_desk, query_results_tab, query_results_mob]
df_list_names = ['desktop', 'tablet', 'mobile']
n_df_list = []

# get rid of dataframes that do not have enough data/values
for z in range(len(df_list)):

    if query_results['control_users'].astype(int).sum() == 0 or query_results['control_converts'].astype(
            int).sum() == 0 or query_results['treatment_users'].astype(int).sum() == 0 or query_results[
        'treatment_converts'].astype(int).sum() == 0:
        logging.info('insufficient data detected for device ' + str(df_list_names[z]))
    else:
        n_df_list.append(df_list[z])

final_csv_string = ''  # string to hold final output

if len(n_df_list) > 0:

    df_counter = 0
    # check true len of df_list
    for x in range(len(n_df_list)):

        # set the local df
        df = n_df_list[x]

        # aggregate figures and create some new output variables
        cu = df['control_users'].astype(int).sum()
        cc = df['control_converts'].astype(int).sum()
        ccs = df['control_conversions'].astype(int).sum()
        tu = df['treatment_users'].astype(int).sum()
        tc = df['treatment_converts'].astype(int).sum()
        tcs = df['treatment_conversions'].astype(int).sum()

        # float division by zero protection
        if cu != 0 and cc != 0 and tu != 0 and tc != 0:
            df_counter += 1

    df_counter2 = 0

    # loop through each dataframe in the list
    for x in range(len(n_df_list)):

        # set the local df
        df = df_list[x]

        # aggregate figures and create some new output variables
        cu = df['control_users'].astype(int).sum()
        cc = df['control_converts'].astype(int).sum()
        ccs = df['control_conversions'].astype(int).sum()
        tu = df['treatment_users'].astype(int).sum()
        tc = df['treatment_converts'].astype(int).sum()
        tcs = df['treatment_conversions'].astype(int).sum()

        # float division by zero protection
        if cu != 0 and cc != 0 and tu != 0 and tc != 0:

            df_counter2 += 1;

            device = df['device'].max()
            date_start = df['date_start'].max()
            date_end = df['date_end'].max()

            logging.info('analyzing ' + str(device) + ' for dates ' + str(date_start) + ' to ' + str(date_end))

            # create new variables for the mcmc
            # take daily unique conversions and total daily unique visitors, make arrays
            control_obs = np.hstack(([0] * (cu - cc), [1] * cc))
            test_obs = np.hstack(([0] * (tu - tc), [1] * tc))
            control_conv = float(cc) / float(cu)
            test_conv = float(tc) / float(tu)

            # set up the pymc3 model and run it
            with pm.Model() as model:

                # prior as uniform stochastic variable
                # stronger beliefs could lead to different priors
                p_test = pm.Uniform("p_test", 0, 1)
                p_control = pm.Uniform("p_control", 0, 1)

                # deterministic delta variable, our unknown of interest
                # deterministic is not based on a distribution
                delta = pm.Deterministic("delta", p_test - p_control)

                # Set of observations
                # Bernoulli stochastic variables generated via our observed values
                obs_A = pm.Bernoulli("obs_A", p_test, observed=test_obs)
                obs_B = pm.Bernoulli("obs_B", p_control, observed=control_obs)

                # monte carlo simulation, last step of model, this part takes the longest
                # metropolis-hastings algo, gets sequence of random variables from prob. dist.
                step = pm.Metropolis()
                trace = pm.sample(20000, step=step, njobs=2)
                burned_trace = trace[10000:]

            # generated likelihood, prior, and posterior distributions as arrays of values
            p_test_samples = burned_trace["p_test"]
            p_control_samples = burned_trace["p_control"]
            delta_samples = burned_trace["delta"]
            delta_min = delta_samples.min()
            delta_max = delta_samples.max()
            target_cann = -0.02
            abs_target = (control_conv) * target_cann

            # results and calculations data for DOMO
            abs_target = (control_conv) * target_cann
            prob_cann = 100 - (round(np.mean(delta_samples < abs_target) * 100, 2))
            prob_no_cann = round(np.mean(delta_samples > abs_target) * 100, 2)
            conf_int_l = str(np.percentile(delta_samples, 5))
            conf_int_h = str(np.percentile(delta_samples, 95))
            conf_int_rel_l = str(round(100 * (np.percentile(delta_samples, 5) / control_conv), 2))
            conf_int_rel_h = str(round(100 * (np.percentile(delta_samples, 95) / control_conv), 2))
            run_at = (time.strftime("%Y-%m-%d %H:%M:%S"))
            conrol_conv_percent = round(control_conv * 100, 4)
            treatment_conv_percent = round(test_conv * 100, 4)
            avg_diff_percent = round((-(control_conv - (float(tc) / float(tu))) / control_conv) * 100, 3)

            summary_csv_string = run_at + "," + device + "," + str(cu) + "," + str(cc) + "," + str(ccs) + "," + \
                                 str(control_conv) + "," + str(tu) + "," + str(tc) + "," + str(tcs) + "," + str(
                test_conv) + "," + \
                                 str(prob_cann) + "," + conf_int_rel_l + "," + conf_int_rel_h + "," + \
                                 str(date_start.date()) + "," + str(date_end.date())

            # create csv string with main outputs
            if first_run == True:
                if df_counter2 < df_counter:
                    summary_csv_string = summary_csv_string + "\n"
                else:
                    summary_csv_string = summary_csv_string
            else:
                summary_csv_string = "\n" + summary_csv_string

            # concat all outputs as a single csv string
            final_csv_string = final_csv_string + summary_csv_string

        else:
            print('zero values found in calculations')

    # save output to file
    if first_run:
        f = open(output_path_filename, 'w')
        f.write(final_csv_string)
        f.close()
    else:
        f = open(output_path_filename, 'a')
        f.write(final_csv_string)
        f.close()

    # convert file to a string for DOMO
    with open(output_path_filename) as f:
        s = f.read() + '\n'

    # import data via domo SDK (my old code for this retired)
    client_id = domo_config.domo_id
    client_secret = domo_config.domo_secret
    domo = Domo(client_id, client_secret, api_host='api.domo.com')

    # specify the datasets endpoint
    datasets = domo.datasets

    # import the data via SDK
    datasets.data_import(result_dataset_id, s)
    domo.logger.info("Uploaded data to DataSet " + result_dataset_id)
    logging.info("\nUploaded data to DataSet " + result_dataset_id)

    # end time
    logging.info("\nfinished: " + time.strftime("%m/%d/%Y %H:%M:%S"))

else:
    logging.info('insufficient data across all devices')
