#!/usr/bin/python

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
pollreactor.install()
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
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
import RPi.GPIO as GPIO


ImageFile.LOAD_TRUNCATED_IMAGES = True

#Config File Preparation
Config = ConfigParser.ConfigParser()
if(os.path.isfile('config.ini')):
	Config.read("config.ini")
else:
	Config.read("config-sample.ini")


#Function used to compare version numbers
def vercmp(version1, version2):
	return 1
	def normalize(v):
		return [int(x) for x in re.sub(r'(\.0+)*$','', v).split(".")]
    #return cmp(normalize(version1), normalize(version2))

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

#Tor setup for remote support
torOn = True
torHostnameFile = '/var/lib/tor/ssh_hidden_service/hostname'

# Logging Setup
FORMAT = '%(asctime)-15s %(message)s'
logFile=ConfigSectionMap("WorkerBee")['logfile']
log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')

my_handler = RotatingFileHandler(logFile, mode='a', maxBytes=5*1024*1024,
                                 backupCount=2, encoding=None, delay=0)
my_handler.setFormatter(log_formatter)
my_handler.propagate = False
my_handler.setLevel(logging.DEBUG)

app_log = logging.getLogger('workerbee')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(my_handler)
app_log.propagate = False

##Settings from config file
hasLCD=Config.getboolean("Hardware","lcd")
hasFHBoard=Config.getboolean("Hardware","fhBoard")
queue_id=ConfigSectionMap("FabHive")['queue']
workerBeeId=ConfigSectionMap("FabHive")['workerbee']
shouldFlipCamera=Config.getboolean('Hardware','flipcamera')
fabhive_url=ConfigSectionMap("FabHive")['fabhiveurl']
api_key=ConfigSectionMap("FabHive")['apikey']
octoprint_api_key=ConfigSectionMap("OctoPrint")['apikey']

##Other startup settings
currentJobId = 0
printingStatus={}
isPrinting=False
octoprintAPIVersion={}
octoprintAPIVersion['api']='9999'
octoprintAPIVersion['server']='9999'

redLEDPin=17
blueLEDPin=18
readyButtonPin=6
cancelButtonPin=5

##Hardware Setup
if hasFHBoard:
	GPIO.setmode(GPIO.BCM)
	##Setup LEDs
	GPIO.setup(redLEDPin,GPIO.OUT)
	GPIO.output(redLEDPin,True)
	GPIO.setup(blueLEDPin,GPIO.OUT)
	GPIO.output(blueLEDPin,True)
	sleep(1)
	GPIO.output(redLEDPin,False)
	GPIO.output(blueLEDPin,False)

	##Setup Buttons
	GPIO.setup(cancelButtonPin, GPIO.IN) #1 by default, 0 when pressed
	GPIO.setup(readyButtonPin, GPIO.IN)

def turnOnRed():
	if hasFHBoard:
		GPIO.output(redLEDPin,True)

def turnOffRed():
	if hasFHBoard:
		GPIO.output(redLEDPin,False)

def buttonChecker():
	if not GPIO.input(cancelButtonPin):
		app_log.debug("Cancel button pressed")
		cancelPrint()
	if not GPIO.input(readyButtonPin):
		app_log.debug("Ready button pressed")
		readyButtonPressed()


##File watching setup
path_to_watch = "/dev/disk/by-label/"
path_mount_base = "/tmp/fabhive"
filename_to_look_for="/config.ini"
before = dict ([(f, None) for f in os.listdir (path_to_watch)])

##Used for uploading files
register_openers()

if (hasLCD):
	import Adafruit_CharLCD as LCD
	# Initialize the LCD using the pins
	lcd = LCD.Adafruit_CharLCDPlate()
	lcd.set_color(1.0, 1.0, 0.0)
	lcd.clear()
	lcd.message('Starting...')
	time.sleep(3.0)



MINUTES = 60.0

# script filename (usually with path)
# print inspect.getfile(inspect.currentframe())
# script directory
script_directory=os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


# print script_directory
print "WorkerBee started."

def octoprint_on():
    try:
        response=urllib2.urlopen('http://localhost:5000',timeout=1)
        return True
    except:
	    return False

