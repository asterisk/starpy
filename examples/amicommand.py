#! /usr/bin/env python
"""Test/sample to call "show database" command
"""
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi, utilapplication, menu
import os, logging, pprint, time

log = logging.getLogger( 'callduration' )
APPLICATION = utilapplication.UtilApplication()

def main():
	def onConnect( ami ):
		def onResult( result ):
			print 'Result', result 
			return ami.logoff()
		def onError( reason ):
			print reason.getTraceback()
			return reason
		def onFinished( result ):
			reactor.stop()
		df = ami.command( 'database show' )
		df.addCallbacks( onResult, onError )
		df.addCallbacks( onFinished, onFinished )
		return df
	amiDF = APPLICATION.amiSpecifier.login( 
	).addCallback( onConnect )

if __name__ == "__main__":
	logging.basicConfig()
	manager.log.setLevel( logging.DEBUG )
	reactor.callWhenRunning( main )
	reactor.run()

