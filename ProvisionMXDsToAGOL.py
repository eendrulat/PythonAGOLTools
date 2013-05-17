# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# ProvisionMXDsToAGOL.py
# Created on: 2013-03-06 16:37:30.00000
# Description: Batch upload of MXDs to AGOL Feature Services and WebMaps
# ---------------------------------------------------------------------------

# Import arcpy module
import arcpy, arcgisscripting
import xml.dom.minidom as DOM
import os, os.path
import sys
import urllib2, urllib
import json
import uuid
import time
from time import gmtime, strftime

# Options
DEBUG = False
LOGGING = True

if len(sys.argv) < 5:
    print 'Incorrect number of parameters specified'
    print 'syntax: python <filename> username password mxd_workspace config_file [log_file]'
    print '     username: ArcGIS Online username. User must have Publisher privileges (or above)'
    print '     password: ArcGIS Online password.'
    print '     mxd_workspace: Fully qualified path to a folder containing MXDs to be provisioned.'
    print '     config_file: Fully qualified filename for output configuration file. Destination must be writable.'
    print '     log_file: [optional] Fully qualified filename for output log file. Destination must be writable.'
    sys.exit()


# Local variables:
wrkspc = sys.argv[3]
configFile = sys.argv[4]
user = sys.argv[1]
pw = sys.argv[2]

#logging
if LOGGING:
    if len(sys.argv) > 5:
        logPath = sys.argv[5]
    else:
        logPath = str(time.time())+'.log'
    if os.path.exists(logPath): os.remove(logPath)
    logFile = open(logPath, 'w')
    start = "ArcGIS Online MXD Provisioning started "+strftime("%a, %d %b %Y %H:%M:%S", gmtime())+"\n"
    sys.argv[2] = '[password hidden]'
    start += "Command line parameters: "+str(sys.argv)+"\n"
    start += "==================================================================\n"
    logFile.write(start)
    logFile.flush()

# Debug options
if DEBUG:
    # FIDDLER STUFF - HTTPS
    proxy = urllib2.ProxyHandler({'https':'https://127.0.0.1:8888'})
    opener = urllib2.build_opener(proxy, urllib2.HTTPHandler)
    urllib2.install_opener(opener)
    #
    # FIDDLER STUFF - HTTP
    proxy = urllib2.ProxyHandler({'http':'http://127.0.0.1:8888'})
    opener = urllib2.build_opener(proxy, urllib2.HTTPHandler)
    urllib2.install_opener(opener)
    #

# Logging
def log(information):
    if LOGGING:
        print information
        logFile.write(information)
        logFile.write('\n')
        logFile.flush()
    return

# functions
# Functions to handle all I/O with AGOL
def sendRequest(url, data):
    result = urllib2.urlopen(url, data).read()
    jres = json.loads(result)
    return jres
def sendRequest2(request):
    result = urllib2.urlopen(request).read()
    jres = json.loads(result)
    return jres

# Function to return a token for this session
def getToken(user, pw):
    data = {'username': user,
        'password': pw,
        'referer' : 'https://www.arcgis.com',
        'f': 'json'}
    url  = 'https://arcgis.com/sharing/rest/generateToken'
    jres = sendRequest(url, urllib.urlencode(data))
    return jres['token']

# Function to return an AGOL item details
def getItem(token, itemId):
    data = {"token": token,
            "f": "json"}
    url = "http://www.arcgis.com/sharing/rest/content/items/"+itemId
    return sendRequest(url, urllib.urlencode(data))

# Function to get Layers from a Feature Service
def getLayers(token, url):
    data = {"token": token,
            "f": "json"}
    jres = sendRequest(url, urllib.urlencode(data))
    return jres["layers"]

# Function to get all user content from AGOL
def getUserContent(token, username):
    data = {"token": token,
            "f": "json"}
    url = "http://www.arcgis.com/sharing/content/users/"+username+"?f=json&token="+token
    #workaround unexpected AGOL response to Accept-Encoding:identity header
    request = urllib2.Request(url, headers={"Accept-Encoding":""})
    return sendRequest2(request)

