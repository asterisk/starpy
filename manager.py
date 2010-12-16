"""Asterisk Manager Interface for the Twisted networking framework

The Asterisk Manager Interface is a simple line-oriented protocol that allows
for basic control of the channels active on a given Asterisk server.

Module defines a standard Python logging module log 'AMI'
"""
from twisted.internet import protocol, reactor, defer
from twisted.protocols import basic
from twisted.internet import error as tw_error
import socket, logging
from starpy import error

log = logging.getLogger('AMI')

class AMIProtocol(basic.LineOnlyReceiver):
    """Protocol for the interfacing with the Asterisk Manager Interface (AMI)

    Provides most of the AMI Action interfaces.
    Auto-generates ActionID fields for all calls.

    Events and messages are passed around as simple dictionaries with
    all-lowercase keys.  Values are case-sensitive.

    XXX Want to allow for timeouts

    Attributes:
        count -- total count of messages sent from this protocol
        hostName -- used along with count and ID to produce unique IDs
        messageCache -- stores incoming message fragments from the manager
        id -- An identifier for this instance
    """
    count = 0
    amiVersion = None
    id = None
    def __init__(self, *args, **named):
        """Initialise the AMIProtocol, arguments are ignored"""
        self.messageCache = []
        self.actionIDCallbacks = {}
        self.eventTypeCallbacks = {}
        self.hostName = socket.gethostname()
    def registerEvent(self, event, function):
        """Register callback for the given event-type

        event -- string name for the event, None to match all events, or
            a tuple of string names to match multiple events.

            See http://www.voip-info.org/wiki/view/asterisk+manager+events
            for list of events and the data they bear.  Includes:

                Newchannel -- note that you can receive multiple Newchannel
                    events for a single channel!
                Hangup
                Newexten
                Newstate
                Reload
                Shutdown
                ExtensionStatus
                Rename
                Newcallerid
                Alarm
                AlarmClear
                Agentcallbacklogoff
                Agentcallbacklogin
                Agentlogin
                Agentlogoff
                MeetmeJoin
                MeetmeLeave
                MessageWaiting
                Join
                Leave
                AgentCalled
                ParkedCall
                Cdr
                ParkedCallsComplete
                QueueParams
                QueueMember

            among other standard events.  Also includes user-defined events.
        function -- function taking (protocol,event) as arguments or None
            to deregister the current function.

        Multiple functions may be registered for a given event
        """
        log.debug('Registering function %s to handle events of type %r', function, event)
        if isinstance(event, (str,unicode,type(None))):
            event = (event,)
        for ev in event:
            self.eventTypeCallbacks.setdefault(ev, []).append(function)
    def deregisterEvent(self, event, function=None):
        """Deregister callback for the given event-type

        event -- event name (or names) to be deregistered, see registerEvent
        function -- the function to be removed from the callbacks or None to
            remove all callbacks for the event

        returns success boolean
        """
        log.debug('Deregistering handler %s for events of type %r', function, event)
        if isinstance(event, (str,unicode,type(None))):
            event = (event,)
        success = True
        for ev in event:
            try:
                set = self.eventTypeCallbacks[ ev ]
            except KeyError, err:
                success = False
            else:
                try:
                    while function in set:
                        set.remove(function)
                except (ValueError,KeyError), err:
                    success = False
                if not set or function is None:
                    try:
                        del self.eventTypeCallbacks[ ev ]
                    except KeyError, err:
                        success = False
        return success
    def lineReceived(self, line):
        """Handle Twisted's report of an incoming line from the manager"""
        log.debug('Line In: %r', line)
        self.messageCache.append(line)
        if not line.strip():
            self.dispatchIncoming() # does dispatch and clears cache
    def connectionMade(self):
        """Handle connection to the AMI port (auto-login)

        This is a Twisted customisation point, we use it to automatically
        log into the connection we've just established.

        XXX Should probably use proper Twisted-style credential negotiations
        """
        log.info('Connection Made')
        df = self.login()
        def onComplete(message):
            """Check for success, errback or callback as appropriate"""
            if not message['response'] == 'Success':
                log.info('Login Failure: %s', message)
                self.transport.loseConnection()
                self.factory.loginDefer.errback(
                    error.AMICommandFailure("""Unable to connect to manager""", message)
                )
            else:
                # XXX messy here, would rather have the factory trigger its own
                # callback...
                log.info('Login Complete: %s', message)
                self.factory.loginDefer.callback(
                    self,
                )
        def onFailure(reason):
            """Handle failure to connect (e.g. due to timeout)"""
            log.info('Login Call Failure: %s', reason.getTraceback())
            self.transport.loseConnection()
            self.factory.loginDefer.errback(
                reason
            )
        df.addCallbacks(onComplete, onFailure)
    def connectionLost(self, reason):
        """Connection lost, clean up callbacks"""
        for key,callable in self.actionIDCallbacks.items():
            try:
                callable(tw_error.ConnectionDone("""FastAGI connection terminated"""))
            except Exception, err:
                log.error("""Failure during connectionLost for callable %s: %s""", callable, err)
        self.actionIDCallbacks.clear()
        self.eventTypeCallbacks.clear()
    VERSION_PREFIX = 'Asterisk Call Manager'
    END_DATA = '--END COMMAND--'
    def dispatchIncoming(self):
        """Dispatch any finished incoming events/messages"""
        log.debug('Dispatch Incoming')
        message = {}
        while self.messageCache:
            line = self.messageCache.pop(0)
            line = line.strip()
            if line:
                if line.endswith(self.END_DATA):
                    # multi-line command results...
                    message.setdefault(' ', []).extend([
                        l for l in line.split('\n') if (l and l!=self.END_DATA)
                    ])
                else:
                    # regular line...
                    if line.startswith(self.VERSION_PREFIX):
                        self.amiVersion = line[len(self.VERSION_PREFIX)+1:].strip()
                    else:
                        try:
                            key,value = line.split(':',1)
                        except ValueError, err:
                            # XXX data-safety issues, what prevents the VERSION_PREFIX from
                            # showing up in a data-set?
                            log.warn("""Improperly formatted line received and ignored: %r""", line)
                        else:
                            message[ key.lower().strip() ] = value.strip()
        log.debug('Incoming Message: %s', message)
        if message.has_key('actionid'):
            key = message['actionid']
            callback = self.actionIDCallbacks.get(key)
            if callback:
                try:
                    callback(message)
                except Exception, err:
                    # XXX log failure here...
                    pass
        # otherwise is a monitor message or something we didn't send...
        if message.has_key('event'):
            self.dispatchEvent(message)
    def dispatchEvent(self, event):
        """Given an incoming event, dispatch to registered handlers"""
        for key in (event['event'], None):
            try:
                handlers = self.eventTypeCallbacks[ key ]
            except KeyError, err:
                pass
            else:
                for handler in handlers:
                    try:
                        handler(self, event)
                    except Exception, err:
                        # would like the getException code here...
                        log.error(
                            'Exception in event handler %s on event %s: %s',
                            handler, event, err
                        )
    def generateActionId(self):
        """Generate a unique action ID

        Assumes that hostName must be unique among all machines which talk
        to a given AMI server.  With that is combined the memory location of
        the protocol object (which should be machine-unique) and the count of
        messages that this manager has created so far.

        Generally speaking, you shouldn't need to know the action ID, as the
        protocol handles the management of them automatically.
        """
        self.count += 1
        return '%s-%s-%s'%(self.hostName,id(self),self.count)
    def sendDeferred(self, message):
        """Send with a single-callback deferred object

        Returns deferred that fires when a response to this message is received
        """
        df = defer.Deferred()
        actionid = self.sendMessage(message, df.callback)
        df.addCallbacks(
            self.cleanup, self.cleanup,
            callbackArgs=(actionid,), errbackArgs=(actionid,)
        )
        return df
    def cleanup(self, result, actionid):
        """Cleanup callbacks on completion"""
        try:
            del self.actionIDCallbacks[actionid]
        except KeyError, err:
            pass
        return result

    def sendMessage(self, message, responseCallback=None):
        """Send the message to the other side, return deferred for the result

        returns the actionid for the message
        """
        message = dict([(k.lower(),v) for (k,v) in message.items()])
        if not message.has_key('actionid'):
            message['actionid'] = self.generateActionId()
        if responseCallback:
            self.actionIDCallbacks[message['actionid']] = responseCallback
        log.debug("""MSG OUT: %s""", message)
        for key,value in message.items():
            self.sendLine('%s: %s'%(str(key.lower()),str(value)))
        self.sendLine('')
        return message['actionid']
    def collectDeferred(self, message, stopEvent):
        """Collect all responses to this message until stopEvent or error

        returns deferred returning sequence of events/responses
        """
        df = defer.Deferred()
        cache = []
        def onEvent(event):
            if event.get('response') == 'Error':
                df.errback(error.AMICommandFailure(event))
            elif event['event'] == stopEvent:
                df.callback(cache)
            else:
                cache.append(event)
        actionid = self.sendMessage(message, onEvent)
        df.addCallbacks(
            self.cleanup, self.cleanup,
            callbackArgs=(actionid,), errbackArgs=(actionid,)
        )
        return df
    def errorUnlessResponse(self, message, expected='Success'):
        """Raise a AMICommandFailure error unless message['response'] == expected

        If == expected, returns the message
        """
        if message['response'] != expected:
            raise error.AMICommandFailure(message)
        return message

    ## End-user API
    def absoluteTimeout(self, channel, timeout):
        """Set timeout value for the given channel (in seconds)"""
        message = {'action':'absolutetimeout','timeout':timeout,'channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def agentLogoff(self,agent,soft):
        """Logs off the specified agent for the queue system."""
        if soft in (True,'yes',1):
            soft='true'
        else:
            soft='false'
        message = {'Action':'AgentLogoff','Agent':agent,'Soft':soft}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def agents(self):
        """Retrieve agents information"""
        message = {"action":"agents"}
        return self.collectDeferred(message, "AgentsComplete")
    def changeMonitor(self, channel, filename):
        """Change the file to which the channel is to be recorded"""
        message = {'action':'changemonitor','channel':channel,'filename':filename}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def command(self, command):
        """Run asterisk console command, return deferred result for line of lines

        returns deferred returning list of lines (strings) of the command
        output.

        See listCommands to see available commands
        """
        df = self.sendDeferred({'action': 'command', 'command':command })
        df.addCallback(self.errorUnlessResponse, expected='Follows')
        def onResult(message):
            return message[' ']
        return df.addCallback(onResult)
    def dbGet(self,family,key):
        """This action retrieves a value from the AstDB database"""
        df = defer.Deferred()
        def extractValue(ami,event):
            value = event['val']
            return df.callback(value)
        message = {'Action':'DBGet','family':family,'key':key}
        self.sendDeferred(message).addCallback(self.errorUnlessResponse)
        self.registerEvent("DBGetResponse",extractValue)
        return df
    def  dbPut(self,family,key,value):
        """Sets a key value in the AstDB database"""
        message = {'Action':'DBPut','Family':family,'Key':key,'Val':value}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def events(self, eventmask=False):
        """Determine whether events are generated"""
        if eventmask in ('off',False,0):
            eventmask = 'off'
        elif eventmask in ('on',True,1):
            eventmask = 'on'
        # otherwise is likely a type-mask
        message = {'action':'events','eventmask':eventmask}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def extensionState(self,exten,context):
        """This command reports the extension state for the given extension. If the extension has a hint, this will report the status of the device connected to the extension

        The following are the possible extension states:

        -2    Extension removed
        -1    Extension hint not found
         0    Idle
         1    In use
         2    Busy"""
        message = {'Action':'ExtensionState','Exten':exten,'Context':context}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def getConfig(self,filename):
        """Retrieves the data from an Asterisk configuration file"""
        message = {'Action':'GetConfig','filename':filename}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def getVar(self, channel, variable):
        """Retrieve the given variable from the channel"""
        def extractVariable(message):
            """When message comes in, extract the variable from it"""
            if message.has_key(variable.lower()):
                value = message[variable.lower()]
            elif message.has_key('value'):
                value = message['value']
            else:
                raise error.AMICommandFailure(message)
            if value == '(null)':
                value = None
            return value
        message = {'action':'getvar','channel':channel,'variable':variable}
        return self.sendDeferred(
            message
        ).addCallback(
            self.errorUnlessResponse
        ).addCallback(
            extractVariable,
        )
    def hangup(self, channel):
        """Tell channel to hang up"""
        message = {'action':'hangup','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)

    def login(self):
        """Log into the AMI interface (done automatically on connection)

        Uses factory.username and factory.secret
        """
        self.id = self.factory.id
        return self.sendDeferred({
            'action': 'login',
            'username': self.factory.username,
            'secret': self.factory.secret,
        }).addCallback(self.errorUnlessResponse)
    def listCommands(self):
        """List the set of commands available

        Returns a single message with each command-name as a key
        """
        message = {'action':'listcommands',}
        def removeActionId(message):
            try:
                del message['actionid']
            except KeyError, err:
                pass
            return message
        return self.sendDeferred(message).addCallback(
            self.errorUnlessResponse
        ).addCallback(
            removeActionId
        )
    def logoff(self):
        """Log off from the manager instance"""
        message = {'action':'logoff'}
        return self.sendDeferred(message).addCallback(
            self.errorUnlessResponse, expected = 'Goodbye',
        )
    def mailboxCount(self, mailbox):
        """Get count of messages in the given mailbox"""
        message = {'action':'mailboxcount','mailbox':mailbox}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def mailboxStatus(self, mailbox):
        """Get status of given mailbox"""
        message = {'action':'mailboxstatus','mailbox':mailbox}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def meetmeMute(self, meetme, usernum):
        """Mute a user in a given meetme"""
        message = {'action':'MeetMeMute','meetme':meetme,'usernum':usernum}
        return self.sendDeferred(message)
    def meetmeUnmute(self,meetme,usernum):
        """ Unmute a specified user in a given meetme"""
        message = {'action':'meetmeunmute','meetme':meetme,'usernum':usernum}
        return self.sendDeferred(message)
    def monitor(self, channel, file, format, mix):
        """Record given channel to a file (or attempt to anyway)"""
        message = {'action':'monitor','channel':channel,'file':file,'format':format, 'mix':mix}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def originate(
        self, channel, context=None, exten=None, priority=None,
        timeout=None, callerid=None, account=None, application=None,
        data=None, variable={}, async=False
    ):
        """Originate call to connect channel to given context/exten/priority

        channel -- the outgoing channel to which will be dialed
        context/exten/priority -- the dialplan coordinate to which to connect
            the channel (i.e. where to start the called person)
        timeout -- duration before timeout in seconds (note: not Asterisk standard!)
        callerid -- callerid to display on the channel
        account -- account to which the call belongs
        application -- alternate application to Dial to use for outbound dial
        data -- data to pass to application
        variable -- variables associated to the call
        async -- make the origination asynchronous
        """
        variable = '|'.join([ "%s=%s" %(x[0], x[1]) for x in variable.items() ])
        message = dict([(k,v) for (k,v) in {
            'action': 'originate',
            'channel':channel,'context':context,'exten':exten,'priority':priority,
            'timeout':timeout,'callerid':callerid,'account':account,'application':application,
            'data':data, 'variable':variable, 'async':str(async)
        }.items() if v is not None])
        if message.has_key('timeout'):
            message['timeout'] = message['timeout']*1000
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def park(self, channel,channel2,timeout):
        """Park channel"""
        message = {'action':'park','channel':channel,'channel2':channel2,'timeout':timeout}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def parkedCalls(self):
        """Retrieve set of parked calls via multi-event callback"""
        message = {'action':'ParkedCalls'}
        return self.collectDeferred(message, 'ParkedCallsComplete')
    def pauseMonitor(self,channel):
        """Temporarily stop recording the channel"""
        message = {'action':'pausemonitor','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def ping(self):
        """Check to see if the manager is alive..."""
        message = {'action':'ping'}
        if self.amiVersion == "1.0":
            return self.sendDeferred(message).addCallback(
                self.errorUnlessResponse, expected = 'Pong',
            )
        else:
            return self.sendDeferred(message).addCallback(
                self.errorUnlessResponse
            )
    def playDTMF(self, channel, digit):
        """Play DTMF on a given channel"""
        message = {'action':'playdtmf','channel':channel,'digit':digit}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def queueAdd(self, queue, interface, penalty=0, paused=True):
        """Add given interface to named queue"""
        if paused in (True,'true',1):
            paused = 'true'
        else:
            paused = 'false'
        message = {'action':'queueadd','queue':queue,'interface':interface,'penalty':penalty, 'paused':paused}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def queuePause(self,queue, interface, paused = True):
        if paused in (True,'true',1):
            paused = 'true'
        else:
            paused = 'false'
        message = {'action':'queuepause','queue':queue,'interface':interface,'paused':paused}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def queueRemove(self, queue, interface):
        """Remove given interface from named queue"""
        message = {'action':'queueremove','queue':queue,'interface':interface}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def queues(self):
        """Retrieve information about active queues via multiple events"""
        # XXX AMI returns improperly formatted lines so this doesn't work now.
        message = {'action':'queues'}
        #return self.collectDeferred(message, 'QueueStatusEnd')
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def queueStatus(self):
        """Retrieve information about active queues via multiple events"""
        message = {'action':'queuestatus'}
        return self.collectDeferred(message, 'QueueStatusComplete')
    def redirect(self, channel, context, exten, priority, extraChannel=None):
        """Transfer channel(s) to given context/exten/priority"""
        message = {
            'action':'redirect','channel':channel,'context':context,
            'exten':exten,'priority':priority,
        }
        if extraChannel is not None:
            message['extrachannel'] = extraChannel
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def setCDRUserField(self, channel, userField, append=True):
        """Set/add to a user field in the CDR for given channel"""
        if append in (True,'true',1):
            append = 'true'
        else:
            append = 'false'
        message = {
            'channel':channel,'userfield':userField,'append':append,
        }
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def setVar(self, channel, variable, value):
        """Set channel variable to given value"""
        message = {'action':'setvar','channel':channel,'variable':variable,'value':value}
        return self.sendDeferred(
            message
        ).addCallback(
            self.errorUnlessResponse
        )
    def sipPeers(self):
        """List all known sip peers"""
        # XXX not available on my box...
        message = {'action':'sippeers'}
        return self.collectDeferred(message, 'PeerlistComplete')
    def sipShowPeers(self, peer):
        message = {'action':'sipshowpeer','peer':peer}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def status(self, channel=None):
        """Retrieve status for the given (or all) channels via multi-event callback

        channel -- channel name or None to retrieve all channels

        returns deferred returning list of Status Events for each requested
        channel
        """
        message = {'action':'Status'}
        if channel:
            message['channel'] = channel
        return self.collectDeferred(message, 'StatusComplete')
    def stopMonitor(self, channel):
        """Stop monitoring the given channel"""
        message = {'action':'monitor','channel':channel,}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def unpauseMonitor(self, channel):
        """Resume recording a channel"""
        message = {'action':'unpausemonitor','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def updateConfig(self, srcfile, dstfile, reload, headers={}):
        """Update a configuration file

        headers should be a dictionary with the following keys
        Action-XXXXXX
        Cat-XXXXXX
        Var-XXXXXX
        Value-XXXXXX
        Match-XXXXXX
        """
        message = {}
        if reload in (True,'yes',1):
            reload='yes'
        else:
            reload='no'
        message = {'action':'updateconfig','srcfilename':srcfile,'dstfilename':dstfile,'reload':reload}
        for k,v in headers.items():
            message[k] = v
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def userEvent(self,event,**headers):
        """Sends an arbitrary event to the Asterisk Manager Interface."""
        message = {'Action':'UserEvent','userevent':event}
        for i,j in headers.items():
            message[i] =j
        return self.sendMessage(message)
    def waitEvent(self,timeout):
        """Waits for an event to occur

            After calling this action, Asterisk will send you a Success response as soon as another event is queued by the AMI"""
        message={'action':'WaitEvent','timeout':timeout}
        return self.collectDeferred(message, 'WaitEventComplete')
    def zapDNDoff(self,channel):
        """Toggles the do not disturb state on the specified Zap channel to off"""
        messge = {'action':'zapDNDoff','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def zapDNDon(self,channel):
        """Toggles the do not disturb state on the specified Zap channel to on"""
        messge = {'action':'zapDNDon','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def zapDialOffhook(self,channel,number):
        """Dials the specified number on the Zap channel while the phone is off-hook"""
        message = {'Action':'ZapDialOffhook','ZapChannel':channel,'Number':number}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def zapHangup(self,channel):
        """Hangs up the specified Zap channel"""
        message = {'Action':'ZapHangup','ZapChannel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def zapRestart(self,channel):
        """Completly restarts the Zaptel channels, terminating any calls in progress"""
        message = {'Action':'ZapRestart','ZapChannel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)
    def zapShowChannels(self):
        """List all zap channels"""
        message = {'action':'zapshowchannels'}
        return self.collectDeferred(message, 'ZapShowChannelsComplete')
    def zapTransfer(self,channel):
        """Transfers zap channel"""
        message = {'Action':'ZapTransfer','channel':channel}
        return self.sendDeferred(message).addCallback(self.errorUnlessResponse)



class AMIFactory(protocol.ClientFactory):
    """A factory for AMI protocols
    """
    protocol = AMIProtocol
    def __init__(self, username, secret, id=None):
        self.username = username
        self.secret = secret
        self.id = id
    def login(self, ip='localhost', port=5038, timeout=5):
        """Connect, returning our (singleton) protocol instance with login completed

        XXX This is messy, we'd much rather have the factory able to create
        large numbers of protocols simultaneously
        """
        self.loginDefer = defer.Deferred()
        reactor.connectTCP(ip, port, self, timeout=timeout)
        return self.loginDefer
    def clientConnectionFailed(self, connector, reason):
        """Connection failed, report to our callers"""
        self.loginDefer.errback(reason)