def freeSpace():
	df = subprocess.Popen(["df", "/"], stdout=subprocess.PIPE)
	output = df.communicate()[0]
	device, size, used, available, percent, mountpoint = output.split("\n")[1].split()
	logging.debug("Used: " + str(percent))
	percent=percent.replace('%','')
	percent="." + percent
	return percent

def rebootscript():
    print "rebooting system"
    command = "/sbin/reboot"
    subprocess.call(command, shell = True)

def checkConfigFile():
	app_log.debug("Checking for new config file")
	global before
	after = dict ([(f, None) for f in os.listdir (path_to_watch)])
	added = [f for f in after if not f in before]
	removed = [f for f in before if not f in after]
	if added:
		i=0
		for f in added:
			app_log.debug("New Device Found: " + f)
			if not (os.path.isdir(path_mount_base + str(i))):
				os.mkdir(path_mount_base + str(i))
			subprocess.check_call(["mount",path_to_watch + f,path_mount_base + str(i)])
			if(os.path.isfile(path_mount_base+str(i)+filename_to_look_for)):
				app_log.debug("Found new config file")
				shutil.copyfile(path_mount_base+str(i)+filename_to_look_for,script_directory+filename_to_look_for);
				rebootscript()
			else:
				app_log.debug("No config file on drive, unmounting")
				subprocess.check_call(["umount",path_mount_base + str(i)])
			i=i+1
	else:
		app_log.debug("No new devices")

	if removed:
		app_log.debug("Removed: " + ' '.join(['%s' % f for f in removed]))
	before = after

def file_get_contents(filename):
    with open(filename) as f:
        return f.read()

def getOctoprintAPIVersion():
	global octoprintAPIVersion

	headers={'X-Api-Key':octoprint_api_key}
	if octoprint_on():
		try:
			r=requests.get('http://localhost:5000/' + 'api/version',headers=headers)
			app_log.debug("R.Text: " + r.text)
			decodedData=json.loads(r.text)

			octoprintAPIVersion['api']=decodedData['api']
			octoprintAPIVersion['server']=decodedData['server']
			app_log.debug("Octoprint API Versions: API(" + octoprintAPIVersion['api'] + ") Server("+octoprintAPIVersion['server']+")")
		except:
			app_log.debug("Exceptiong determining API version" + str(sys.exc_info()[0]))
			app_log.debug("API Key used: " + octoprint_api_key)
			octoprintAPIVersion['api']='9999'
	else:
		app_log.debug("OctoPrint is not up yet")
		updateBotStatus(2,'OctoPrint is not up yet')

##This function might not be needed.  Keeping it here as a placeholder for now.
def isPrinterOnline():
	headers={'Authorization':api_key}
	try:
		r=requests.get('http://localhost:5000/' + 'api/job',headers=headers)
		if(decodedData['state']=='Offline'):
			updateBotStatus(3,'Printer is offline for octoprint')
			return False
	except:
		e = sys.exc_info()[0]
		app_log.debug('Exception trying to determine if the printer is online: %s' % e)
		return False
	return True


def printerStatus():
	# data={'status':str(statusCode),'message':message}
	global isPrinting
	headers={'Authorization':api_key}
	try:
		r=requests.get(fabhive_url + 'bots/' + str(workerBeeId) ,headers=headers)
		bot_stats=json.loads(r.text)
		# app_log.debug("bot url: " + fabhive_url + 'bots/' + str(workerBeeId))
		# app_log.debug("bot status: " + r.text)

		headers={'X-Api-Key':octoprint_api_key}
		r=requests.get('http://localhost:5000/' + 'api/job',headers=headers)
		# app_log.debug("job status: " + r.text)
		decodedData=json.loads(r.text)

		if(decodedData['state']=='Offline'):
			updateBotStatus(3,'Printer is offline for octoprint')
			return 'offline'
		if ( decodedData['state'] == 'Operational' and bot_stats['status']==0):
			isPrinting=False
			return 'idle'
		if ( decodedData['state'] == 'Operational' and bot_stats['status']==1):
			isPrinting=False
			return 'printing complete'
		if ( decodedData['state'] == 'Printing' and bot_stats['status']!=0):
			return 'printing'
		if(decodedData['state'] == 'Printing' and bot_stats['status']==0):
			updateBotStatus(statusCode=1,message='Connected to the hive.')
			return 'printing'
		if ( decodedData['state'] == 'Closed' or bot_stats['status']!=0):
			return 'offline'
		return 'other'
	except:
		e = sys.exc_info()[0]
		app_log.debug('Exceptiong determining printer status:  %s' % e)
		app_log.debug("API Version: " + str(getOctoprintAPIVersion()))
		if(octoprintAPIVersion['api']=='9999'):
			app_log.debug("Bad API key for OctoPrint")
			updateBotStatus(3,'Bad API key for OctoPrint')
			return 'offline'
		else:
			return 'other'