# Function to delete items from AGOL
def deleteItems(token, username, items):
    strItems = str(items).encode('utf-8')[1:-1]
    strItems = strItems.replace('\'', '')
    strItems = strItems.replace('\"', '\"')
    data = {"token": token,
            "items": strItems,
            "f": "json"}
    url = "http://www.arcgis.com/sharing/rest/content/users/"+username+"/deleteItems"
    return sendRequest(url, urllib.urlencode(data))

def shareItems(token, username, items):
    strItems = str(items).encode('utf-8')[1:-1]
    strItems = strItems.replace('\'', '')
    strItems = strItems.replace('\"', '\"')
    data = {"token": token,
            "items": strItems,
            "everyone": "true",
            "f": "json"}
    url = "http://www.arcgis.com/sharing/rest/content/users/"+username+"/shareItems"
    return sendRequest(url, urllib.urlencode(data))

#function to generate popup info for a layer
def getPopupInfo(layerUrl):
    log('...generating Popups...')
    #create Field Info array
    fi = []

    #get field info from feature service
    log ('......getting layer fields')
    fields = getFields(layerUrl)

    # loop through fields but ignore the NAME and OBJECTID fields
    log ('......building Popup')
    for field in fields:
        if str(field["name"]).encode('utf-8') != "OBJECTID":
            fmat = "null"
            if field["type"] == "esriFieldTypeInteger":
                fmat = dict(places=0, digitSeparator="true")
            fi.append(dict(fieldName=str(field["name"]).encode('utf-8'),
                           label=str(field["alias"]).encode('utf-8'),
                           isEditable="false",
                           tooltip="",
                           visible="true",
                           format=fmat,
                           stringFieldOption="textbox"))

    #create popupInfo object
    popupInfo =dict(title="{Name}",
                    fieldInfos = fi
                    )

    return popupInfo


# get field info from feature service
def getFields(url):
    data = {"token": token,
            "f": "json"}
    jres = sendRequest(url, urllib.urlencode(data))
    return jres["fields"]

# Function to create a Web Map
def createWebMap(token, username, title, serviceDetails, featureServiceId):
    # build tags
    tags = []
    for tag in serviceDetails["tags"]:
        tags.append(tag.encode('utf-8'))
    strTags = str(tags).encode('utf-8')
    if len(strTags) > 1:
        strTags = strTags[1:-1]
    strTags = strTags.replace('\'', '')
    strTags = strTags.replace('\"', '')

    # build layer list
    log('Enumerating layers')
    layers = getLayers(token, serviceDetails["url"])
    webmapLayerArr = []
    log('Building WebMap...')
    for layer in reversed(layers): #webmap layers are specified in reverse order!
        log('...layer '+ str(layer["id"])+ ': '+ layer["name"])
        url = str(str(serviceDetails["url"])+"/"+str(layer["id"])).encode('utf-8')
        layerData = dict(url=url, #layer URL
                        id=str(layer["id"]).encode('utf-8'), #id (unique!)
                        visibility=True, #initial state
                        opacity=0.7, #transparency: 1=opaque; 0=transparent
                        mode=1, # ?
                        title=str(layer["name"]).encode('utf-8'), #TOC layer name
                        itemId=featureServiceId.encode('utf-8'), #AGOL item id of this service (GUID)
                        popupInfo=getPopupInfo(url))## Added by PH #popup: either disablePopup=True OR popupInfo {...}
        webmapLayerArr.append(layerData)

    layerList = str(webmapLayerArr)

    # AGOL only likes true & false, not Python's True & False
    layerList = layerList.replace("True", "true")
    layerList = layerList.replace("False", "false")

    # build up a webmap parameter set
    log('Provisioning WebMap')
    params = "item={0}&title={1}&tags={2}&snippet={3}&description={4}&accessInformation={5}&licenseInfo={6}&extent={7}&text=%7B%22operationalLayers%22%3A{8}%2C%22baseMap%22%3A%7B%22baseMapLayers%22%3A%5B%7B%22id%22%3A%22defaultBasemap%22%2C%22opacity%22%3A1%2C%22visibility%22%3Atrue%2C%22url%22%3A%22{9}%22%7D%5D%2C%22title%22%3A%22Imagery%22%7D%2C%22version%22%3A%221.7%22%2C%22applicationProperties%22%3A%7B%22viewing%22%3A%7B%22routing%22%3A%7B%22enabled%22%3Atrue%7D%2C%22basemapGallery%22%3A%7B%22enabled%22%3Atrue%7D%2C%22measure%22%3A%7B%22enabled%22%3Atrue%7D%7D%7D%7D&type=Web%20Map&typeKeywords=Web%20Map%2C%20Explorer%20Web%20Map%2C%20Map%2C%20Online%20Map%2C%20ArcGIS%20Online%2CData%20Editing%2CCollector&overwrite=false&f=json&token={10}"\
    .format(uuid.uuid1(), #item (unique!)
            title, #title
            strTags, #tags
            serviceDetails["snippet"], #snippet
            serviceDetails["description"], #description
            serviceDetails["accessInformation"], #accessInformation
            serviceDetails["licenseInfo"], #licenseInfo
            urllib.quote_plus("-0.8791,51.2169,0.7606,51.771"), #extent
            urllib.quote_plus(layerList), #layer list
            urllib.quote_plus("http://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer"), #basemap
            token) #token

    url = 'http://www.arcgis.com/sharing/content/users/'+username+'/addItem'
    return sendRequest(url, params)

