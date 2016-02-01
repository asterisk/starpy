#! /usr/bin/env python

import os, logging, pprint, time
import random
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi
import utilapplication
import menu
from basicproperty import common, propertied, basic


log = logging.getLogger('priexhaustion')
log.setLevel(logging.DEBUG)


class ChannelTracker(propertied.Propertied):
    """Track open channels on the Asterisk server"""
    channels = common.DictionaryProperty(
        "channels",
        """Set of open channels on the system""",
    )
    thresholdCount = common.IntegerProperty(
        "thresholdCount",
        """Storage of threshold below which we don't warn user""",
        defaultValue=20,
    )

    def main(self):
        """Main operation for the channel-tracking demo"""
        deferred = APPLICATION.amiSpecifier.login(on_reconnect=self.onAMIReconnect)
        self.addCallbacks(deferred)

    def onAMIReconnect(self, deferred=None):
        """Callback for AMIFactory's reconnect event"""
        log.debug("""Reconnecting""")
        self.addCallbacks(deferred)

    def addCallacks(self, deferred=None)
        """Callbacks setting helper"""
        deferred.addCallback(self.onAMIConnect)
        deferred.addErrback(self.onAMIFailed)

    def onAMIConnect(self, ami):
        """Connection handler"""
        self.delay = self.initialDelay
        ami.status().addCallback(self.onStatus, ami=ami)
        ami.registerEvent('Hangup', self.onChannelHangup)
        ami.registerEvent('Newchannel', self.onChannelNew)

    def onAMIFailed(self, reason):
        """Failed connection handler"""
        log.error("""Connection failed: """)
        log.debug("""Reason: %s""" % reason)

    def onStatus(self, events, ami=None):
        """Integrate the current status into our set of channels"""
        log.debug("""Initial channel status retrieved""")
        for event in events:
            self.onChannelNew(ami, event)

    def onChannelNew(self, ami, event):
        """Handle creation of a new channel"""
        log.debug("""Start on channel %s""", event)
        if 'uniqueid' in event:
            opening = not event['uniqueid'] in self.channels
            self.channels[event['uniqueid']] = event
            if opening:
                self.onChannelChange(ami, event, opening=opening)

    def onChannelHangup(self, ami, event):
        """Handle hangup of an existing channel"""
        try:
            del self.channels[event['uniqueid']]
        except KeyError, err:
            log.warn("""Hangup on unknown channel %s""", event)
        else:
            log.debug("""Hangup on channel %s""", event)
        self.onChannelChange(ami, event, opening=False)

    def onChannelChange(self, ami, event, opening=False):
        """Channel count has changed, do something useful like enforcing limits"""
        if opening and len(self.channels) > self.thresholdCount:
            log.warn("""Current channel count: %s""", len(self.channels))
        else:
            log.info("""Current channel count: %s""", len(self.channels))

APPLICATION = utilapplication.UtilApplication()

if __name__ == "__main__":
    logging.basicConfig()
    tracker = ChannelTracker()
    reactor.callWhenRunning(tracker.main)
    reactor.run()
