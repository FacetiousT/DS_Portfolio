#quick function to generate ROC curve after making test predictions

#import libraries
import pandas as pd
import numpy as np
from sklearn import metrics

#roc_curve function takes predicted labels as 'y_test', then true 'labels', then a title as arguments
#need to rename these arguments
def get_roc_curve(y_test,labels,title=''):

    fpr, tpr, _ = metrics.roc_curve(y_test, labels)    

    #calculate AUC
    roc_auc = metrics.auc(fpr,tpr)    
    
    plt.figure()
    lw = 2
    plt.plot(fpr, tpr, color='darkorange',
             lw=lw, label='ROC curve (area = %0.3f)' % roc_auc)
    plt.plot([0, 1], [0, 1], color='navy', lw=lw, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title(title+'ROC')
    plt.legend(loc="lower right")
    plt.show()    
    
    #print out the log-loss as well
    print ("log-loss: "+str(metrics.log_loss(y_test,labels)))
