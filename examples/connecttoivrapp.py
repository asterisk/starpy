"""Example script to generate a call to connect a remote channel to an IVR

This version of the script uses the utilapplication framework and is
pared down for presentation on a series of slides
"""
from starpy import manager
import utilapplication
from twisted.internet import reactor
import sys, logging
APPLICATION = utilapplication.UtilApplication()

def main( channel = 'sip/4167290048@testout', connectTo=('outgoing','s','1') ):
	df = APPLICATION.amiSpecifier.login()
	def onLogin( protocol ):
		"""We've logged into the manager, generate a call and log off"""
		context, extension, priority = connectTo
		df = protocol.originate(
			channel,
			context,extension,priority,
		)
		def onFinished( result ):
			return protocol.logoff()
		df.addCallbacks( onFinished, onFinished )
		return df 
	def onFailure( reason ):
		print reason.getTraceback()
	def onFinished( result ):
		reactor.stop()
	df.addCallbacks( 
		onLogin, onFailure 
	).addCallbacks( onFinished, onFinished )
	return df

if __name__ == "__main__":
	logging.basicConfig()
	reactor.callWhenRunning( main )
	reactor.run()
