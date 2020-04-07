#!/usr/bin/env python
# coding: utf-8

# In[21]:


def wait():
    
    root.config(cursor="wait") 
    threading.Thread(target=split_df).start() 

def split_df():
    
    #read in the file
    global file
    global filename
    
    file_snipped_l = file.split("/")
    len_ = len(file_snipped_l)-1
    name = file_snipped_l[len_]
    
    elbl3 = Label(root,text="")
    elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")
    
    try:
        elbl3 = Label(root,text="Loading File")
        elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")
        df = pd.read_csv(file,low_memory=False)        
    except:
        elbl3 = Label(root,text="File Loading Err")
        elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")        
    
    #get size of the file
    try:
        elbl3 = Label(root,text="Getting File Size")
        elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")            
        size = sys.getsizeof(df)
    except:
        elbl3 = Label(root,text="Sizing Err")
        elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")        
        
    #get params
    global splits
    splits = entry1.get()
#     global split_size
#     split_size = entry2.get()
    
    ldf = len(df)
    
    try:
        if splits != 0:
            n = ldf / int(splits)
            n = math.ceil(n)
            list_df = [df[i:i+n] for i in range(0,df.shape[0],n)]

            #write dataframes to file
            for x in range(len(list_df)):
                list_df[x].to_csv(filename+"/"+name[:-4]+"_"+str(x+1)+".csv",index=False)
                
            elbl3 = Label(root,text="New Files Created")
            elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W") 
                
    except:
        elbl3 = Label(root,text="File Creation Err, Specify Split Number")
        elbl3.grid(row=4, column=3, padx=5,pady=5,sticky="W")     
        
    root.config(cursor="")
    root.update() 


# In[22]:


#set the dir
from os import listdir, getcwd, access, R_OK, W_OK, path
from tkinter import filedialog
from tkinter import *
import numpy as np
import math
import time
import pandas as pd
import threading

#get current working dir
cwd = getcwd()
cwd = cwd.replace('\\','\/')

filename = ''
file = ''
splits = 0
split_size = 0

def browse_file():
    global file
    file = filedialog.askopenfilename(initialdir = cwd,title = "Select file",filetypes = (("csv files","*.csv")
                                                                                                   ,("dat files","*.dat")
                                                                                                   ,("all files","*.*")))
    file_snipped_l = file.split("/")
    len_ = len(file_snipped_l)-1
    w = Label(root, text=file_snipped_l[len_],padx=5)
    w.grid(row=1,column=3,columnspan=2,sticky="W")

def browse_path():
    # Allow user to select a directory and store it in global var
    # called folder_path
    global folder_path
    global filename
    filename = filedialog.askdirectory()
    folder_path.set(filename)
    
    w2 = Label(root, text=filename,padx=5)
    w2.grid(row=2,column=3,columnspan=2,sticky="W")    
    
    #close the program
    #global root
    #root.destroy()

#instantiate the GUI
root = Tk()

#set title
root.title('File Splitter')

#set width and height
w = 500
h = 200

ws = root.winfo_screenwidth() # width of the screen
hs = root.winfo_screenheight() # height of the screen

# calculate x and y coordinates for the Tk root window
x = (ws/2) - (w/2)
y = (hs/2) - (h/2)

#set dimensions
root.geometry('%dx%d+%d+%d' % (w, h, x, y))


folder_path = StringVar()

#empty row
lbl1 = Label(root,text="File Splitter Application")
lbl1.grid(row=0, column=2,padx=5,pady=5,columnspan=1)

#browse buttons
button1 = Button(text="Select File", width=20, command=browse_file, pady = 5)
button1.grid(row=1, column=2, pady=5, padx= 5)

button2 = Button(text="Set Output Directory", width=20, command=browse_path, pady = 5)
button2.grid(row=2, column=2)

#entries for params
elbl1 = Label(root,text="Enter Number of Splits")
elbl1.grid(row=3, column=2)
entry1 = Entry(root,font=("Calibri 12"))
entry1.grid(row=3, column=3, pady=5,sticky="W")

# elbl2 = Label(root,text="OR Enter Size of Splits MB(s)")
# elbl2.grid(row=4, column=2, padx=5,pady=5)
# entry2 = Entry(root,font=("Calibri 12"))
# entry2.grid(row=4, column=3, pady=5,sticky="W")

#initiate splitting
button3 = Button(text="Split The File", width=20,command=wait, pady=5)
button3.grid(row=4, column=2,columnspan=1,pady=5,padx=5)
elbl3 = Label(root,text="")
elbl3.grid(row=4, column=3, padx=5,pady=5)

root.mainloop()


# In[ ]:




