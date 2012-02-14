#! /usr/bin/env python
"""Provide a trivial date-and-time service"""
from twisted.internet import reactor
from starpy import fastagi
import utilapplication
import logging, time

log = logging.getLogger( 'dateandtime' )

def testFunction( agi ):
	"""Give time for some time a bit in the future"""
	log.debug( 'testFunction' )
	df = agi.streamFile( 'at-tone-time-exactly' )
	def onFailed( reason ):
		log.error( "Failure: %s", reason.getTraceback())
		return None
	def cleanup( result ):
		agi.finish()
		return result
	def onSaid( resultLine ):
		"""Having introduced, actually read the time"""
		t = time.time()
		t2 = t+7.0
		df = agi.sayDateTime( t2, format='HMS' )
		def onDateFinished( resultLine ):
			# now need to sleep until .05 seconds before the time 
			df = agi.wait( t2-.05-time.time() )
			def onDoBeep( result ):
				df = agi.streamFile( 'beep' )
				return df
			def waitTwo( result ):
				return agi.streamFile( 'thank-you-for-calling' )
			return df.addCallback( onDoBeep ).addCallback( waitTwo )
		return df.addCallback( onDateFinished )
	return df.addCallback( 
		onSaid 
	).addErrback( 
		onFailed 
	).addCallbacks(
		cleanup, cleanup,
	)

if __name__ == "__main__":
	logging.basicConfig()
	fastagi.log.setLevel( logging.INFO )
	APPLICATION = utilapplication.UtilApplication()
	reactor.callWhenRunning( APPLICATION.agiSpecifier.run, testFunction )
	reactor.run()
