#!/usr/bin/python

import KatanaConfig
import subprocess
import sys
import time
import os
import logging
import requests, json
import boto
from boto.s3.key import Key
from boto.s3.connection import S3Connection
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

if (KatanaConfig.hasLCD()):
	import Adafruit_CharLCD as LCD
	# Initialize the LCD using the pins
	lcd = LCD.Adafruit_CharLCDPlate()
	lcd.set_color(1.0, 1.0, 0.0)
	lcd.clear()
	lcd.message('Starting...')
	time.sleep(3.0)



# s3Path="http://kabar-files.s3.amazonaws.com/"

MINUTES = 60.0


requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

queue_id=KatanaConfig.queue_id()
myPrinterId=KatanaConfig.myPrinterId()

printerPort=KatanaConfig.printerPort()
webcam_command=KatanaConfig.WEBCAM_CAPTURE()

loud = True
statusreport = True

# conn = S3Connection(KatanaConfig.AWS_KEY(),KatanaConfig.AWS_SECRET())
# bucket=conn.get_bucket(KatanaConfig.bucket_name())

katana_url=KatanaConfig.KATANA_URL()
api_key=KatanaConfig.KATANA_KEY()
octoprint_api_key=KatanaConfig.OCTOPRINT_API_KEY()

isPrinting=True

lastCameraCapture=0

lastCheckIn=0

def printerStatus():
	# data={'status':str(statusCode),'message':message}
	headers={'Authorization':api_key}
	try:
		r=requests.get(katana_url + 'bots/' + str(myPrinterId) ,headers=headers)
		bot_stats=json.loads(r.text)

		headers={'X-Api-Key':octoprint_api_key}
		r=requests.get('http://localhost:5000/' + 'api/job',headers=headers)
		decodedData=json.loads(r.text)
		if ( decodedData['state'] == 'Operational' and bot_stats['status']==0):
			return 'idle'
		if ( decodedData['state'] == 'Printing' and bot_stats['status']!=0):
			return 'printing'
		if ( decodedData['state'] == 'Closed' or bot_stats['status']!=0):
			return 'offline'
		return 'other'
	except:
		return 'other'


def getPrintingStatus():
	headers={'X-Api-Key':octoprint_api_key}
	r=requests.get('http://localhost:5000/' + 'api/job',headers=headers)
	decodedData=json.loads(r.text)
	printingStatus={}
	if ( decodedData['state'] == 'Printing'):
		printingStatus['percentComplete']=decodedData['progress']['completion']
		printingStatus['timeLeft']=decodedData['progress']['printTimeLeft']
		printingStatus['fileName']=decodedData['job']['file']['name']
		isPrinting=True
	else:
		printingStatus['percentComplete']='100'
		printingStatus['timeLeft']='0'
		printingStatus['fileName']='0'
	return printingStatus


def printerTemps():
	headers={'X-Api-Key':octoprint_api_key}
	r=requests.get('http://localhost:5000/' + 'api/printer',headers=headers)
	decodedData=json.loads(r.text)
	temps={}
	temps['bed']=decodedData['temps']['bed']['actual']
	temps['hotend']=decodedData['temps']['tool0']['actual']
	print "bed: " + str(temps['bed'])
	print "hotend: " + str(temps['hotend'])
	return temps

def updateLCD(message,color):
	if (KatanaConfig.hasLCD()):
		lcd.clear()
		lcd.set_color(1.0, 1.0, 0.0)
		lcd.message(message)

