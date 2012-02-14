#! /usr/bin/env python
"""FastAGI server using starpy and the utility application framework

This is basically identical to hellofastagi, save that it uses the application
framework to allow for configuration-file-based setup of the AGI service.
"""
from twisted.internet import reactor
from starpy import fastagi
import utilapplication
import logging, time

log = logging.getLogger( 'hellofastagi' )

def testFunction( agi ):
	"""Demonstrate simplistic use of the AGI interface with sequence of actions"""
	log.debug( 'testFunction' )
	sequence = fastagi.InSequence()
	sequence.append( agi.sayDateTime, time.time() )
	sequence.append( agi.finish )
	def onFailure( reason ):
		log.error( "Failure: %s", reason.getTraceback())
		agi.finish()
	return sequence().addErrback( onFailure )

if __name__ == "__main__":
	logging.basicConfig()
	fastagi.log.setLevel( logging.DEBUG )
	APPLICATION = utilapplication.UtilApplication()
	APPLICATION.handleCallsFor( 's', testFunction )
	APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
	reactor.run()
