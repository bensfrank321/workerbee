#!/usr/bin/python

#comments that have a "?" at the end were added by Ben Frank

import netifaces as ni
import ConfigParser
import subprocess
import sys
import time
import os
import logging
from logging.handlers import RotatingFileHandler
import requests, json
import logging
from datetime import datetime
import urllib
import socket
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.internet import pollreactor
from twisted.internet import reactor
from twisted.internet import task
import math
import urllib
from poster.encode import multipart_encode
from poster.streaminghttp import register_openers
import urllib2
from PIL import Image
from PIL import ImageFile
import os.path
import inspect, shutil
import re
from time import sleep
# pollreactor.install()

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Config File Preparation
Config = ConfigParser.ConfigParser({'fhboard': 'False'})
if (os.path.isfile('config.ini')):
    Config.read("config.ini")
else:
    Config.read("config-sample.ini")


# Function used to compare version numbers
def vercmp(version1, version2):
    def normalize(v):
        #This function goes through a list and turns the data into integers?
        return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split(".")]

    return cmp(normalize(version1), normalize(version2))

#Function is used with octoprint_api_key  which is used in more functions?
def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1


# Tor setup for remote support
torOn = True
torHostnameFile = '/var/lib/tor/ssh_hidden_service/hostname'

# Logging Setup
FORMAT = '%(asctime)-15s %(message)s'
logFile = ConfigSectionMap("WorkerBee")['logfile']
log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')

my_handler = RotatingFileHandler(logFile, mode='a', maxBytes=5 * 1024 * 1024,
                                 backupCount=2, encoding=None, delay=0)
my_handler.setFormatter(log_formatter)
my_handler.propagate = False
my_handler.setLevel(logging.DEBUG)

app_log = logging.getLogger('workerbee')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(my_handler)
app_log.propagate = False

##Settings from config file
hasLCD = Config.getboolean("Hardware", "lcd")
hasFHBoard = Config.getboolean("Hardware", "fhBoard")
queue_id = ConfigSectionMap("FabHive")['queue']
workerBeeId = ConfigSectionMap("FabHive")['workerbee']
shouldFlipCamera = Config.getboolean('Hardware', 'flipcamera')
fabhive_url = ConfigSectionMap("FabHive")['fabhiveurl']
api_key = ConfigSectionMap("FabHive")['apikey']
octoprint_api_key = ConfigSectionMap("OctoPrint")['apikey']#gets API key?

##Other startup settings
currentJobId = 0
printingStatus = {}
isPrinting = False
octoprintAPIVersion = {}
octoprintAPIVersion['api'] = '9999'
octoprintAPIVersion['server'] = '9999'

redLEDPin = 17
blueLEDPin = 18
readyButtonPin = 6
cancelButtonPin = 5

##Used for uploading files
#Registers streaming http handlers with urllib2?
register_openers()


#Not currently being used in this script?
MINUTES = 60.0

# script filename (usually with path)
# print inspect.getfile(inspect.currentframe())
# script directory
script_directory = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

# print script_directory
print "WorkerBee started."

#This function is used in GetOctoprintAPIVersion(), printerTemps(), and RequestJob()?S
def octoprint_on():
    try:
        response = urllib2.urlopen('http://localhost:5000', timeout=10)
        return True
    except:
        return False


def freeSpace():
    df = subprocess.Popen(["df", "/"], stdout=subprocess.PIPE)
    output = df.communicate()[0]
    device, size, used, available, percent, mountpoint = output.split("\n")[1].split()
    logging.debug("Used: " + str(percent))
    percent = percent.replace('%', '')
    percent = "." + percent
    return percent

#Reboots script?
def rebootscript():
    print "rebooting system"
    command = "/sbin/reboot"#Linux terminal command is executed and reboots script?
    subprocess.call(command, shell=True)#calls/executes command using class subprocess?

#Reads file which is a variable with a name called filename?
def file_get_contents(filename):
    with open(filename) as f:
        return f.read()