# Function to modify a SDDraft file, changing/injecting properties to make a Service Definition
def modifySDDraft(sddraft):
        # read sddraft xml
        log ('Parsing SDDraft XML')
        doc = DOM.parse(sddraft)

        # Inject the Feature Service marker
        log('Injecting new values...')
        values = doc.getElementsByTagName('TypeName')
        for value in values:
            if value.firstChild.data == 'MapServer':
                log('...updating ' + value.firstChild.data + ' to FeatureServer')
                value.firstChild.data = 'FeatureServer'

        # Inject the static data property
        log('...creating hasStaticData node')
        prop = doc.createElement("PropertySetProperty")
        prop.attributes["xsi:type"] = "typens:PropertySetProperty"
        key = doc.createElement("Key")
        keyval = doc.createTextNode("hasStaticData")
        key.appendChild(keyval)
        val = doc.createElement("Value")
        val.attributes["xsi:type"] = "xs:string"
        valval = doc.createTextNode("true")
        val.appendChild(valval)
        prop.appendChild(key)
        prop.appendChild(val)
        log('...appending hasStaticData node')
        configProps = doc.getElementsByTagName('ConfigurationProperties')[0]
        propArray = configProps.firstChild
        propArray.appendChild(prop)

        # Change the CRUD properties
        values = doc.getElementsByTagName('Value')
        for value in values:
            if value.hasChildNodes():
                # Change the default WebCapabilities from 'Query,Create,Update,Delete,Uploads,Editing' to just 'Query'.
                if value.firstChild.data == 'Query,Create,Update,Delete,Uploads,Editing':
                    value.firstChild.data = 'Query'
                    log('...setting CRUD properties: ' + value.firstChild.data)
                if value.firstChild.data == 'Map':
                    value.firstChild.data = 'Query'
                    log('...setting CRUD properties: ' + value.firstChild.data)

        # output to a new sddraft
        log('Saving new SDDraft')
        if os.path.exists(sddraft): os.remove(sddraft)
        f = open(sddraft, 'w')
        doc.writexml(f)
        f.close()

        return sddraft


# Function to output a file that links MXD-name to WebMap-GUID
def buildJavaScript(config):
    log('Generating JavaScript config file')
    if os.path.exists(configFile): os.remove(configFile)
    f = open(configFile, 'w')
    f.write("var webmaps = "+str(config).encode('utf-8'))
    f.flush()
    f.close()
    return

# Function to authenticate with AGOL via GP. Try 5 times.
def authenticate():
    result = False
    for i in range(0,5):
        log('Authenticating with AGOL...')
        auth = arcpy.SignInToPortal_server(user, pw, 'http://www.arcgis.com/')
        if (auth.getOutput(0) == "true"):
            result = True
            log ('...success')
            break
        log('...failed')
    return result

