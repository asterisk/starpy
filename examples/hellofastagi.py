#! /usr/bin/env python
"""Simple FastAGI server using starpy"""
from twisted.internet import reactor
from starpy import fastagi
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
	f = fastagi.FastAGIFactory(testFunction)
	reactor.listenTCP(4573, f, 50, '127.0.0.1') # only binding on local interface
	reactor.run()
