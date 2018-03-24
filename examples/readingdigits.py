#! /usr/bin/env python
"""Read digits from the user in various ways..."""
from twisted.internet import reactor
from starpy import fastagi
import logging

log = logging.getLogger('hellofastagi')


class DialPlan(object):
    """Stupid little application to report how many times it's been accessed"""

    def __init__(self):
        self.count = 0

    def __call__(self, agi):
        """Store the AGI instance for later usage, kick off our operations"""
        self.agi = agi
        return self.start()

    def start(self):
        """Begin the dial-plan-like operations"""
        return self.agi.answer().addCallbacks(self.onAnswered, self.answerFailure)

    def answerFailure(self, reason):
        """Deal with a failure to answer"""
        log.warn(
            """Unable to answer channel %r: %s""",
            self.agi.variables['agi_channel'], reason.getTraceback(),
        )
        self.agi.finish()

    def onAnswered(self, resultLine):
        """We've managed to answer the channel, yay!"""
        self.count += 1
        return self.agi.wait(2.0).addCallback(self.onWaited)

    def onWaited(self, result):
        """We've finished waiting, tell the user the number"""
        return self.agi.sayNumber(self.count, '*').addErrback(
            self.onNumberFailed,
        ).addCallbacks(
            self.onFinished, self.onFinished,
        )

    def onFinished(self, resultLine):
        """We said the number correctly, hang up on the user"""
        return self.agi.finish()

    def onNumberFailed(self, reason):
        """We were unable to read the number to the user"""
        log.warn(
            """Unable to read number to user on channel %r: %s""",
            self.agi.variables['agi_channel'], reason.getTraceback(),
        )

    def onHangupFailure(self, reason):
        """Failed trying to hang up"""
        log.warn(
            """Unable to hang up channel %r: %s""",
            self.agi.variables['agi_channel'], reason.getTraceback(),
        )


if __name__ == "__main__":
    logging.basicConfig()
    fastagi.log.setLevel(logging.DEBUG)
    f = fastagi.FastAGIFactory(DialPlan())
    reactor.listenTCP(4573, f, 50, '127.0.0.1')  # only binding on local interface
    reactor.run()