# Function to publish to AGOL via GP
def UploadtoAGOL(sd):
    result = False
    log('Uploading and provisioning services')
    try:
        uploadSDresult = arcpy.UploadServiceDefinition_server(sd, 'My Hosted Services')
        result = uploadSDresult.getOutput(3)
    except arcgisscripting.ExecuteError as e:
        log('ERROR: '+e.message)
    return result

# main
#userInput = raw_input('This MXD provisioning process will delete any existing ArcGIS Online content with the same names. Do you wish to continue? (Y/N)')
#log("User Input: "+userInput)
#if userInput != 'Y' and userInput != 'y': sys.exit()

config = dict()
token = getToken(user, pw)
content = getUserContent(token, user)
items = content['items']

try:
    # Iterate files in the directory - pull out MXDs
    for root, _, files in os.walk(wrkspc):
        for mxd in files:
            if not mxd.endswith(".mxd"): continue

            # housekeeping
            log('Processing '+mxd)
            mapDoc = arcpy.mapping.MapDocument(wrkspc + mxd)
            service = mxd[:-4]
            sddraft = wrkspc + service + '.sddraft'
            sd = wrkspc + service + '.sd'

            # Process: Convert MXD
            log('Creating Service Definition Draft')
            arcpy.mapping.CreateMapSDDraft(mapDoc, sddraft, service, 'MY_HOSTED_SERVICES')

            # modify sddraft with custom attributes
            sddraft = modifySDDraft(sddraft)

            # analyze new sddraft for errors
            log('Analyzing SDDraft for errors')
            analysis = arcpy.mapping.AnalyzeForSD(sddraft)

            # stage and upload the service if the sddraft analysis did not contain errors
            if analysis['errors'] == {}:
                # create service definition
                log('Creating Service Definition')
                if os.path.exists(sd): os.remove(sd)
                arcpy.StageService_server(sddraft, sd)
                # if required, sign in to My Hosted Services
                if authenticate() == False:
                    log('Cannot authenticate with AGOL. Skipping '+ mxd)
                    continue

                # check/delete existing AGOL content
                existingItems = filter(lambda x:x['title'] == service, items)
                numItems = len(existingItems)
                if numItems > 0:
                    itemIds = []
                    for item in existingItems:
                        itemIds.append(item['id'].encode('utf-8'))
                    log('Deleting '+str(numItems)+' items named \''+service+'\'')
                    deleteItems(token, user, itemIds)

                # publish to My Hosted Services - try [up to] twice
                uploadResult = UploadtoAGOL(sd)
                if uploadResult == False:
                    log('Upload failed. Reattempting delete.')
                    deleteItems(token, user, itemIds)
                    log('Reattempting upload')
                    uploadResult = UploadtoAGOL(sd)
                    if uploadResult == False:
                        log('Upload failed. Skipping '+mxd)
                        continue
                    else:
                        log('Feature Service done: ' +mxd)

                # Build a webmap
                log('Getting Feature Service details')
                itemResult = getItem(token, uploadResult)
                webmapResponse = createWebMap(token, user, service, itemResult, uploadResult)

                #check response and build config / log errors
                if webmapResponse['success'] == True:
                    webmapId = str(webmapResponse['id']).encode('utf-8')
                    uploadResult = str(uploadResult).encode('utf-8')
                    config[service] = webmapId
                    log('Setting sharing permissions')
                    shareItems(token, user, [webmapId, uploadResult])
                else:
                    log("Error provisioning WebMap for "+mxd+":: "+ webmapResponse)

                log('Processing complete: ' +mxd)

            else:
                # if the sddraft analysis contained errors, display them
                log(analysis['errors'])
                log('failed with errors: '+mxd)

            log('============')
except:
    log('ERROR: Unexpected error. Exiting.')
finally:
    buildJavaScript(config)

log('Finishing up')
if LOGGING:
    logFile.write('done\n')
    stop = "==================================================================\nArcGIS Online MXD Provisioning completed "+strftime("%a, %d %b %Y %H:%M:%S", gmtime())+"\n"
    logFile.write(stop)
    logFile.flush()
    logFile.close()

print 'done'