def getOctoprintAPIVersion():
    global octoprintAPIVersion

    headers = {'X-Api-Key': octoprint_api_key}
    if octoprint_on():
        try:
            r = requests.get('http://localhost:5000/' + 'api/version', headers=headers)
            app_log.debug("R.Text: " + r.text)
            decodedData = json.loads(r.text)

            octoprintAPIVersion['api'] = decodedData['api']
            octoprintAPIVersion['server'] = decodedData['server']
            app_log.debug(
                "Octoprint API Versions: API(" + octoprintAPIVersion['api'] + ") Server(" + octoprintAPIVersion[
                    'server'] + ")")
        except:
            app_log.debug("Exception determining API version" + str(sys.exc_info()[0]))
            app_log.debug("API Key used: " + octoprint_api_key)
            octoprintAPIVersion['api'] = '9999'
    else:
        app_log.debug("OctoPrint is not up yet")
        updateBeeStatus(2, 'OctoPrint is not up yet')


##This function might not be needed.  Keeping it here as a placeholder for now.
def isPrinterOnline():
    headers = {'Authorization': api_key}
    try:
        r = requests.get('http://localhost:5000/' + 'api/job', headers=headers)#Creates URL for specific printer and stores in variable "r"?
        if (decodedData['state'] == 'Offline'):
            updateBeeStatus(3, 'Printer is offline for octoprint')
            return False
    except:
        e = sys.exc_info()[0]
        app_log.debug('Exception trying to determine if the printer is online: %s' % e)
        return False
    return True


def printerStatus():
    global isPrinting
    headers = {'X-Api-Key': api_key}
    try:
        # Get status from FabHive
	app_log.debug("bot url: " + fabhive_url + 'bees/' + str(workerBeeId))
        r = requests.get(fabhive_url + 'bees/' + str(workerBeeId), headers=headers)
        decodedData = json.loads(r.text)
        bot_stats=decodedData['bots'][0]
	app_log.debug("here")
        # app_log.debug("bot url: " + fabhive_url + 'bees/' + str(workerBeeId))
        # app_log.debug("bot status: " + json.dumps(bot_stats))

        # Get status from OctoPrint
        headers = {'X-Api-Key': octoprint_api_key}
        r = requests.get('http://localhost:5000/' + 'api/job', headers=headers)
        # app_log.debug("job status: " + r.text)

        decodedData = json.loads(r.text)
        if ('Offline' in decodedData['state']):
            updateBeeStatus(3, 'Printer is offline for octoprint')
            return 'Printer Offline'
        if (decodedData['state'] == 'Operational' and bot_stats['status'] == 0):
            isPrinting = False
            return 'idle'
        if (decodedData['state'] == 'Operational' and decodedData['progress']['completion'] == 100):
            isPrinting = False
            return 'printing complete'
        if (decodedData['state'] == 'Printing' and bot_stats['status'] != 0):
            return 'printing'
        if (decodedData['state'] == 'Printing' and bot_stats['status'] == 0):
            updateBeeStatus(statusCode=1, message='Connected to the hive.')
            return 'printing'
        if (decodedData['state'] == 'Closed' or bot_stats['status'] != 0):
            return 'offline'

        app_log.debug("job status: " + r.text)
        return 'other'

    except:
        e = sys.exc_info()[0]
        app_log.debug('Exceptiong determining printer status:  %s' % e)
        app_log.debug("API Version: " + str(getOctoprintAPIVersion()))
        if (octoprintAPIVersion['api'] == '9999'):
            app_log.debug("Unable to get API Version")
            updateBeeStatus(2, 'Unable to get API for OctoPrint')
            return 'offline'
        else:
            return 'other'


def getPrintingStatus():
    global isPrinting
    headers = {'X-Api-Key': octoprint_api_key}
    r = requests.get('http://localhost:5000/' + 'api/job', headers=headers)
    try: 
        decodedData = json.loads(r.text)
        global printingStatus
        if (decodedData['state'] == 'Printing'):
           printingStatus['percentComplete'] = decodedData['progress']['completion']
           printingStatus['timeLeft'] = decodedData['progress']['printTimeLeft']
           printingStatus['fileName'] = decodedData['job']['file']['name']
           isPrinting = True
        else:
           printingStatus['percentComplete'] = decodedData['progress']['completion']
           printingStatus['timeLeft'] = '0'
           printingStatus['fileName'] = decodedData['job']['file']['name']
    except:
        e = sys.exc_info()[0]
        app_log.debug('Exception getting print status:  %s' % e)

    r = requests.get('http://localhost:5000/api/printer', headers=headers)
    try:
        decodedData = json.loads(r.text)
        printingStatus['temperature'] = decodedData['temperature']['tool0']['actual']

    except:
        e = sys.exc_info()[0]
        app_log.debug('Exception determining temp:  %s' % e)
        app_log.debug("getPrintingStatus: Error getting temperature: ")
        printingStatus['temperature'] = 0.0
    return printingStatus

