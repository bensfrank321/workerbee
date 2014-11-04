def queue_id():
	queue_id=1
	return queue_id

def myPrinterId():	
	myPrinterId=7
	return myPrinterId

def printerPort():
	printerPort='/dev/ttyACM0'
	return printerPort

def KATANA_KEY():
	katana_key="API_KEY_FROM_KATANA"
	return katana_key

def KATANA_URL():
	katana_url="http://URL_FOR_KATANA"
	return katana_url

def AWS_KEY():
	AWS_KEY='AWS_KEY'
	return AWS_KEY

def AWS_SECRET():
	AWS_SECRET='AWS_SECRET'
	return AWS_SECRET

def bucket_name():
	bucket_name='AWS_BUCKET_NAME'
	return bucket_name

def WEBCAM_CAPTURE():
	webcam_capture_command='/usr/bin/raspistill -w 1024 -h 768 -q 60 -o ./pi-' + str(myPrinterId()) + '.jpg '
	return webcam_capture_command
