#! /usr/bin/env python
"""Provide a trivial date-and-time service"""
from twisted.internet import reactor
from starpy import fastagi
import logging
import time

log = logging.getLogger('dateandtime')


def testFunction(agi):
    """Give time for some time a bit in the future"""
    log.debug('testFunction')
    df = agi.streamFile('at-tone-time-exactly')

    def onFailed(reason):
        log.error("Failure: %s", reason.getTraceback())
        return None

    def cleanup(result):
        agi.finish()
        return result

    def onSaid(resultLine):
        """Having introduced, actually read the time"""
        t = time.time()
        t2 = t+20.0
        df = agi.sayDateTime(t2, format='HM')

        def onDateFinished(resultLine):
            # now need to sleep until .5 seconds before the time
            df = agi.wait(t2-.5-time.time())

            def onDoBeep(result):
                df = agi.streamFile('beep')
                return df
            return df.addCallback(onDoBeep)
        return df.addCallback(onDateFinished)
    return df.addCallback(
        onSaid
    ).addErrback(
        onFailed
    ).addCallbacks(
        cleanup, cleanup,
    )


if __name__ == "__main__":
    logging.basicConfig()
    fastagi.log.setLevel(logging.INFO)
    f = fastagi.FastAGIFactory(testFunction)
    reactor.listenTCP(4574, f, 50, '127.0.0.1')  # only binding on local interface
    reactor.run()