#Checks printer temperatures
def printerTemps():
    temps = {}
    temps['bed'] = 0
    temps['hotend'] = 0

    if octoprint_on():
        app_log.debug("Getting printer temps")
        try:
            headers = {'X-Api-Key': octoprint_api_key}
            r = requests.get('http://localhost:5000/api/printer', headers=headers)
            # app_log.debug("(" + r.text + ")")
            if (r.text == "Printer is not operational" or octoprintAPIVersion['api'] == '9999'):
                return temps

            decodedData = json.loads(r.text)
            if (vercmp(octoprintAPIVersion['server'], '1.2.2')):
                temps['bed'] = decodedData['temperature']['bed']['actual']
                temps['hotend'] = decodedData['temperature']['tool0']['actual']
            else:
                temps['bed'] = decodedData['temps']['bed']['actual']
                temps['hotend'] = decodedData['temps']['tool0']['actual']
            app_log.debug("bed: " + str(temps['bed']))
            app_log.debug("hotend: " + str(temps['hotend']))

            if (temps['hotend'] > 50):
                turnOnRed()
            else:
                turnOffRed()
        except:
            app_log.debug("printerTemps: Error getting temperature. ")
    return temps


def updateLCD(message, color):
    if (hasLCD):
        lcd.clear()
        lcd.set_color(1.0, 1.0, 0.0)
        lcd.message(message)


