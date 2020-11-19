from tkinter import *
from tkinter import messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	DESCRIBE = 5
	STOP = 6
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
		self.receivedPacketNum = 0
		self.displayedPacketNum = 0
		self.receivedPacketTotalSize = 0
		self.displayedPacketTotalSize = 0
		self.playTime = 0
		self.previousTimeStamp = -1
		
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		###########################################
		# Create Fast Play button		
		self.fplay = Button(self.master, width=20, padx=3, pady=3)
		self.fplay["text"] = "Fast Play"
		self.fplay["command"] = self.setupAndPlay
		self.fplay.grid(row=2, column=1, padx=2, pady=2)
		
		# Create Stop button
		self.stop = Button(self.master, width=20, padx=3, pady=3)
		self.stop["text"] = "Stop"
		self.stop["command"] =  self.stopMovie
		self.stop.grid(row=2, column=3, padx=2, pady=2)

		#########################################
		# Create Describe button
		self.describe = Button(self.master, width=20, padx=3, pady=3)
		self.describe["text"] = "Describe"
		self.describe["command"] = self.describeMovie
		self.describe.grid(row=1, column=4, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=3, sticky=W+E+N+S, padx=5, pady=5) 

		# info display
		self.info = StringVar()
		self.infolabel = Label(self.master, textvariable=self.info)
		self.infolabel.grid(row=0, column=3, columnspan=2, sticky=W+E+N, padx=5, pady=5)
		self.info.set("Statistic not avaiable.")
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
		
	#####################################
	# fast play
	def setupAndPlay(self):
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
		elif self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
			
			for i in range(5):
				if self.state == self.READY:
					break
				time.sleep(0.1)
			
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
			
	# stop
	def stopMovie(self):
		"""Stop button handler."""
		if self.state != self.INIT and self.frameNbr != 0:
			if self.state == self.PLAYING:
				self.sendRtspRequest(self.PAUSE)
				for i in range(50):
					if self.state == self.READY:
						break
					time.sleep(0.01)
				
			self.frameNbr = 0
			self.receivedPacketNum = 0
			self.displayedPacketNum = 0
			self.receivedPacketTotalSize = 0
			self.displayedPacketTotalSize = 0
			self.playTime = 0
			self.previousTimeStamp = -1
			
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.STOP)
			
			for i in range(50):
				if self.state == self.PLAYING:
					break
				time.sleep(0.01)
			
			self.pauseMovie()
	
	#################################
	# describe
	def describeMovie(self):
		"""Describe button handler."""
		self.sendRtspRequest(self.DESCRIBE)

	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					# Update received packet
					packetSize = len(data)
					self.receivedPacketNum = self.receivedPacketNum + 1
					self.receivedPacketTotalSize = self.receivedPacketTotalSize + packetSize
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))
										
					if currFrameNbr > self.frameNbr: # Discard the late packet
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
						# Update displayed packet
						self.displayedPacketNum = self.displayedPacketNum + 1
						self.displayedPacketTotalSize = self.displayedPacketTotalSize + packetSize

					self.showStats()
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					#self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			# Update RTSP sequence number.
			# ...
			self.rtspSeq = self.rtspSeq + 1
			# Write the RTSP request to be sent.
			# request = ...
			request = 'SETUP ' + str(self.fileName) + ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nTransport: RTP/UDP; client_port= ' + str(self.rtpPort)
			# Keep track of the sent request.
			# self.requestSent = ...
			self.requestSent = self.SETUP
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			# ...
			self.rtspSeq = self.rtspSeq + 1
			# Write the RTSP request to be sent.
			# request = ...
			request = 'PLAY ' + str(self.fileName)  +  ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
			# Keep track of the sent request.
			# self.requestSent = ...
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			# ...
			self.rtspSeq = self.rtspSeq + 1
			# Write the RTSP request to be sent.
			# request = ...
			request = 'PAUSE ' + str(self.fileName) + ' RTSP/1.0\nCseq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
			# Keep track of the sent request.
			# self.requestSent = ...
			self.requestSent = self.PAUSE
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			# ...
			self.rtspSeq = self.rtspSeq + 1
			# Write the RTSP request to be sent.
			# request = ...
			request = 'TEARDOWN ' + str(self.fileName) + ' RTSP/1.0\nCseq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
			# Keep track of the sent request.
			# self.requestSent = ...
			self.requestSent = self.TEARDOWN
			
		###################################
		# stop
		elif requestCode == self.STOP and self.state != self.INIT:
			# Update RTSP sequence number.
			# ...
			self.rtspSeq = self.rtspSeq + 1
			# Write the RTSP request to be sent.
			# request = ...
			request = 'PLAY ' + str(self.fileName)  +  ' RTSP/1.0\nCSeq: ' + str(self.rtspSeq) + '\nRange: npt=0.0-\nSession: ' + str(self.sessionId)
			# Keep track of the sent request.
			# self.requestSent = ...
			self.requestSent = self.PLAY
			
		#######################################
		# Describe request
		elif requestCode == self.DESCRIBE and not self.state == self.INIT:
			# Update RTSP sequence number.
			self.rtspSeq = self.rtspSeq + 1

			# Write the RTSP request to be sent.
			request = 'DESCRIBE ' + str(self.fileName) + ' RTSP/1.0\nCseq: ' + str(self.rtspSeq) + '\nSession: ' + str(self.sessionId)
			# Keep track of the sent request.
			self.requestSent = self.DESCRIBE


		#######################################

		else:
			return
		
		# Send the RTSP request using rtspSocket.
		# ...
		self.rtspSocket.send(request.encode("utf-8"))
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		print("=======================")
		print("Reply received :")
		print(data)
		print("=======================")
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						# Update RTSP state.
						# self.state = ...
						self.state = self.READY
						# Open RTP port.
						self.openRtpPort()
					elif self.requestSent == self.PLAY:
						# self.state = ...
						self.state = self.PLAYING
						# Update timestamp
						self.startTimer()
					elif self.requestSent == self.PAUSE:
						# self.state = ...
						self.state = self.READY
						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()
						# Update playTime and reset timestamp
						self.stopTimer()
						### Adding this line cause error
						### press fastplay, or setup and then play
						### while the movie is playing, press stop
						self.showStats()
					elif self.requestSent == self.TEARDOWN:
						# self.state = ...
						self.state = self.INIT
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1
					################################
					elif self.requestSent == self.DESCRIBE:
						# keep old state
						# print description
						for i in lines[3:]:
							print(i)
						desc = lines[7][2:] + "\n" + lines[8]
						messagebox.showinfo('Description', desc)

	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		# self.rtpSocket = ...
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# Set the timeout value of the socket to 0.5sec
		# ...
		self.rtpSocket.settimeout(0.5)
		try:
			# Bind the socket to the address using the RTP port given by the client user
			# ...
			self.rtpSocket.bind(('',self.rtpPort))
		except:
			messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()

	#Start timer
	def startTimer(self):
		self.previousTimeStamp = time.perf_counter()

	#Stop timer
	def stopTimer(self):
		if self.previousTimeStamp > 0:
			self.playTime = self.playTime + (time.perf_counter() - self.previousTimeStamp)
			self.previousTimeStamp = -1

	#Add playTime
	def addPlayTime(self):
		# Update playTime and reset timestamp
		if self.previousTimeStamp > 0:
			currentTimeStamp = time.perf_counter()
			self.playTime = self.playTime + (currentTimeStamp - self.previousTimeStamp)
			self.previousTimeStamp = currentTimeStamp

	#ShowStats function
	def showStats(self):
		self.addPlayTime()
		totalPacketNum = self.frameNbr
		if totalPacketNum != 0:
			strval = ""
			strval += "\nStatistics :"
			strval += "\nTotal number of packets : %d" % totalPacketNum
			strval += "\nPackets received : %d packets" % self.receivedPacketNum
			strval += "\nPackets displayed : %d packets" % self.displayedPacketNum
			strval += "\nPackets lost : %d packets" % (totalPacketNum - self.displayedPacketNum)
			strval += "\nPackets lost rate : %.2f%%" % ((float) (totalPacketNum - self.displayedPacketNum) / totalPacketNum)
			strval += "\nPlay time : %fs" % self.playTime
			strval += "\nBytes received : %d bytes" % self.receivedPacketTotalSize
			strval += "\nBytes displayed : %d bytes" % self.displayedPacketTotalSize
			strval += "\nVideo data rate : %.0f bits per second" % (self.displayedPacketTotalSize * 8/self.playTime)
			strval += "\nThroughput : %.0f bits per second" % (self.receivedPacketTotalSize * 8 / self.playTime)
			self.info.set(strval)