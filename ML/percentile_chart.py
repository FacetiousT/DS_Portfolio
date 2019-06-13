#an incomplete script, to protect data

def build_chart(path,publisher,device,date_range):

    #put into dataframe
    df = pd.read_csv(path)
    #make sure you only do this 1 time
    df['conv_rate_bucket'] = df['conv_rate_bucket']*100    
    
    percen_reversed = 100-df['percentile']
    data_to_plot = pd.concat([percen_reversed,df[['pred_at_boundary','conv_above_boundary','conv_rate_bucket',\
                                                            'conv_pct_above_boundary']]],axis=1)

    #sort and index and reformat the data
    data_to_plot = data_to_plot[0:-1]
    data_to_plot = data_to_plot.sort_values(by='percentile',ascending=True)
    data_to_plot.index = range(len(data_to_plot))
    
    #instantiate the plot
    sns.set(font_scale=1.5)

    #custom palette
    flatui = ["#9b59b6"]
    colors = ["windows blue"]#, "amber", "greyish", "faded green", "dusty purple"]

    g = sns.barplot(x='percentile', y='conv_pct_above_boundary'
                    , data = data_to_plot,\
              palette=sns.xkcd_palette(colors))
                    #color_palette("BuGn_r"))
        #cubehelix_palette(20, start=2.6, rot=0 
        #,dark=0.08, light=.6, reverse=False) )   #'Blues_r')

    #add labels and change the figure size
    g.set_xlabel('Percentile of Users')
    # g.invert_xaxis()
    g.set_ylabel('Percent of Conversions')
    g.figure.set_size_inches(20,10)
    g.set_xticklabels(g.xaxis.get_majorticklabels(), rotation=0
                      , fontsize = 15,ha='right')

    # Now make some data labels
    rects = g.patches
    values = []

    for rect in rects:
        ((x0, y0), (x1, y1))  = rect.get_bbox().get_points()
        values.append(y1)

    labels = [str(int(values[i]))+"%" for i in range(len(values))]

    for rect, label in zip(rects, labels):
        height = rect.get_height()
        g.text(rect.get_x() + rect.get_width()/2, height + 1
               , label, ha='center', va='bottom',color="#2b5797")

    #plot a second axis
    #ax2 = g.twinx()
    mycolor1 = "#2ecc71"
    mycolor = "#E61B18"
    mycolor2 = "#F55350"

    ax2 = g.twinx()
    ax2.plot(g.get_xticks(),data_to_plot['pred_at_boundary'],
             linewidth=7, color=mycolor1)

    #add data labels
    #get the coordinates and post the labels
    for i,j in zip(g.get_xticks(),data_to_plot['pred_at_boundary']): 
        
        if(i<len(data_to_plot)-1):
            z = round(j*100,2)
            ax2.annotate('%s%%' %z, 
                         xy=(i,j), 
                         xytext=(0,5), 
                         textcoords='offset points',
                         fontsize=18,
                         color="black",
                         weight="bold")
        #take care of the last, low value
        else:
            z = round(j*100,3)
            ax2.annotate('%s%%' %z, 
                         xy=(i,j), 
                         xytext=(0,5), 
                         textcoords='offset points',
                         fontsize=18,
                         color="black",
                         weight="bold")

    #label and format the 2nd axis
    ax2.set_ylabel('Predicted Conversion Rate')
    vals = ax2.get_yticks()
    ax2.set_yticklabels(['{:3.2f}%'.format(x*100) for x in vals])
    
    # ADD THIS LINE to remove 2nd axis grid
    ax2.grid(None)

    #hardcode some values
    import time
    datetime = time.strftime("%m%d%y%H")

    file_name = publisher+device+datetime+".png"

    #set the title and save the figure
    g.set_title('PERCENT OF CONVERSIONS \n '+publisher+' - '+device+'  '+date_range+'')
    plt.savefig(file_name, bbox_inches='tight', dpi=400)
