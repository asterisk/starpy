#! /usr/bin/env python
"""Demonstrate usage of getVariable on the agi interface...
"""
from twisted.internet import reactor
from starpy import fastagi
import utilapplication
import logging, time, pprint

log = logging.getLogger( 'hellofastagi' )

def envVars( agi ):
	"""Print out channel variables for display"""
	vars = [
		x.split( ' -- ' )[0].strip() 
		for x in agi.getVariable.__doc__.splitlines()
		if len(x.split( ' -- ' )) == 2
	]
	for var in vars:
		yield var 

def printVar( result, agi, vars ):
	"""Print out the variables produced by envVars"""
	def doPrint( result, var ):
		print '%r -- %r'%( var, result )
	def notAvailable( reason, var ):
		print '%r -- UNDEFINED'%( var, )
	try:
		var = vars.next()
	except StopIteration, err:
		return None
	else:
		return agi.getVariable( var ).addCallback( doPrint, var ).addErrback(
			notAvailable, var,
		).addCallback(
			printVar, agi, vars,
		)
	

def testFunction( agi ):
	"""Print out known AGI variables"""
	log.debug( 'testFunction' )
	print 'AGI Variables'
	pprint.pprint( agi.variables )
	print 'Channel Variables'
	sequence = fastagi.InSequence()
	sequence.append( printVar, None, agi, envVars(agi) )
	sequence.append( agi.finish )
	def onFailure( reason ):
		log.error( "Failure: %s", reason.getTraceback())
		agi.finish()
	return sequence().addErrback( onFailure )

if __name__ == "__main__":
	logging.basicConfig()
	#fastagi.log.setLevel( logging.DEBUG )
	APPLICATION = utilapplication.UtilApplication()
	APPLICATION.handleCallsFor( 's', testFunction )
	APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
	reactor.run()