def showIP():
    if (hasLCD):
        lcd.clear()
        # lcd.set_color(1.0,1.0,0.0)
        lcd.message("IP:" + [(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close()) for s in
                             [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1] + "\n")


def showStatus():
    status = printerStatus()

    if (hasLCD):
        lcd.clear()
        lcd.message("Printer Status: \n" + status)

    app_log.debug("Status: " + status)


def markJobTaken(jobID):
    ##Make sure job isn't already taken
    try:
        headers = {'X-API-Key': api_key}
        r = requests.get(fabhive_url + 'jobs/' + str(jobID), headers=headers)
        app_log.debug(r.text)
    except:
        app_log.debug("Brrr...that didn't work")
        return False

    decodedData = json.loads(r.text)
    app_log.debug(r.text)
    if (decodedData['error'] == True or decodedData['status'] != 0):
        return False
    else:
        headers = {'X-API-Key': api_key}
        data = {'status': '1', 'bot_id': workerBeeId}
        try:
            r = requests.put(fabhive_url + 'jobs/' + str(jobID), data=data, headers=headers)
            decodedData = json.loads(r.text)
            if (decodedData['error'] == False):
                app_log.debug("Mark Job Taken: " + r.text)
                return True
        except:
            app_log.debug("Failed here")
            reactor.stop()
            sys.exit()
            return False


def markJobCompleted(jobID):
    app_log.debug("Mark Job Complete function for job id: " + str(jobID))
    if (jobID > 0):
        headers = {'X-Api-Key': api_key}
        data = {'status': '2', 'bot_id': workerBeeId}
        try:
            file = open('webcam.jpg', 'wb')
            file.write(urllib.urlopen("http://127.0.0.1:8080/?action=snapshot").read())
            file.close
            app_log.debug("Saved Image")
            im = Image.open('webcam.jpg')
            app_log.debug("Opened Image")
            if shouldFlipCamera:
                rotateImaged = im.rotate(180)
                app_log.debug("Rotated Image")
                rotateImaged.save('webcam-flipped.jpg')
                app_log.debug("Saved Rotated Image")
                file = open('webcam-flipped.jpg', 'r')
            else:
                file = open('webcam.jpg', 'r')

            files = {'file': ('webcam.jpg', file)}
        except:
            app_log.debug("Failed to get image of completed job: " + str(sys.exc_info()[0]))

        try:
            if 'files' in locals():
                app_log.debug("Posting Job Complete w/ Image: " + str(jobID))
                r = requests.post(fabhive_url + 'jobs/' + str(jobID), data=data, headers=headers, files=files)

            else:
                app_log.debug("Putting Job Complete w/out image: " + str(jobID))
                r = requests.put(fabhive_url + 'jobs/' + str(jobID), data=data, headers=headers)
                decodedData = json.loads(r.text)
            if (decodedData['error'] == False):
                app_log.debug("Mark Job Completed: " + r.text)
                return True
            else:
                return True
        except:
            app_log.debug("Failed to mark job completed: " + str(jobID))
            return False

    return True


def addJobToOctoprint(job):
    ##Download file
    app_log.debug("Downloading file: " + job['gcodePath'])
    try:
        r = requests.get(job['gcodePath'], stream=True)
        with open(job['gcodePath'].split('/')[-1], 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()

        app_log.debug("Sending file to octoprint: " + job['gcodePath'])

        datagen, headers = multipart_encode({"file": open(job['gcodePath'].split('/')[-1], "rb")})
        headers['X-Api-Key'] = octoprint_api_key
        request = urllib2.Request("http://localhost:5000/api/files/local", datagen, headers)
        # Actually do the request, and get the response
        postResponse = urllib2.urlopen(request).read()
        app_log.debug("Post to octoprint response: " + str(postResponse))

        # files = {job['gcodePath']: open(job['gcodePath'].split('/')[-1], 'rb')}
        # r=requests.post( 'http://localhost:5000/api/files/local', headers=headers,files=files)
        # app_log.debug("Sent file to octoprint: " + r.text)
        # print "Response: " + str(r)
        # print "Response Text: " + str(r.text)
        decodedData = json.loads(postResponse)
        if (decodedData['done'] == True):
            os.remove(job['gcodePath'].split('/')[-1])
            return True
        else:
            return False
    except urllib2.URLError as e:
        print e.code
        print e.reason
        app_log.debug("Exception sending file to octoprint: " + str(sys.exc_info()[0]))
        return False


def cancelPrint():
    turnOnBlue()
    app_log.debug("Getting printer temps")
    headers = {'X-Api-Key': octoprint_api_key, 'Content-Type': 'application/json'}
    data = {'command': 'cancel'}
    r = requests.post('http://localhost:5000/api/job', headers=headers, data=json.dumps(data))
    app_log.debug("(" + r.text + ")")
    app_log.debug("Homing Axis")
    headers = {'X-Api-Key': octoprint_api_key, 'Content-Type': 'application/json'}
    data = {'command': 'home', "axes": ["x", "y"]}
    r = requests.post('http://localhost:5000/api/printer/printhead', headers=headers, data=json.dumps(data))
    app_log.debug("(" + r.text + ")")
    updateBeeStatus(statusCode=1, message='Cancel Button Pressed')
    sleep(2)
    turnOffBlue()


def octoprintFile(job):
    fileName = job['gcodePath'].split('/')[-1]
    headers = {'X-Api-Key': octoprint_api_key, 'Content-Type': 'application/json'}
    # data={"command":"select"}
    data = {"command": "select", "print": "true"}
    # print "filename: " + fileName
    # print "Data: " + str(data)
    r = requests.post('http://localhost:5000/api/files/local/' + fileName, headers=headers, data=json.dumps(data))
    # print "Response: " + str(r.status_code)
    if (r.status_code == 204):
        app_log.debug("Success")
        return True
    else:
        app_log.debug("Failed to print: " + str(r) + r.text)
        return False


def readyButtonPressed():
    turnOnBlue()
    updateBeeStatus(statusCode=0, message='Ready Button Pressed')
    sleep(2)
    turnOffBlue()


def updateBeeStatus(statusCode=99, message='', temp=0, diskSpace=0):
    app_log.debug("Updating printer status: " + message)
    if (temp == 0):
        app_log.debug("temp is 0")
        temps = printerTemps()
        temp = temps['hotend']
        app_log.debug("Temp Now: ")
        app_log.debug(temp)
    if diskSpace == 0:
        diskSpace = freeSpace()
    app_log.debug("Updating printer status temp: " + str(temp))
    app_log.debug("Updating printer status diskSpace: " + str(diskSpace))
    data={}
    data['temperature']=temp
    data['diskSpaceFree']=diskSpace

    if statusCode != 99:
        data['status']=str(statusCode)

    if message != '':
        data['message']=message

    data['last_checkin']=str(time.strftime('%Y-%m-%d %H:%M:%S'))

    app_log.debug("Sending Data: ")
    app_log.debug(data)
    headers = {'X-API-Key': api_key}
    try:
        r = requests.put(fabhive_url + 'bees/' + str(workerBeeId) + '?' + urllib.urlencode(data), headers=headers)
    except:
        app_log.debug("Could not update bot status. Network Issue.: " + str(sys.exc_info()[0]))
        # print "response: " + r.text


def reportTorName():
    try:
        torHostname = file_get_contents(torHostnameFile).rstrip('\n')
        app_log.debug("Tor Hostname: " + torHostname)
        gws=ni.gateways()
        # print(gws)
        iface=gws['default'][ni.AF_INET][1]
        ni.ifaddresses(iface)
        ip = ni.ifaddresses(iface)[2][0]['addr']
        # print (ip)
    except:
        app_log.debug("Could not tor hostname.")

    data = {'hostname': torHostname, 'controlURL': 'http://' + ip}
    headers = {'X-API-Key': api_key}
    try:
        r = requests.put(fabhive_url + 'bees/' + str(workerBeeId) + '?' + urllib.urlencode(data), headers=headers)
    except:
        app_log.debug("Could not update hostname.")


def checkBotIn():
    global printingStatus
    global isPrinting
    global currentJobId
    app_log.debug("Checking Bot In")
    reportTorName()

    status = printerStatus()

    app_log.debug("Status: " + status)

    if (status == "printing complete"):
        printStatus = getPrintingStatus()
        diskUsed = freeSpace()
        # updateBeeStatus(statusCode=99, message='Checked In', temp=printStatus['temperature'], diskSpace=diskUsed)
        updateBeeStatus(statusCode=99, message='Printing Complete: ' + printStatus['fileName'] + '<BR/>Percent Complete: ' + str(
            math.ceil(float(printStatus['percentComplete']))), temp=printStatus['temperature'], diskSpace=diskUsed)
        if (currentJobId > 0):
            app_log.debug("Time to mark the job as completed.")
            if (math.ceil(printStatus['percentComplete']) == 100):
                while True:
                    app_log.debug("Marking job complete")
                    result = markJobCompleted(currentJobId)
                    app_log.debug("Marking job complete: " + str(result))
                    if (result):
                        app_log.debug("Job marked complete")
                        break
                currentJobId = 0


    if (status == "printing"):
        app_log.debug("I'm printing")
        printStatus = getPrintingStatus()
        diskUsed = freeSpace()
        updateBeeStatus(statusCode=1, message='Printing: ' + printStatus['fileName'] + '<BR/>Percent Complete: ' + str(
            math.ceil(float(printStatus['percentComplete']))), temp=printStatus['temperature'], diskSpace=diskUsed)


   if (status == "idle" and isPrinting == False):#If a printer is idle and isn't printing, the request a job?
        app_log.debug("Requesting job")
        requestJob()#activate function called requestJob()?

    if (status == "offline"):
        updateBeeStatus(message='Checking In')

    if (status == 'Printer Offline'):#If printer is offline, change status to offline?
        updateBeeStatus(3, 'Printer is offline for octoprint')


def requestJob():
    global currentJobId
    app_log.debug("Requesting new job")
    headers = {'X-Api-Key': api_key}
    try:
        # Get status from FabHive
        r = requests.get(fabhive_url + 'hives/' + str(queue_id) + '/next', headers=headers)
        app_log.debug('here: ' + fabhive_url + 'hives/' + str(queue_id) + '/next')
        app_log.debug(r.text)#r.text turns html codes into readable text then prints text with app_log.debug?
        decodedData = json.loads(r.text)#deserializes r.text and turns it into a python object?
        app_log.debug('here')
        # app_log.debug("bot url: " + fabhive_url + 'bees/' + str(workerBeeId))
        app_log.debug("next Job: " + json.dumps(decodedData))#json.dumps(decodedData)--Serializes obj to a JSON formatted str?
        job=decodedData['jobs'][0]
        updateBeeStatus(statusCode=1, message='Received job: ' + job['filename'])
        if (addJobToOctoprint(job) == True):
            app_log.debug("This worked, mark the file as taken")
            result=markJobTaken(job['id'])
            if(result==True):
                updateBeeStatus(statusCode=1,message='Printing: ' + job['filename'])
                currentJobId=job['id']
                result=octoprintFile(job)
            else:
                updateBeeStatus(statusCode=0,message='Job was already taken')
                currentJobId=0
        else:
            updateBeeStatus(statusCode=0,message='Job failed to load on Octoprint')
            currentJobId=0

    except:
        e = sys.exc_info()[0]
        app_log.debug('Exception getting next job:  %s' % e)

if octoprint_on():
    getOctoprintAPIVersion()
    printStatus = getPrintingStatus()
    diskUsed = freeSpace()
    updateBeeStatus(statusCode=1, message='Starting Up', temp=printStatus['temperature'], diskSpace=diskUsed)
    reportTorName()

checkinLoop=task.LoopingCall(checkBotIn)
checkinLoop.start(5)
reactor.run()


# All previous code for reference
#
#
#
#
# #Twisted Implementation
# class HiveClient(Protocol):
# 	def __init__(self, factory):
# 		self.factory = factory
# 		self.hasConnected=False
# 		self.checkInRepeater = LoopingCall(self.checkBotIn)
#
# 	def connectionMade(self):
# 		data={'type':'connect','bot':workerBeeId}
# 		self.transport.write(json.dumps(data))
#
# 		updateBeeStatus(statusCode=1,message='Connected to the hive.')
# 		try:
# 			torHostname=file_get_contents(torHostnameFile).rstrip('\n')
# 			app_log.debug("Tor Hostname: " + torHostname)
# 		except:
# 			app_log.debug("Could not tor hostname.")
#
# 		data={'hostname':torHostname}
# 		headers={'Authorization':api_key}
# 		try:
# 		  r=requests.put(fabhive_url + 'bots/' + str(workerBeeId) + '/hostname',data=data,headers=headers)
# 		except:
# 		  app_log.debug("Could not update bot status. Network Issue.")
#
# 		##Report IP Address
# 		try:
# 			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 			s.connect(("8.8.8.8",80))
# 			address=s.getsockname()[0]
# 			app_log.debug("IP Address: " + address)
# 			s.close()
# 			data={'address':address}
# 			headers={'Authorization':api_key}
# 			try:
# 			  r=requests.put(fabhive_url + 'bots/' + str(workerBeeId) + '/address',data=data,headers=headers)
# 			except:
# 			  app_log.debug("Unable to report Address")
#
# 		except:
# 			app_log.debug("Unable to get Address")
#
# 		##Check In to FabHive every minute
# 		self.checkInRepeater.start(1 * MINUTES)
#
# 		self.hasConnected=True
#
# 	def dataReceived(self, data):
# 		global currentJobId
# 		app_log.debug( "> Received: ''%s''\n" % (data))
# 		messages=data.split('\n')
#
# 		for message in messages:
# 			app_log.debug("messages: " + message)
# 			decodedData=json.loads(message)
# 			if(decodedData['type']=='job'):
# 				app_log.debug("received a new job")
# 				updateBeeStatus(statusCode=1,message='Received job: ' + decodedData['filename'])
# 				if(addJobToOctoprint(decodedData)==True):
# 					app_log.debug("This worked, mark the file as taken")
# 					result=markJobTaken(decodedData['id'])
# 					if(result==True):
# 						updateBeeStatus(statusCode=1,message='Printing: ' + decodedData['filename'])
# 						currentJobId=decodedData['id']
# 						result=octoprintFile(decodedData)
# 					else:
# 						updateBeeStatus(statusCode=0,message='Job was already taken')
# 						currentJobId=0
# 				else:
# 					updateBeeStatus(statusCode=0,message='Job failed to load on Octoprint')
# 					currentJobId=0
#
#
# 	def stopAllTimers(self):
# 		app_log.debug("Stopping all timers")
# 		self.checkInRepeater.stop
#
#
# 	def checkBotIn(self):
# 		global printingStatus
# 		global isPrinting
# 		global currentJobId
# 		if(self.hasConnected):
# 			showStatus()
# 			app_log.debug("I should check in now. Queen Bee might be worried about me.")
#
# 			data={'type':'checkIn','bot':workerBeeId}
# 			self.transport.write(json.dumps(data) + '\n')
#
# 			status=printerStatus()
#
# 			app_log.debug("Status: " + status)
# 			app_log.debug("isPrinting: " + str(isPrinting))
#
# 			if(status=="printing complete"):
# 				printStatus=getPrintingStatus()
# 				diskUsed=freeSpace()
# 				updateBeeStatus(statusCode=99,message='Checked In',temp=printStatus['temperature'],diskSpace=diskUsed)
# 				if(currentJobId>0):
# 					if(printingStatus['percentComplete']==100):
# 						while True:
# 							app_log.debug("Marking job complete")
# 							result=markJobCompleted(currentJobId)
# 							app_log.debug("Marking job complete: " + str(result))
# 							if(result):
# 								app_log.debug("Job marked complete")
# 								break
# 						currentJobId=0
#
# 			if(status=="printing"):
# 				app_log.debug("I'm printing")
# 				printStatus=getPrintingStatus()
# 				diskUsed=freeSpace()
# 				updateBeeStatus(statusCode=1,message='Printing: ' + printStatus['fileName'] + '<BR/>Percent Complete: ' + str(math.ceil(printStatus['percentComplete'])),temp=printStatus['temperature'],diskSpace=diskUsed)
#
# 		 	if(status=="idle" and isPrinting==False):
# 				app_log.debug("Requesting job")
# 				self.requestJob()
#
# 		else:
# 			app_log.debug("We haven't connected yet. No need to check in yet.")
#
# 	def requestJob(self):
# 		if(self.hasConnected):
# 			data={'type':'jobRequest','bot':workerBeeId}
# 			self.transport.write(json.dumps(data))
# 		else:
# 			app_log.debug("We haven't connected yet.")
#
#
# class WorkerBee(object):
# 	def __init__(self):
# 		updateBeeStatus(statusCode=1,message='Printer is online.')
# 		if (hasLCD):
# 			lcd.set_color(0.0, 1.0, 0.0)
# 			lcd.clear()
# 			lcd.message('Connected.')
#
#
#
#
# class HiveFactory(ReconnectingClientFactory):
# 	def __init__(self):
# 		self.protocol=HiveClient(self)
# 		self.workerBee=WorkerBee()
#
# 		##Check temp every 15 seconds for LED
# 		self.checkTempRepeater = LoopingCall(self.checkPrinterTemp)
# 		self.checkTempRepeater.start(1*15,True)
#
# 		##Check for new config file every 30 seconds
# 		self.configFileRepeater=LoopingCall(checkConfigFile)
# 		self.configFileRepeater.start(1*30,True)
#
# 		##Check cancel and ready buttons every 3 seconds
# 		if hasFHBoard:
# 			self.buttonCheckRepeater=LoopingCall(buttonChecker)
# 			self.buttonCheckRepeater.start(1*3,True)
#
# 	def startedConnecting(self, connector):
# 		app_log.debug('Started to connect.')
#
#
# 	def buildProtocol(self, addr):
# 		app_log.debug('Connected.')
# 		app_log.debug('Resetting reconnection delay')
# 		self.resetDelay()
# 		return HiveClient(self)
#
# 	def clientConnectionLost(self, connector, reason):
# 		app_log.debug('Lost connection.  Reason:' + str(reason))
# 		self.protocol.stopAllTimers();
# 		ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
#
# 	def clientConnectionFailed(self, connector, reason):
# 		app_log.debug('Connection failed. Reason:' + str(reason))
# 		self.protocol.stopAllTimers();
# 		ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)
#
# 	def checkPrinterTemp(self):
# 		# extruderTemp=self.workerBee.pronsole.status.extruder_temp
# 		if hasFHBoard:
# 			temps=printerTemps()
# 			if(temps['hotend']>40):
# 				turnOnRed()
# 			else:
# 				turnOffRed()
# 		if (hasLCD):
# 			temps=printerTemps()
# 			if(temps['hotend']>40):
# 				lcd.set_color(1.0,0.0,0.0)
# 			else:
# 				lcd.set_color(0.0,0.0,1.0)
#
# 			lcd.clear()
# 			lcd.message("E Temp:" + str(temps['hotend']) + "\n")
# 			lcd.message("B Temp:" + str(temps['bed']) + "\n")
#
# getOctoprintAPIVersion()
# reactor.connectTCP("fabhive.buzz", 5005, HiveFactory())
#
# # reactor.callWhenRunning(WorkerBee())
# reactor.run()
