#! /usr/bin/env python
"""Sample application to test the menuing utility classes"""
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi, utilapplication, menu, error
import os, logging, pprint, time

log = logging.getLogger( 'menutest' )

mainMenu = menu.Menu(
	soundFile = 'houston',
	options = [
		menu.Option( option='0' ),
		menu.Option( option='#' ),
		menu.ExitOn( option='*' ),
		menu.SubMenu( 
			option='1',
			menu = menu.Menu(
				tellInvalid = False, # don't report incorrect selections
				soundFile = 'atlantic',
				options = [
					menu.Option( option='0' ),
					menu.Option( option='#' ),
					menu.ExitOn( option='*' ),
				],
			),
		),
		menu.SubMenu(
			option='2',
			menu = menu.CollectDigits(
				soundFile = 'extension',
				maxDigits = 5,
				minDigits = 3,
			),
		),
	],
)

class Application( utilapplication.UtilApplication ):
	"""Application for the call duration callback mechanism"""
	def onS( self, agi ):
		"""Incoming AGI connection to the "s" extension (start operation)"""
		log.info( """New call tracker""" )
		def onComplete( result ):
			log.info( """Final result: %r""", result )
			agi.finish()
		return mainMenu( agi ).addCallbacks( onComplete, onComplete )

APPLICATION = Application()

if __name__ == "__main__":
	logging.basicConfig()
	log.setLevel( logging.DEBUG )
	#manager.log.setLevel( logging.DEBUG )
	fastagi.log.setLevel( logging.DEBUG )
	menu.log.setLevel( logging.DEBUG )
	APPLICATION.handleCallsFor( 's', APPLICATION.onS )
	APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
	from twisted.internet import reactor
	reactor.run()
