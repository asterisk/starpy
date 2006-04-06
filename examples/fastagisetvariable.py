#! /usr/bin/env python
"""Try to set a FastAGI variable"""
from twisted.internet import reactor
from starpy import fastagi, utilapplication
import logging, time

log = logging.getLogger( 'hellofastagi' )

def testFunction( agi ):
	"""Demonstrate simplistic use of the AGI interface with sequence of actions"""
	log.debug( 'testFunction' )
	def setX( ):
		return agi.setVariable( 'this"toset', 'That"2set' )
	def getX( result ):
		return agi.getVariable( 'this"toset' )
	def onX( value ):
		print 'Retrieved value', value 
		reactor.stop()
	return setX().addCallback( getX ).addCallbacks( onX, onX )

if __name__ == "__main__":
	logging.basicConfig()
	fastagi.log.setLevel( logging.DEBUG )
	APPLICATION = utilapplication.UtilApplication()
	APPLICATION.handleCallsFor( 's', testFunction )
	APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
	reactor.run()