def getPrintingStatus():
	global isPrinting
	headers={'X-Api-Key':octoprint_api_key}
	r=requests.get('http://localhost:5000/' + 'api/job',headers=headers)
	decodedData=json.loads(r.text)
	global printingStatus
	if ( decodedData['state'] == 'Printing'):
		printingStatus['percentComplete']=decodedData['progress']['completion']
		printingStatus['timeLeft']=decodedData['progress']['printTimeLeft']
		printingStatus['fileName']=decodedData['job']['file']['name']
		isPrinting=True
	else:
		printingStatus['percentComplete']=decodedData['progress']['completion']
		printingStatus['timeLeft']='0'
		printingStatus['fileName']='0'


	r=requests.get('http://localhost:5000/api/printer',headers=headers)
	decodedData=json.loads(r.text)
	try:
		if(vercmp(octoprintAPIVersion['server'],'1.2.2')):
			printingStatus['temperature']=decodedData['temps']['tool0']['actual']
		else:
			printingStatus['temperature']=decodedData['temps']['tool0']['actual']
	except:
			app_log.debug("Error getting temperature: ")
			app_log.debug("r.text")
			app_log.debug("")
			app_log.debug("")
			printingStatus['temperature']=0
	return printingStatus


def printerTemps():
	temps={}
	temps['bed']=0
	temps['hotend']=0

	if octoprint_on():
		app_log.debug("Getting printer temps")
		headers={'X-Api-Key':octoprint_api_key}
		r=requests.get('http://localhost:5000/api/printer',headers=headers)
		# app_log.debug("(" + r.text + ")")
		if(r.text=="Printer is not operational" or octoprintAPIVersion['api']=='9999'):
			return temps

		decodedData=json.loads(r.text)
		if(vercmp(octoprintAPIVersion['server'],'1.2.2')):
			temps['bed']=decodedData['temperature']['bed']['actual']
			temps['hotend']=decodedData['temperature']['tool0']['actual']
		else:
			temps['bed']=decodedData['temps']['bed']['actual']
			temps['hotend']=decodedData['temps']['tool0']['actual']
		app_log.debug("bed: " + str(temps['bed']))
		app_log.debug("hotend: " + str(temps['hotend']))

		if(temps['hotend']>50):
			turnOnRed()
		else:
			turnOffRed()
	return temps

def updateLCD(message,color):
	if (hasLCD):
		lcd.clear()
		lcd.set_color(1.0, 1.0, 0.0)
		lcd.message(message)

