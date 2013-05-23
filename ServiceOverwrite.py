#===============================================================================
# '''
# Created on 11 Dec 2012
# 
# @author: dpeters
# 
# Function to overwrite an existing Feature Service in AGOL
# '''
# 
#===============================================================================


import urllib
import json
import arcpy
import time

# Add your own credentials 
agolUser = ''
agolPwd = ''

# Set the environment path
arcpy.env.workspace = r''
arcpy.env.overwriteOutput = 1

# Set the source feature class containing new data
fc = ''
# temporary feature class for processing upload data
tempFC = ''

# Add the url to your AGOL feature service
featureServiceBaseURL = ''

# Log file name
logFileName = r''


##### END OF VARIABLE SETTING #####

startTime = time.time()

# Open a text file to log results to
mylog = open(logFileName, "w")

# Function to write to the log and the python console
def logmsg(messageText):
    mylog.write(messageText)
    mylog.write("\n")
    mylog.flush()
    print messageText

# Function to return a token for this session
def getToken():
    logmsg("Getting Token...")
    data = {'username': agolUser,
        'password': agolPwd,
        'referer' : 'https://www.arcgis.com',
        'f': 'json'}

    URL  = 'https://arcgis.com/sharing/rest/generateToken'

    result = urllib.urlopen(URL, urllib.urlencode(data)).read()
    jres = json.loads(result)
    return jres['token']

def getAGOLFieldList():
    # Get the field list from the AGOL Feature Service
    # Returns a python list of fields

    URL = featureServiceBaseURL + '?f=json'

    data = {'token' : token,
            'f' : 'json'}

    result = urllib.urlopen(URL, urllib.urlencode(data)).read()
    jres = json.loads(result)

    agolFieldList = []

    flds = jres['fields']
    for fld in flds:
        agolFieldList.append(fld['name'])
    
    return agolFieldList

# Function to strip unicode tags from generated json
# e.g. convert { u'key' : u'value' } to { 'key' : 'value' }
# otherwise AGOL will not understand the JSON
def convert_txt(vinput):
    if isinstance(vinput, dict):
        return {convert_txt(key): convert_txt(value) for key, value in vinput.iteritems()}
    elif isinstance(vinput, list):
        return [convert_txt(element) for element in vinput]
    elif isinstance(vinput, unicode):
        return vinput.encode('utf-8')
    else:
        return vinput

# Retrieve the token - required for every REST request
token = getToken()


logmsg("Deleting Features..")

URL = featureServiceBaseURL + '/deleteFeatures'

data = {'token' : token,
        'f' : 'json',
        'where' : 'OBJECTID>-1'}

result = urllib.urlopen(URL, urllib.urlencode(data)).read()
jres = json.loads(result)

delres = jres['deleteResults']
deletedFeatureCount = len(delres)
logmsg(str(delres))
logmsg(str(len(delres)) + ' Features deleted')

# AGOL strips out certain field from an FC when generating a feature service
# So we will only use fields from the FC that match what is in the Feature service

logmsg("Removing fields (Field Info)")

# Get the field list from AGOL
agolFieldList = getAGOLFieldList()

sourceFields = arcpy.ListFields(fc)
myFieldInfo = arcpy.FieldInfo()

# The field info object will hide unnecessary fields
for fld in sourceFields:
    print "Field name " + fld.name
    print "Is it the shape field? " + str(fld.name!="Shape")
    print "Is the field in AGOL?" + str(fld not in agolFieldList)
    if fld.name!="Shape" and fld.name not in agolFieldList:
        
        myFieldInfo.addField(fld.name, fld.name,"HIDDEN", "")
        
arcpy.MakeFeatureLayer_management(fc, tempFC, field_info = myFieldInfo)

# Load the feature layer into a feature set
# this will allow us to use the json property of the feature set
featureSet = arcpy.FeatureSet()
featureSet.load(tempFC)
desc = arcpy.Describe(featureSet)

jfeatures = convert_txt(json.loads(desc.json)['features'])

uploadFeatureCount = len(jfeatures)

logmsg("There are {featureCount} features to upload...".format(featureCount = uploadFeatureCount))

URL = featureServiceBaseURL + '/addFeatures'

logmsg("Ok, so far so good, now let's batch up the features...")

# Split the features into batches so the json isn't too long for the server
for batchStart in range (0, len(jfeatures), 10):

    logmsg("Processing " + str(batchStart) + " to " + str(batchStart + 9))
    data = {'token' : token,
            'f' : 'json',
            'features' : jfeatures[batchStart:batchStart + 10]}
    logmsg('Data to be passed in:')
    logmsg(str(jfeatures[batchStart:batchStart + 10]))
    logmsg("Batch: " + str(batchStart) + " to " + str(batchStart + 9) + "\n")
    result = urllib.urlopen(URL, urllib.urlencode(data)).read()
    logmsg('Result Text:({featuresAdded} results)\n'.format(featuresAdded=len(result)))
    logmsg(result)
    jresult = json.loads(result)
    print "ADD RESULTS"
    for res in jresult['addResults']:
        print res
    
logmsg("Completed in {seconds} seconds! :D:D:D".format(seconds = time.time()-startTime)) 
del mylog
