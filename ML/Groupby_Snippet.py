#show how to aggregate custom fields with a groupby in pandas

gb = df.groupby(['kmeans_cluster_5']).agg({
    'Income_2':{'Inc_Mean':lambda x: round(np.mean(x),2)
                       ,'Inc_Median':lambda x: round(np.median(x),2)
                       ,'User_Cnt':'count'},
    'SF':{'SF_Median':'median'},
    'Rent':{'Rent_Median':'median'
            ,'Rent_Mean':lambda x: round(np.mean(x),2)},
    '# of Occupants':{'Occupants_Sum':'sum'},
    'Gender': {'Gender_M':lambda x: x[x=='M'].count()
               ,'Gender_F':lambda x: x[x=='F'].count()
               ,'Gender_MF':lambda x: x[x=='MF'].count()
               ,'Gender_Uniques':lambda x: x.nunique()}, #when there is a tie for mode, it gives the list of values
    'Household Type': {'HT_single':lambda x: x[x=='Single'].count()
                       ,'HT_couple':lambda x: x[x=='Couple'].count()
                       ,'HT_family':lambda x: x[x=='Family'].count()
                       ,'HT_mode':lambda x: x.mode()},
    '# of Children':{'Tot_Children':'sum'
                     ,'Children_Mean':lambda x: round(np.mean(x),2)}
})
