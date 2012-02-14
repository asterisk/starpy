#! /usr/bin/env python
"""Sample application to read call duration back to user

Implemented as an AGI and a manager connection, send
those who want to time the call to the AGI, we will wait
for the end of the call, then call them back with the
duration message.
"""
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi
import utilapplication
import menu
import os, logging, pprint, time

log = logging.getLogger( 'callduration' )

class Application( utilapplication.UtilApplication ):
    """Application for the call duration callback mechanism"""
    def onS( self, agi ):
        """Incoming AGI connection to the "s" extension (start operation)"""
        log.info( """New call tracker""" )
        c = CallTracker()
        return c.recordChannelInfo( agi ).addErrback(
            agi.jumpOnError, difference=100,
        )

class CallTracker( object ):
    """Object which tracks duration of a single call

    This object encapsulates the entire interaction with the user, from
    the initial incoming FastAGI that records the channel ID and account
    number through the manager watching for the disconnect to the new call
    setup and the FastAGI that plays back the results...

    Requires a context 'callduration' with 's' mapping to this AGI, as well
    as all numeric extensions.
    """
    ourContext = 'callduration'
    def __init__( self ):
        """Initialise the tracker object"""
        self.uniqueChannelId = None
        self.currentChannel = None
        self.callbackChannel = None
        self.account = None
        self.cancelled = False
        self.ami = None
        self.startTime = None
        self.stopTime = None
    def recordChannelInfo( self, agi ):
        """Records relevant channel information, creates manager watcher"""
        self.uniqueChannelId = agi.variables['agi_uniqueid']
        self.currentChannel = currentChannel = agi.variables['agi_channel']
        # XXX everything up to the last - is normally our local caller's "address"
        # this is not, however, a great way to decide who to call back...
        self.callbackChannel = currentChannel.rsplit( '-', 1)[0]
        # Ask user for the account number...
        df = menu.CollectDigits(
            soundFile = 'your-account',
            maxDigits = 7,
            minDigits = 3,
            timeout = 5,
        )( agi ).addCallback(
            self.onAccountInput,agi=agi,
        )
        # XXX handle AMI login failure...
        amiDF = APPLICATION.amiSpecifier.login(
        ).addCallback( self.onAMIConnect )
        dl = defer.DeferredList( [df, amiDF] )
        return dl.addCallback( self.onConnectAndAccount )
    def onAccountInput( self, result, agi, retries=2):
        """Allow user to enter again if timed out"""
        self.account = result[0][1]
        self.startTime = time.time()
        agi.finish() # let the user go about their business...
        return agi
    def cleanUp( self, agi=None ):
        """Cleanup on error as much as possible"""
        items = []
        if self.ami:
            items.append( self.ami.logoff())
            self.ami = None
        if items:
            return defer.DeferredList( items )
        else:
            return defer.succeed( False )
    def onAMIConnect( self, ami ):
        """We have successfully connected to the AMI"""
        log.debug( "AMI login complete" )
        if not self.cancelled:
            self.ami = ami
            return ami
        else:
            return self.ami.logoff()
    def onConnectAndAccount( self, results ):
        """We have connected and retrieved an account"""
        log.info( """AMI Connected and account information gathered: %s""", self.uniqueChannelId )
        df = defer.Deferred()
        def onChannelHangup( ami, event ):
            """Deal with the hangup of an event"""
            if event['uniqueid'] == self.uniqueChannelId:
                log.info( """AMI Detected close of our channel: %s""", self.uniqueChannelId )
                self.stopTime = time.time()
                # give the user a few seconds to put down the hand-set
                reactor.callLater( 2, df.callback, event )
                self.ami.deregisterEvent( 'Hangup', onChannelHangup )
            log.debug( 'event:', event )
        if not self.cancelled:
            self.ami.registerEvent( 'Hangup', onChannelHangup )
            return df.addCallback( self.onHangup, callbacks=5 )
    def onHangup( self, event, callbacks=5 ):
        """Okay, the call is finished, time to inform the user"""
        log.debug( 'onHangup %s %s', event, callbacks )
        def ignoreResult( result ):
            """Since we're using an equal timeout waiting for a connect
            we don't care *how* this fails/succeeds"""
            pass
        self.ami.originate(
            self.callbackChannel,
            self.ourContext, id(self), 1,
            timeout = 15,
        ).addCallbacks( ignoreResult, ignoreResult )
        df = APPLICATION.waitForCallOn( id(self), 15 )
        df.addCallbacks(
            self.onUserReconnected, self.onUserReconnectFail,
            errbackKeywords = { 'event': event, 'callbacks': callbacks-1 },
        )
    def onUserReconnectFail( self, reason, event, callbacks ):
        """Wait for bit, then retry..."""
        if callbacks:
            # XXX really want something like a decaying back-off in frequency
            # with final values of e.g. an hour...
            log.info( """Failure connecting: will retry in 30 seconds""" )
            reactor.callLater( 30, self.onHangup, event, callbacks )
        else:
            log.error( """Unable to connect to user, giving up""" )
            return self.cleanUp( None )
    def onUserReconnected( self, agi ):
        """Handle the user interaction after they've re-connected"""
        log.info( """Connection re-established with the user""" )
        # XXX should handle unexpected failures in here...
        delta = self.stopTime - self.startTime
        minutes, seconds = divmod( delta, 60 )
        seconds = int(seconds)
        hours, minutes = divmod( minutes, 60 )
        duration = []
        if hours:
            duration.append( '%s hour%s'%(hours,['','s'][hours!=1]))
        if minutes:
            duration.append( '%s second%s'%(minutes,['','s'][minutes!=1]))
        if seconds:
            duration.append( '%s second%s'%(seconds,['','s'][seconds!=1]))
        if not duration:
            duration = '0'
        else:
            duration = " ".join( duration )
        seq = fastagi.InSequence( )
        seq.append( agi.wait, 1 )
        seq.append( agi.execute, "Festival", "Call to account %r took %s"%(self.account,duration) )
        seq.append( agi.wait, 1 )
        seq.append( agi.execute, "Festival", "Repeating, call to account %r took %s"%(self.account,duration) )
        seq.append( agi.wait, 1 )
        seq.append( agi.finish )
        def logSuccess( ):
            log.debug( """Finished successfully!""" )
            return defer.succeed( True )
        seq.append( logSuccess )
        seq.append( self.cleanUp, agi )
        return seq()

APPLICATION = Application()

if __name__ == "__main__":
    logging.basicConfig()
    log.setLevel( logging.DEBUG )
    #manager.log.setLevel( logging.DEBUG )
    #fastagi.log.setLevel( logging.DEBUG )
    APPLICATION.handleCallsFor( 's', APPLICATION.onS )
    APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
    from twisted.internet import reactor
    reactor.run()
