#! /usr/bin/env python
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi
import utilapplication
import menu
import os, logging, pprint, time
from basicproperty import common, propertied, basic

log = logging.getLogger( 'priexhaustion' )
log.setLevel( logging.INFO )

class ChannelTracker( propertied.Propertied ):
	"""Track open channels on the Asterisk server"""
	channels = common.DictionaryProperty(
		"channels", """Set of open channels on the system""",
	)
	thresholdCount = common.IntegerProperty(
		"thresholdCount", """Storage of threshold below which we don't warn user""",
		defaultValue = 20,
	)
	def main( self ):
		"""Main operation for the channel-tracking demo"""
		amiDF = APPLICATION.amiSpecifier.login( 
		).addCallback( self.onAMIConnect )
	def onAMIConnect( self, ami ):
		ami.status().addCallback( self.onStatus, ami=ami )
		ami.registerEvent( 'Hangup', self.onChannelHangup )
		ami.registerEvent( 'Newchannel', self.onChannelNew )
	def onStatus( self, events, ami=None ):
		"""Integrate the current status into our set of channels"""
		log.debug( """Initial channel status retrieved""" )
		for event in events:
			self.onChannelNew( ami, event )
	def onChannelNew( self, ami, event ):
		"""Handle creation of a new channel"""
		log.debug( """Start on channel %s""", event )
		opening = not self.channels.has_key( event['uniqueid'] )
		self.channels[ event['uniqueid'] ] = event 
		if opening:
			self.onChannelChange( ami, event, opening = opening )
	def onChannelHangup( self, ami, event ):
		"""Handle hangup of an existing channel"""
		try:
			del self.channels[ event['uniqueid']]
		except KeyError, err:
			log.warn( """Hangup on unknown channel %s""", event )
		else:
			log.debug( """Hangup on channel %s""", event )
		self.onChannelChange( ami, event, opening = False )
	def onChannelChange( self, ami, event, opening=False ):
		"""Channel count has changed, do something useful like enforcing limits"""
		if opening and len(self.channels) > self.thresholdCount:
			log.warn( """Current channel count: %s""", len(self.channels ) )
		else:
			log.info( """Current channel count: %s""", len(self.channels ) )

APPLICATION = utilapplication.UtilApplication()

if __name__ == "__main__":
	logging.basicConfig()
	tracker = ChannelTracker()
	reactor.callWhenRunning( tracker.main )
	reactor.run()