def showIP():
	if (KatanaConfig.hasLCD()):
		lcd.clear()
		# lcd.set_color(1.0,1.0,0.0)
		lcd.message("IP:" + [(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1] + "\n")

def showStatus():
	status=printerStatus()

	if (KatanaConfig.hasLCD()):
		lcd.clear()
		lcd.message("Printer Status: \n" + status)

	print "Status: " + status


# def checkBotStatus():
# 	lastCheckIn=datetime.now()
# 	headers={'Authorization':api_key}
# 	r=requests.get(katana_url + 'bots/' + str(myPrinterId) ,headers=headers)
# 	# print "response: " + r.text
# 	bot_stats=json.loads(r.text)
# 	if not((bot_stats['pendingCommand'] == 'NULL') or (bot_stats['pendingCommand'] is None) or (len(bot_stats['pendingCommand'])==0)):
# 		runCommand(bot_stats['pendingCommand'])
#
# 	headers={'Authorization':api_key}
# 	r=requests.put(katana_url + 'bots/' + str(myPrinterId) + '/checkin',headers=headers)
#
# 	tryCaptureImage()
# 	return bot_stats

def runCommand(gcode):
	print 'Running Command: ' + gcode
	try:
		time.sleep(5)
		p.default(gcode)
		data={'command':'NULL'}
		headers={'Authorization':api_key}
		r=requests.put(katana_url + 'bots/' + str(myPrinterId) + '/command/',data=data,headers=headers)
		print "Result: "
		print r.text
	except:
	 	e = sys.exc_info()[0]
	 	print 'Failed to connect to printer: %s' % e

def markJobTaken(jobID):
	##Make sure job isn't already taken
	try:
		headers={'Authorization':api_key}
		r=requests.get(katana_url + 'jobs/' + str(jobID),headers=headers)
	except:
		return False

	decodedData=json.loads(r.text)
	if( decodedData['error']==True or decodedData['status']!=0):
		return False
	else:
		headers={'Authorization':api_key}
		data={'status':'1','bot':myPrinterId}
		r=requests.put(katana_url + 'jobs/' + str(jobID),data=data,headers=headers)
		decodedData=json.loads(r.text)
		if(decodedData['error']==False):
			print "Mark Job Taken: " + r.text
			return True


def addJobToOctoprint(job):
	##Download file
	print "Downloading file: " + job['gcodePath']
	try:
		r=requests.get(job['gcodePath'],stream=True)
		with open(job['gcodePath'].split('/')[-1], 'wb') as f:
			for chunk in r.iter_content(chunk_size=1024):
				if chunk: # filter out keep-alive new chunks
					f.write(chunk)
					f.flush()

		print "Sending file to octoprint: " + job['gcodePath']

		headers={'X-Api-Key':octoprint_api_key}
		files = {'file': open(job['gcodePath'].split('/')[-1], 'r')}
		r=requests.post( 'http://localhost:5000/api/files/local', headers=headers,files=files)
		# print "Response: " + str(r)
		# print "Response Text: " + str(r.text)
		decodedData=json.loads(r.text)
		if( decodedData['done']==True):
			os.remove(job['gcodePath'].split('/')[-1])
			return True
		else:
			return False
	except:
		return False

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
		print "Success"
		return True
	else:
		print "Failed to print: " + str(r) + r.text
		return False

def updateBotStatus(statusCode=99,message=''):
	if statusCode==99:
		data={'message':message}
		headers={'Authorization':api_key}
		try:
			r=requests.put(katana_url + 'bots/' + str(myPrinterId) + '/message',data=data,headers=headers)
		except:
			print "Could not update bot status. Network Issue."
	else:
		data={'status':str(statusCode),'message':message}
		headers={'Authorization':api_key}
		try:
			r=requests.put(katana_url + 'bots/' + str(myPrinterId),data=data,headers=headers)
		except:
			print "Could not update bot status. Network Issue."
		# print "response: " + r.text

#Twisted Implementation
class HiveClient(Protocol):
	def __init__(self, factory):
		self.factory = factory
		self.hasConnected=False
		self.checkInRepeater = LoopingCall(self.checkBotIn)

	def connectionMade(self):
		data={'type':'connect','bot':myPrinterId}
		self.transport.write(json.dumps(data))

		updateBotStatus(statusCode=1,message='Connected to the hive.')

		self.checkInRepeater.start(1 * MINUTES)
		self.hasConnected=True

	def dataReceived(self, data):
		print "> Received: ''%s''\n" % (data)
		messages=data.split('\n')

		for message in messages:
			print "messages: " + message
			decodedData=json.loads(message)
			if(decodedData['type']=='job'):
				print "received a new job"
				updateBotStatus(statusCode=1,message='Received job: ' + decodedData['filename'])
				if(addJobToOctoprint(decodedData)==True):
					print "This worked, mark the file as taken"
					result=markJobTaken(decodedData['id'])
					if(result==True):
						updateBotStatus(statusCode=1,message='Printing: ' + decodedData['filename'])
						result=octoprintFile(decodedData)
					else:
						updateBotStatus(statusCode=0,message='Job was already taken')
				else:
					updateBotStatus(statusCode=0,message='Job was already taken')
						# POST /api/files/local/whistle_v2.gcode HTTP/1.1
						# Host: example.com
						# Content-Type: application/json
						# X-Api-Key: abcdef...
						#
						# {
						#   "command": "select",
						#   "print": true
						# }

					# data={'type':'takeJob','jobID':decodedData['id'], 'botID':myPrinterId}
					# self.transport.write(json.dumps(data))

			# 	print "Bzzz....The hive welcomes " + str(decodedData['bot']) + " bot to the hive."
			# 	self.handle_REGISTER(decodedData['bot'])

	def stopAllTimers(self):
		print "Stopping all timers"
		self.checkInRepeater.stop

	def checkBotIn(self):
		if(self.hasConnected):
			showStatus()
			print "I should check in now. Queen Bee might be worried about me."
			data={'type':'checkIn','bot':myPrinterId}
			self.transport.write(json.dumps(data) + '\n')

			status=printerStatus()

			if(status=="printing"):
				printStatus=getPrintingStatus()
				updateBotStatus(statusCode=1,message='Printing: ' + printStatus['fileName'] + '<BR/>Percent Complete: ' + str(math.ceil(printStatus['percentComplete'])))

		 	if(status=="idle" and isPrinting=False):
				self.requestJob()

		else:
			print "We haven't connected yet. No need to check in yet."

	def requestJob(self):
		if(self.hasConnected):
			data={'type':'jobRequest','bot':myPrinterId}
			self.transport.write(json.dumps(data))
		else:
			print "We haven't connected yet."


class WorkerBee(object):
	def __init__(self):

		# self.pronsole=pronsole()
		# lcd.set_color(1.0, 1.0, 0.0)
		# lcd.clear()
		# lcd.message('Connecting to \nprinter...')
		# try:
		# 	self.pronsole.connect_to_printer(printerPort, 250000)
		# 	time.sleep(2)
		# except:
		# 	print 'Failed to connect to printer: ', sys.exc_info()[0]
		# 	updateBotStatus(statusCode=3,message='Could not connect to printer')
		# 	raise

		updateBotStatus(statusCode=1,message='Waiting for printer to come online.')
		# while not self.pronsole.online:
		# 	print "waiting for printer to come online"
		# 	time.sleep(5)
		updateBotStatus(statusCode=1,message='Printer is online.')
		if (KatanaConfig.hasLCD()):
			lcd.set_color(0.0, 1.0, 0.0)
			lcd.clear()
			lcd.message('Connected.')

	# def printerStatus(self):
	# 	# data={'status':str(statusCode),'message':message}
	# 	headers={'X-Api-Key':octoprint_api_key}
	# 	r=requests.get('http://localhost/' + 'api/job',headers=headers)
	# 	decodedData=json.loads(r.text)
	# 	if ( decodedData['state'] == 'Operational'):
	# 		return 'idle'
	# 	if ( decodedData['state'] == 'Printing'):
	# 		return 'printing'
	# 	if ( decodedData['state'] == 'Closed'):
	# 		return 'offline'
	#
	# 	return 'other'




class HiveFactory(ReconnectingClientFactory):
	def __init__(self):
		self.protocol=HiveClient(self)
		self.checkTempRepeater = LoopingCall(self.checkPrinterTemp)
		self.workerBee=WorkerBee()
		self.checkTempRepeater.start(1*15)

	def startedConnecting(self, connector):
		print 'Started to connect.'


	def buildProtocol(self, addr):
		print 'Connected.'
		print 'Resetting reconnection delay'
		self.resetDelay()
		return HiveClient(self)

	def clientConnectionLost(self, connector, reason):
		print 'Lost connection.  Reason:', reason
		self.protocol.stopAllTimers();
		ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

	def clientConnectionFailed(self, connector, reason):
		print 'Connection failed. Reason:', reason
		self.protocol.stopAllTimers();
		ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

	def checkPrinterTemp(self):
		# extruderTemp=self.workerBee.pronsole.status.extruder_temp
		if (KatanaConfig.hasLCD()):
			temps=printerTemps()
			if(temps['hotend']>40):
				lcd.set_color(1.0,0.0,0.0)
			else:
				lcd.set_color(0.0,0.0,1.0)

			lcd.clear()
			lcd.message("E Temp:" + str(temps['hotend']) + "\n")
			lcd.message("B Temp:" + str(temps['bed']) + "\n")

	# def checkInTimer(self):
	# 	if(self.hasConnected):
	# 		print "I should check in now. Queen Bee might be worried about me."
	# 		self.protocol.checkBotIn
	# 	else:
	# 		print "We haven't connected yet. No need to check in yet."


reactor.connectTCP("fabhive.buzz", 5005, HiveFactory())

# reactor.callWhenRunning(WorkerBee())
reactor.run()

#
# while 1:
# 	checkWithServer=False
# 	if(lastCheckIn==0):
# 		checkWithServer=True
# 	else:
# 		delta=datetime.now() - lastCheckIn
# 		if(delta.seconds>30):
# 			print "Last check in was " + str(delta.seconds) + " ago"
# 			checkWithServer=True
#
# 	if(not checkWithServer):
# 		print "continue"
# 		continue
#
# 	print "checkWithServer: " + str(checkWithServer)
#
# 	#check printer status
# 	bot_stats=checkBotStatus()
# 	if bot_stats['status']==0:
# 		isPrinting=False
# 	else:
# 		isPrinting=True
# 		print "Not ready for a new job yet."
# 		bot_stats_checkAgain=checkBotStatus()
# 		while(not bot_stats_checkAgain['status']==0):
# 			updateBotStatus(message='Temp: ' + str(p.status.extruder_temp)+'')
# 			bot_stats_checkAgain=checkBotStatus()
# 		print "Now I'm ready"
#
# 	if not isPrinting:
# 		#download next job for this queue
# 		headers={'Authorization':api_key}
# 		r=requests.get(katana_url + '/queues/' + str(queue_id) +'/next',headers=headers)
# 		result=json.loads(r.text)
# 		if(result['error']==False):
# 			print 'Got Next Job: ' + result['filename']
#
# 			updateBotStatus(statusCode=0,message='Downloading file: ' + result['filename'])
#
# 			#k = Key(bucket)
# 			#k.key = result['filename']
# 			#k.get_contents_to_filename(result['filename'])
#
# 			testfile=urllib.URLopener()
# 			print "Getting: " + s3Path + result['filename'] + '.gcode'
# 			testfile.retrieve(s3Path + result['filename'] + '.gcode',result['filename'] + '.gcode')
#
# 			#check job is still not taken
# 			headers={'Authorization':api_key}
# 			r=requests.get(katana_url + 'jobs/' + str(result['id']),headers=headers)
# 			checkResult=json.loads(r.text)
# 			if(checkResult['status']==0):
# 				#mark job as pending
# 				data={'status':'1','bot':myPrinterId}
# 				headers={'Authorization':api_key}
# 				r=requests.put(katana_url + 'jobs/' + str(result['id']),data=data,headers=headers)
#
#
# 				updateBotStatus(statusCode=1,message='Printing file: ' + result['filename'])
#
# 				isPrinting=True
#
# 				p.load_gcode(result['filename'] + '.gcode')
#
#
# 				try:
# 					p.do_print(p)
# 					try:
# 						while p.p.printing:
# 							progress = 100 * float(p.p.queueindex) / len(p.p.mainqueue)
# 							print "Updating print bot status: "	+ ' (Temp: ' + str(p.status.extruder_temp) + ', Percent Complete: ' + str(progress) + ')'
# 							tryCaptureImage()
# 							updateBotStatus(message='Printing: ' + result['filename'] + ' (Temp: ' + str(p.status.extruder_temp) + ', Percent Complete: %.2f)' % progress)
# 							time.sleep(5)
#
# 						#isPrinting=True
# 						print "Updating print status"
# 						data={'status':'3','bot':myPrinterId}
# 						headers={'Authorization':api_key}
# 						r=requests.put(katana_url + 'jobs/' + str(result['id']),data=data,headers=headers)
# 						captureImage
# 						updateBotStatus(message='Finished printing: ' + result['filename'] )
# 						print "Result: "
# 						print r.text
# 					except:
# 						data={'status':'0','bot':myPrinterId}
# 						headers={'Authorization':api_key}
# 						r=requests.put(katana_url + 'jobs/' + str(result['id']),data=data,headers=headers)
# 						p.disconnect()
#
# 						updateBotStatus(statusCode=1,message='Failed to print: ' + result['filename'])
#
# 					updateBotStatus(statusCode=1,message='Completed print: ' + result['filename'])
#
#
# 				except:
# 					data={'status':'0','bot':myPrinterId}
# 					headers={'Authorization':api_key}
# 					r=requests.put(katana_url + 'jobs/' + str(result['id']),data=data,headers=headers)
# 					isPrinting=False
#
# 	tryCaptureImage()
