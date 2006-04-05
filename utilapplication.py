"""Class providing utility applications with common support code"""
from basicproperty import common, propertied, basic, weak
from ConfigParser import ConfigParser
from starpy import fastagi, manager
from twisted.internet import defer, reactor
import logging,os

log = logging.getLogger( 'app' )

class UtilApplication( propertied.Propertied ):
	"""Utility class providing simple application-level operations
	
	FastAGI entry points are waitForCallOn and handleCallsFor, which allow
	for one-shot and permanant handling of calls for an extension 
	(respectively), and agiSpecifier, which is loaded from configuration file 
	(as specified in self.configFiles).
	"""
	amiSpecifier = basic.BasicProperty(
		"amiSpecifier", """AMI connection specifier for the application see AMISpecifier""",
		defaultFunction = lambda prop,client: AMISpecifier()
	)
	agiSpecifier = basic.BasicProperty(
		"agiSpecifier", """FastAGI server specifier for the application see AGISpecifier""",
		defaultFunction = lambda prop,client: AGISpecifier()
	)
	extensionWaiters = common.DictionaryProperty(
		"extensionWaiters", """Set of deferreds waiting for incoming extensions""",
	)
	extensionHandlers = common.DictionaryProperty(
		"extensionHandlers", """Set of permanant callbacks waiting for incoming extensions""",
	)
	configFiles = configFiles=('starpy.conf','~/.starpy.conf')
	def __init__( self ):
		"""Initialise the application from options in configFile"""
		parser = self._loadConfigFiles( self.configFiles )
		self._copyPropertiesFrom( parser, 'AMI', self.amiSpecifier )
		self._copyPropertiesFrom( parser, 'FastAGI', self.agiSpecifier )
	def _loadConfigFiles( self, configFiles ):
		"""Load options from configuration files given (if present)"""
		parser = ConfigParser( )
		filenames = [
			os.path.abspath( os.path.expandvars( os.path.expanduser( file ) ))
			for file in configFiles
		]
		log.info( "Possible configuration files:\n\t%s", "\n\t".join(filenames) or None)
		filenames = [
			file for file in filenames
			if os.path.isfile(file)
		]
		log.info( "Actual configuration files:\n\t%s", "\n\t".join(filenames) or None)
		parser.read( filenames )
		return parser
	def _copyPropertiesFrom( self, parser, section, client, properties=None ):
		"""Copy properties from the config-parser's given section into client"""
		if properties is None:
			properties = client.getProperties()
		for property in properties:
			if parser.has_option( section, property.name ):
				try:
					value = parser.get( section, property.name )
					setattr( client, property.name, value )
				except (TypeError,ValueError,AttributeError,NameError), err:
					log( """Unable to set property %r of %r to config-file value %r: %s"""%(
						property.name, client, parser.get( section, property.name, 1), err,
					))
		return client
	def dispatchIncomingCall( self, agi ):
		"""Handle an incoming call (dispatch to the appropriate registered handler)"""
		extension = agi.variables['agi_extension']
		log.info( """AGI connection with extension: %r""",  extension )
		try:
			df = self.extensionWaiters.pop( extension )
		except KeyError, err:
			try:
				callback = self.extensionHandlers[ extension ]
			except KeyError, err:
				log.warn( """Unexpected connection to extension %r: %s""", extension, agi.variables )
				agi.finish()
			else:
				try:
					return callback( agi )
				except Exception, err:
					log.error( """Failure during callback %s for agi %s: %s""", callback, agi.variables, err )
					# XXX return a -1 here
		else:
			if not df.called:
				df.callback( agi )
	def waitForCallOn( self, extension, timeout=15 ):
		"""Wait for an AGI call on extension given
		
		extension -- string extension for which to wait 
		timeout -- duration in seconds to wait before defer.TimeoutError is 
			returned to the deferred.
		
		returns deferred returning connected FastAGIProtocol or an error
		"""
		extension = str(extension)
		log.info( 'Waiting for extension %r for %s seconds', extension, timeout )
		df = defer.Deferred( )
		self.extensionWaiters[ extension ] = df
		def onTimeout( ):
			if not df.called:
				df.errback( defer.TimeoutError( 
					"""Timeout waiting for call on extension: %r"""%(extension,)
				))
		reactor.callLater( timeout, onTimeout )
		return df
	def handleCallsFor( self, extension, callback ):
		"""Register permanant handler for given extension
		
		extension -- string extension for which to wait 
		callback -- callback function to be called for each incoming channel
			to the given extension.
		
		returns None
		"""
		extension = str(extension)
		self.extensionHandlers[ extension ] = callback 

class AMISpecifier( propertied.Propertied ):
	"""Manager interface setup/specifier"""
	username = common.StringLocaleProperty(
		"username", """Login username for the manager interface""",
	)
	secret = common.StringLocaleProperty(
		"secret", """Login secret for the manager interface""",
	)
	password = secret
	server = common.StringLocaleProperty(
		"server", """Server IP address to which to connect""",
		defaultValue = '127.0.0.1',
	)
	port = common.IntegerProperty(
		"port", """Server IP port to which to connect""",
		defaultValue = 5038,
	)
	def login( self ):
		"""Login to the specified manager via the AMI"""
		theManager = manager.AMIFactory(self.username, self.secret)
		return theManager.login(self.server, self.port)

class AGISpecifier( propertied.Propertied ):
	"""Specifier of where we send the user to connect to our AGI"""
	port = common.IntegerProperty(
		"port", """IP port on which to listen""",
		defaultValue = 4573,
	)
	interface = common.StringLocaleProperty(
		"interface", """IP interface on which to listen (local only by default)""",
		defaultValue = '127.0.0.1',
	)
	context = common.StringLocaleProperty(
		"context", """Asterisk context to which to connect incoming calls""",
		defaultValue = 'survey',
	)
	def run( self, mainFunction ):
		"""Start up the AGI server with the given mainFunction"""
		f = fastagi.FastAGIFactory(mainFunction)
		return reactor.listenTCP(self.port, f, 50, self.interface) 
