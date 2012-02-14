#! /usr/bin/env python
"""Sample application to watch for PRI exhaustion

This script watches for events on the AMI interface, tracking the identity of
open channels in order to track how many channels are being used.  This would 
be used to send messages to an administrator when network capacity is being 
approached.

Similarly, you could watch for spare capacity on the network and use that 
to decide whether to allow low-priority calls, such as peering framework or
free-world-dialup calls to go through.
"""
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
		# XXX do something useful on failure to login...
	def onAMIConnect( self, ami ):
		"""Register for AMI events"""
		# XXX should do an initial query to populate channels...
		# XXX should handle asterisk reboots (at the moment the AMI 
		# interface will just stop generating events), not a practical
		# problem at the moment, but should have a periodic check to be sure
		# the interface is still up, and if not, should close and restart
		log.debug( 'onAMIConnect' )
		ami.status().addCallback( self.onStatus, ami=ami )
		ami.registerEvent( 'Hangup', self.onChannelHangup )
		ami.registerEvent( 'Newchannel', self.onChannelNew )
	def interestingEvent( self, event, ami=None ):
		"""Decide whether this channel event is interesting 
		
		Real-world application would want to take only Zap channels, or only
		channels from a given context, or whatever other filter you want in 
		order to capture *just* the scarce resource (such as PRI lines).
		
		Keep in mind that an "interesting" event must show up as interesting 
		for *both* Newchannel and Hangup events or you will leak 
		references/channels or have unknown channels hanging up.
		"""
		return True
	def onStatus( self, events, ami=None ):
		"""Integrate the current status into our set of channels"""
		log.debug( """Initial channel status retrieved""" )
		for event in events:
			self.onChannelNew( ami, event )
	def onChannelNew( self, ami, event ):
		"""Handle creation of a new channel"""
		log.debug( """Start on channel %s""", event )
		if self.interestingEvent( event, ami ):
			opening = not self.channels.has_key( event['uniqueid'] )
			self.channels[ event['uniqueid'] ] = event 
			if opening:
				self.onChannelChange( ami, event, opening = opening )
	def onChannelHangup( self, ami, event ):
		"""Handle hangup of an existing channel"""
		if self.interestingEvent( event, ami ):
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
	#log.setLevel( logging.DEBUG )
	#manager.log.setLevel( logging.DEBUG )
	#fastagi.log.setLevel( logging.DEBUG )
	tracker = ChannelTracker()
	reactor.callWhenRunning( tracker.main )
	reactor.run()
