#!/bin/bash
logger "In the Workerbee Start Script"
cd /home/pi/workerbee
sleep 30s
sudo /usr/bin/python ./workerBee.py