def showIP():
	if (hasLCD):
		lcd.clear()
		# lcd.set_color(1.0,1.0,0.0)
		lcd.message("IP:" + [(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1] + "\n")

def showStatus():
	status=printerStatus()

	if (hasLCD):
		lcd.clear()
		lcd.message("Printer Status: \n" + status)

	app_log.debug("Status: " + status)

def runCommand(gcode):
	app_log.debug('Running Command: ' + gcode)
	try:
		time.sleep(5)
		p.default(gcode)
		data={'command':'NULL'}
		headers={'Authorization':api_key}
		r=requests.put(fabhive_url + 'bots/' + str(workerBeeId) + '/command/',data=data,headers=headers)
		app_log.debug("Result: ")
		app_log.debug(r.text)
	except:
	 	e = sys.exc_info()[0]
	 	app_log.debug('Failed to connect to printer: %s' % e)

def markJobTaken(jobID):
	##Make sure job isn't already taken
	try:
		headers={'Authorization':api_key}
		r=requests.get(fabhive_url + 'jobs/' + str(jobID),headers=headers)
	except:
		return False

	decodedData=json.loads(r.text)
	if( decodedData['error']==True or decodedData['status']!=0):
		return False
	else:
		headers={'Authorization':api_key}
		data={'status':'1','bot':workerBeeId}
		try:
			r=requests.put(fabhive_url + 'jobs/' + str(jobID),data=data,headers=headers)
			decodedData=json.loads(r.text)
			if(decodedData['error']==False):
				app_log.debug("Mark Job Taken: " + r.text)
				return True
		except:
			return False

def markJobCompleted(jobID):
	app_log.debug("Marki Job Complete function for job id: " + str(jobID))
	if(jobID>0):
		headers={'Authorization':api_key}
		data={'status':'2','bot':workerBeeId}
		try:
			file = open('webcam.jpg','wb')
			file.write(urllib.urlopen("http://127.0.0.1:8080/?action=snapshot").read())
			file.close
			app_log.debug("Saved Image")
			im=Image.open('webcam.jpg')
			app_log.debug("Opened Image")
			if shouldFlipCamera:
				rotateImaged=im.rotate(180)
				app_log.debug("Rotated Image")
				rotateImaged.save('webcam-flipped.jpg')
				app_log.debug("Saved Rotated Image")
				file=open('webcam-flipped.jpg','r')
			else:
				file=open('webcam.jpg','r')

			files={'file':('webcam.jpg',file)}
		except:
			app_log.debug("Failed to get image of completed job: " + str(sys.exc_info()[0]))

		try:
			if 'files' in locals():
				app_log.debug("Posting Job Complete w/ Image: " + str(jobID))
				r=requests.post(fabhive_url + 'jobs/' + str(jobID),data=data,headers=headers,files=files)

			else:
				app_log.debug("Putting Job Complete w/out image: " + str(jobID))
				r=requests.put(fabhive_url + 'jobs/' + str(jobID),data=data,headers=headers)
			decodedData=json.loads(r.text)
			if(decodedData['error']==False):
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
		r=requests.get(job['gcodePath'],stream=True)
		with open(job['gcodePath'].split('/')[-1], 'wb') as f:
			for chunk in r.iter_content(chunk_size=1024):
				if chunk: # filter out keep-alive new chunks
					f.write(chunk)
					f.flush()

		app_log.debug("Sending file to octoprint: " + job['gcodePath'])

		datagen, headers = multipart_encode({"file": open(job['gcodePath'].split('/')[-1], "rb")})
		headers['X-Api-Key']=octoprint_api_key
		request = urllib2.Request("http://localhost:5000/api/files/local", datagen, headers)
		# Actually do the request, and get the response
		postResponse=urllib2.urlopen(request).read()
		app_log.debug("Post to octoprint response: " + str(postResponse))

		# files = {job['gcodePath']: open(job['gcodePath'].split('/')[-1], 'rb')}
		# r=requests.post( 'http://localhost:5000/api/files/local', headers=headers,files=files)
		# app_log.debug("Sent file to octoprint: " + r.text)
		# print "Response: " + str(r)
		# print "Response Text: " + str(r.text)
		decodedData=json.loads(postResponse)
		if( decodedData['done']==True):
			os.remove(job['gcodePath'].split('/')[-1])
			return True
		else:
			return False
	except urllib2.URLError as e:
		print e.code
		print e.reason
		app_log.debug("Exception sending file to octoprint: "  + str(sys.exc_info()[0]) )
		return False

def cancelPrint():
	app_log.debug("Getting printer temps")
	headers={'X-Api-Key':octoprint_api_key,'Content-Type':'application/json'}
	data={'command':'cancel'}
	r=requests.post('http://localhost:5000/api/job',headers=headers,data=json.dumps(data))
	app_log.debug("(" + r.text + ")")
	app_log.debug("Homing Axis")
	headers={'X-Api-Key':octoprint_api_key,'Content-Type':'application/json'}
	data={'command':'home', "axes":["x","y"]}
	r=requests.post('http://localhost:5000/api/printer/printhead',headers=headers,data=json.dumps(data))
	app_log.debug("(" + r.text + ")")


def octoprintFile(job):
	fileName=job['gcodePath'].split('/')[-1]
	headers={'X-Api-Key':octoprint_api_key,'Content-Type':'application/json'}
	# data={"command":"select"}
	data={"command":"select","print":"true"}
	# print "filename: " + fileName
	# print "Data: " + str(data)
	r=requests.post( 'http://localhost:5000/api/files/local/' + fileName, headers=headers, data=json.dumps(data))
	# print "Response: " + str(r.status_code)
	if(r.status_code==204):
		app_log.debug("Success")
		return True
	else:
		app_log.debug("Failed to print: " + str(r) + r.text)
		return False

def readyButtonPressed():
	updateBotStatus(statusCode=0,message='Ready Button Pressed')

def updateBotStatus(statusCode=99,message='',temp=0,diskSpace=0):
	app_log.debug("Updating printer status: " + message)
	if(temp==0):
		app_log.debug("temp is 0")
		temps=printerTemps()
		temp=temps['hotend']
		app_log.debug("Temp Now: ")
		app_log.debug(temp)
	if diskSpace==0:
		diskSpace=freeSpace()
	app_log.debug("Updating printer status temp: " + str(temp))
	app_log.debug("Updating printer status diskSpace: " + str(diskSpace))
	if statusCode==99:
		data={'message':message,'temp':temp,'diskSpace':diskSpace}
		app_log.debug("Sending Data: ")
		app_log.debug(data)
		headers={'Authorization':api_key}
		try:
			r=requests.put(fabhive_url + 'bots/' + str(workerBeeId) + '/message',data=data,headers=headers)
		except:
			app_log.debug("Could not update bot status. Network Issue.")
	else:
		data={'status':str(statusCode),'message':message,'temp':temp,'diskSpace':diskSpace}
		app_log.debug("Sending Data: ")
		app_log.debug(data)
		headers={'Authorization':api_key}
		try:
			r=requests.put(fabhive_url + 'bots/' + str(workerBeeId),data=data,headers=headers)
		except:
			app_log.debug("Could not update bot status. Network Issue.")
		# print "response: " + r.text

#Twisted Implementation
class HiveClient(Protocol):
	def __init__(self, factory):
		self.factory = factory
		self.hasConnected=False
		self.checkInRepeater = LoopingCall(self.checkBotIn)

	def connectionMade(self):
		data={'type':'connect','bot':workerBeeId}
		self.transport.write(json.dumps(data))

		updateBotStatus(statusCode=1,message='Connected to the hive.')
		try:
			torHostname=file_get_contents(torHostnameFile).rstrip('\n')
			app_log.debug("Tor Hostname: " + torHostname)
		except:
			app_log.debug("Could not tor hostname.")

		data={'hostname':torHostname}
		headers={'Authorization':api_key}
		try:
		  r=requests.put(fabhive_url + 'bots/' + str(workerBeeId) + '/hostname',data=data,headers=headers)
		except:
		  app_log.debug("Could not update bot status. Network Issue.")

		##Check In to FabHive every minute
		self.checkInRepeater.start(1 * MINUTES)

		self.hasConnected=True

	def dataReceived(self, data):
		global currentJobId
		app_log.debug( "> Received: ''%s''\n" % (data))
		messages=data.split('\n')

		for message in messages:
			app_log.debug("messages: " + message)
			decodedData=json.loads(message)
			if(decodedData['type']=='job'):
				app_log.debug("received a new job")
				updateBotStatus(statusCode=1,message='Received job: ' + decodedData['filename'])
				if(addJobToOctoprint(decodedData)==True):
					app_log.debug("This worked, mark the file as taken")
					result=markJobTaken(decodedData['id'])
					if(result==True):
						updateBotStatus(statusCode=1,message='Printing: ' + decodedData['filename'])
						currentJobId=decodedData['id']
						result=octoprintFile(decodedData)
					else:
						updateBotStatus(statusCode=0,message='Job was already taken')
						currentJobId=0
				else:
					updateBotStatus(statusCode=0,message='Job failed to load on Octoprint')
					currentJobId=0


	def stopAllTimers(self):
		app_log.debug("Stopping all timers")
		self.checkInRepeater.stop


	def checkBotIn(self):
		global printingStatus
		global isPrinting
		global currentJobId
		if(self.hasConnected):
			showStatus()
			app_log.debug("I should check in now. Queen Bee might be worried about me.")

			data={'type':'checkIn','bot':workerBeeId}
			self.transport.write(json.dumps(data) + '\n')

			status=printerStatus()

			app_log.debug("Status: " + status)
			app_log.debug("isPrinting: " + str(isPrinting))

			if(status=="printing complete"):
				printStatus=getPrintingStatus()
				diskUsed=freeSpace()
				updateBotStatus(statusCode=99,message='Checked In',temp=printStatus['temperature'],diskSpace=diskUsed)
				if(currentJobId>0):
					if(printingStatus['percentComplete']==100):
						while True:
							app_log.debug("Marking job complete")
							result=markJobCompleted(currentJobId)
							app_log.debug("Marking job complete: " + str(result))
							if(result):
								app_log.debug("Job marked complete")
								break
						currentJobId=0

			if(status=="printing"):
				app_log.debug("I'm printing")
				printStatus=getPrintingStatus()
				diskUsed=freeSpace()
				updateBotStatus(statusCode=1,message='Printing: ' + printStatus['fileName'] + '<BR/>Percent Complete: ' + str(math.ceil(printStatus['percentComplete'])),temp=printStatus['temperature'],diskSpace=diskUsed)

		 	if(status=="idle" and isPrinting==False):
				app_log.debug("Requesting job")
				self.requestJob()

		else:
			app_log.debug("We haven't connected yet. No need to check in yet.")

	def requestJob(self):
		if(self.hasConnected):
			data={'type':'jobRequest','bot':workerBeeId}
			self.transport.write(json.dumps(data))
		else:
			app_log.debug("We haven't connected yet.")


class WorkerBee(object):
	def __init__(self):
		updateBotStatus(statusCode=1,message='Printer is online.')
		if (hasLCD):
			lcd.set_color(0.0, 1.0, 0.0)
			lcd.clear()
			lcd.message('Connected.')




class HiveFactory(ReconnectingClientFactory):
	def __init__(self):
		self.protocol=HiveClient(self)
		self.workerBee=WorkerBee()

		##Check temp every 15 seconds for LED
		self.checkTempRepeater = LoopingCall(self.checkPrinterTemp)
		self.checkTempRepeater.start(1*15,True)

		##Check for new config file every 30 seconds
		self.configFileRepeater=LoopingCall(checkConfigFile)
		self.configFileRepeater.start(1*30,True)

		##Check cancel and ready buttons every 3 seconds
		self.buttonCheckRepeater=LoopingCall(buttonChecker)
		self.buttonCheckRepeater.start(1*3,True)

	def startedConnecting(self, connector):
		app_log.debug('Started to connect.')


	def buildProtocol(self, addr):
		app_log.debug('Connected.')
		app_log.debug('Resetting reconnection delay')
		self.resetDelay()
		return HiveClient(self)

	def clientConnectionLost(self, connector, reason):
		app_log.debug('Lost connection.  Reason:' + str(reason))
		self.protocol.stopAllTimers();
		ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

	def clientConnectionFailed(self, connector, reason):
		app_log.debug('Connection failed. Reason:' + str(reason))
		self.protocol.stopAllTimers();
		ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

	def checkPrinterTemp(self):
		# extruderTemp=self.workerBee.pronsole.status.extruder_temp
		if hasFHBoard:
			temps=printerTemps()
			if(temps['hotend']>40):
				turnOnRed()
			else:
				turnOffRed()
		if (hasLCD):
			temps=printerTemps()
			if(temps['hotend']>40):
				lcd.set_color(1.0,0.0,0.0)
			else:
				lcd.set_color(0.0,0.0,1.0)

			lcd.clear()
			lcd.message("E Temp:" + str(temps['hotend']) + "\n")
			lcd.message("B Temp:" + str(temps['bed']) + "\n")

getOctoprintAPIVersion()
reactor.connectTCP("fabhive.buzz", 5005, HiveFactory())

# reactor.callWhenRunning(WorkerBee())
reactor.run()
