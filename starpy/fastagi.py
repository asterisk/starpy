#
# StarPy -- Asterisk Protocols for Twisted
#
# Copyright (c) 2006, Michael C. Fletcher
#
# Michael C. Fletcher <mcfletch@vrplumber.com>
#
# See http://asterisk-org.github.com/starpy/ for more information about the
# StarPy project. Please do not directly contact any of the maintainers of this
# project for assistance; the project provides a web site, mailing lists and
# IRC channels for your use.
#
# This program is free software, distributed under the terms of the
# BSD 3-Clause License. See the LICENSE file at the top of the source tree for
# details.

"""Asterisk FastAGI server for use from the dialplan

You use an asterisk FastAGI like this from extensions.conf:

    exten => 1000,3,AGI(agi://127.0.0.1:4573,arg1,arg2)

Where 127.0.0.1 is the server and 4573 is the port on which
the server is listening.

Module defines a standard Python logging module log 'FastAGI'
"""
from twisted.internet import protocol, reactor, defer
from twisted.internet import error as tw_error
from twisted.protocols import basic
import socket
import logging
import time
from starpy import error

log = logging.getLogger('FastAGI')

FAILURE_CODE = -1


class FastAGIProtocol(basic.LineOnlyReceiver):
    """Protocol for the interfacing with the Asterisk FastAGI application

    Attributes:

        variables -- for  connected protocol, the set of variables passed
            during initialisation, keys are all-lower-case, set of variables
            returned for an Asterisk 1.2.1 installation on Gentoo on a locally
            connected channel:

                agi_network = 'yes'
                agi_request = 'agi://localhost'
                agi_channel = 'SIP/mike-ccca'
                agi_language = 'en'
                agi_type = 'SIP'
                agi_uniqueid = '1139871605.0'
                agi_callerid = 'mike'
                agi_calleridname = 'Mike Fletcher'
                agi_callingpres = '0'
                agi_callingani2 = '0'
                agi_callington = '0'
                agi_callingtns = '0'
                agi_dnid = '1'
                agi_rdnis = 'unknown'
                agi_context = 'testing'
                agi_extension = '1'
                agi_priority = '1'
                agi_enhanced = '0.0'
                agi_accountcode = ''

        # Internal:
        readingVariables -- whether the instance is still in initialising by
            reading the setup variables from the connection
        messageCache -- stores incoming variables
        pendingMessages -- set of outstanding messages for which we expect
            replies
        lostConnectionDeferred -- deferred firing when the connection is lost
        delimiter -- uses bald newline instead of carriage-return-newline

    XXX Lots of problems with data-escaping, no docs on how to escape special
        characters that I can see...
    """
    readingVariables = False
    lostConnectionDeferred = None
    delimiter = '\n'

    def __init__(self, *args, **named):
        """Initialise the AMIProtocol, arguments are ignored"""
        self.messageCache = []
        self.variables = {}
        self.pendingMessages = []

    def connectionMade(self):
        """(Internal) Handle incoming connection (new AGI request)

        Initiates read of the initial attributes passed by the server
        """
        log.info("New Connection")
        self.readingVariables = True

    def connectionLost(self, reason):
        """(Internal) Handle loss of the connection (remote hangup)"""
        log.info("""Connection terminated""")
        try:
            for df in self.pendingMessages:
                df.errback(tw_error.ConnectionDone(
                        "FastAGI connection terminated"))
        finally:
            if self.lostConnectionDeferred:
                self.lostConnectionDeferred.errback(reason)
            del self.pendingMessages[:]

    def onClose(self):
        """Return a deferred which will fire when the connection is lost"""
        if not self.lostConnectionDeferred:
            self.lostConnectionDeferred = defer.Deferred()
        return self.lostConnectionDeferred

    def lineReceived(self, line):
        """(Internal) Handle Twisted's report of an incoming line from AMI"""
        log.debug('Line In: %r', line)
        if self.readingVariables:
            if not line.strip():
                self.readingVariables = False
                self.factory.mainFunction(self)
            else:
                try:
                    key, value = line.split(':', 1)
                    value = value[1:].rstrip('\n').rstrip('\r')
                except ValueError, err:
                    log.error("""Invalid variable line: %r""", line)
                else:
                    self.variables[key.lower()] = value
                    log.debug("""%s = %r""", key, value)
        else:
            try:
                df = self.pendingMessages.pop(0)
            except IndexError, err:
                log.warn("Line received without pending deferred: %r", line)
            else:
                if line.startswith('200'):
                    line = line[4:]
                    if line.lower().startswith('result='):
                        line = line[7:]
                    df.callback(line)
                else:
                    # XXX parse out the error code
                    try:
                        errCode, line = line.split(' ', 1)
                        errCode = int(errCode)
                    except ValueError, err:
                        errCode = 500
                    df.errback(error.AGICommandFailure(errCode, line))

    def sendCommand(self, commandString):
        """(Internal) Send the given command to the other side"""
        log.info("Send Command: %r", commandString)
        commandString = commandString.rstrip('\n').rstrip('\r')
        df = defer.Deferred()
        self.pendingMessages.append(df)
        self.sendLine(commandString)
        return df

    def checkFailure(self, result, failure='-1'):
        """(Internal) Check for a failure-code, raise error if == result"""
        # result code may have trailing information...
        try:
            resultInt, line = result.split(' ', 1)
        except ValueError, err:
            resultInt = result
        if resultInt.strip() == failure:
            raise error.AGICommandFailure(FAILURE_CODE, result)
        return result

    def resultAsInt(self, result):
        """(Internal) Convert result to an integer value"""
        try:
            return int(result.strip())
        except ValueError, err:
            raise error.AGICommandFailure(FAILURE_CODE, result)

    def secondResultItem(self, result):
        """(Internal) Retrieve the second item on the result-line"""
        return result.split(' ', 1)[1]

    def resultPlusTimeoutFlag(self, resultLine):
        """(Internal) Result followed by optional flag declaring timeout"""
        try:
            digits, timeout = resultLine.split(' ', 1)
            return digits.strip(), True
        except ValueError, err:
            return resultLine.strip(), False

    def dateAsSeconds(self, date):
        """(Internal) Convert date to asterisk-compatible format"""
        if hasattr(date, 'timetuple'):
            # XXX values seem to be off here...
            date = time.mktime(date.timetuple())
        elif isinstance(date, time.struct_time):
            date = time.mktime(date)
        return date

    def onRecordingComplete(self, resultLine):
        """(Internal) Handle putative success

        Also watch for failure-on-load problems
        """
        try:
            digit, exitType, endposStuff = resultLine.split(' ', 2)
        except ValueError, err:
            pass
        else:
            digit = int(digit)
            exitType = exitType.strip('()')
            endposStuff = endposStuff.strip()
            if endposStuff.startswith('endpos='):
                endpos = int(endposStuff[7:].strip())
                return digit, exitType, endpos
        raise ValueError("Unexpected result on streaming completion: %r" %
                         resultLine)

    def onStreamingComplete(self, resultLine, skipMS=0):
        """(Internal) Handle putative success

        Also watch for failure-on-load problems
        """
        try:
            digit, endposStuff = resultLine.split(' ', 1)
        except ValueError, err:
            pass
        else:
            digit = int(digit)
            endposStuff = endposStuff.strip()
            if endposStuff.startswith('endpos='):
                endpos = int(endposStuff[7:].strip())
                if endpos == skipMS:
                    # "likely" an error according to the wiki,
                    # we'll raise an error...
                    raise error.AGICommandFailure(FAILURE_CODE,
                                "End position %s == original position, "
                                "result code %s" % (endpos, digit))
                return digit, endpos
        raise ValueError("Unexpected result on streaming completion: %r" %
                         resultLine)

    def jumpOnError(self, reason, difference=100, forErrors=None):
        """On error, jump to original priority+100

        This is intended to be registered as an errBack on a deferred for
        an end-user application.  It performs the Asterisk-standard-ish
        jump-on-failure operation, jumping to new priority of
        priority+difference.  It also forces return to the same context and
        extension, in case some other piece of code has changed those.

        difference -- priority jump to execute
        forErrors -- if specified, a tuple of error classes to which this
            particular jump is limited (i.e. only errors of this type will
            generate a jump & disconnect)

        returns deferred from the InSequence of operations required to reset
        the address...
        """
        if forErrors:
            if not isinstance(forErrors, (tuple, list)):
                forErrors = (forErrors,)
            reason.trap(*forErrors)
        sequence = InSequence()
        sequence.append(self.setContext, self.variables['agi_context'])
        sequence.append(self.setExtension, self.variables['agi_extension'])
        sequence.append(self.setPriority, int(self.variables['agi_priority'])
                                              + difference)
        sequence.append(self.finish)
        return sequence()

    # End-user API
    def finish(self):
        """Finish the AGI "script" (drop connection)

        This command simply drops the connection to the Asterisk server,
        which the FastAGI protocol interprets as a successful termination.

        Note: There *should* be a mechanism for sending a "result" code,
        but I haven't found any documentation for it.
        """
        self.transport.loseConnection()

    def answer(self):
        """Answer the channel (go off-hook)

        Returns deferred integer response code
        """
        return self.sendCommand("ANSWER").addCallback(
            self.checkFailure
        ).addCallback(self.resultAsInt)

    def channelStatus(self, channel=None):
        """Retrieve the current channel's status

        Result integers (from the wiki):
            0 Channel is down and available
            1 Channel is down, but reserved
            2 Channel is off hook
            3 Digits (or equivalent) have been dialed
            4 Line is ringing
            5 Remote end is ringing
            6 Line is up
            7 Line is busy

        Returns deferred integer result code

        This could be used to decide if we can forward the channel to a given
        user, or whether we need to shunt them off somewhere else.
        """
        if channel:
            command = 'CHANNEL STATUS "%s"' % (channel)
        else:
            command = "CHANNEL STATUS"
        return self.sendCommand(command).addCallback(
            self.checkFailure,
        ).addCallback(self.resultAsInt)

    def onControlStreamFileComplete(self, resultLine):
        """(Internal) Handle CONTROL STREAM FILE results.

        Asterisk 12 introduces 'endpos=' to the result line.
        """
        parts = resultLine.split(' ', 1)
        result = int(parts[0])
        endpos = None # Default if endpos isn't specified
        if len(parts) == 2:
            endposStuff = parts[1].strip()
            if endposStuff.startswith('endpos='):
                endpos = int(endposStuff[7:])
            else:
                log.error("Unexpected response to 'control stream file': %s",
                          resultLine)
        return result, endpos

    def controlStreamFile(
            self, filename, escapeDigits,
            skipMS=0, ffChar='*', rewChar='#', pauseChar=None,
         ):
        """Playback specified file with ability to be controlled by user

        filename -- filename to play (on the asterisk server)
            (don't use file-type extension!)
        escapeDigits -- if provided,
        skipMS -- number of milliseconds to skip on FF/REW
        ffChar -- if provided, the set of chars that fast-forward
        rewChar -- if provided, the set of chars that rewind
        pauseChar -- if provided, the set of chars that pause playback

        returns deferred (digit,endpos) on success, or errors on failure,
            note that digit will be 0 if no digit was pressed AFAICS
        """
        command = 'CONTROL STREAM FILE "%s" %r %s %r %r' % (
            filename, escapeDigits, skipMS, ffChar, rewChar
        )
        if pauseChar:
            command += ' %r' % (pauseChar)

        return self.sendCommand(command).addCallback(self.checkFailure) \
            .addCallback(self.onControlStreamFileComplete)

    def databaseDel(self, family, key):
        """Delete the given key from the database

        Returns deferred integer result code
        """
        command = 'DATABASE DEL "%s" "%s"' % (family, key)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='0',
        ).addCallback(self.resultAsInt)

    def databaseDeltree(self, family, keyTree=None):
        """Delete an entire family or a tree within a family from database

        Returns deferred integer result code
        """
        command = 'DATABASE DELTREE "%s"' % (family,)
        if keyTree:
            command += ' "%s"' % (keytree,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='0',
        ).addCallback(self.resultAsInt)

    def databaseGet(self, family, key):
        """Retrieve value of the given key from database

        Returns deferred string value for the key
        """
        command = 'DATABASE GET "%s" "%s"' % (family, key)

        def returnValue(resultLine):
            # get the second item without the brackets...
            return resultLine[1:-1]

        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='0',
        ).addCallback(self.secondResultItem).addCallback(returnValue)

    def databaseSet(self, family, key, value):
        """Set value of the given key to database

        a.k.a databasePut on the asterisk side

        Returns deferred integer result code
        """
        command = 'DATABASE PUT "%s" "%s" "%s"' % (family, key, value)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='0',
        ).addCallback(self.resultAsInt)
    databasePut = databaseSet

    def execute(self, application, *options, **kwargs):
        """Execute a dialplan application with given options

        Note: asterisk calls this "exec", which is Python keyword

        comma_delimiter -- Use new style comma delimiter for diaplan
        application arguments.  Asterisk uses pipes in 1.4 and older and
        prefers commas in 1.6 and up.  Pass comma_delimiter=True to avoid
        warnings from Asterisk 1.6 and up.

        Returns deferred string result for the application, which
        may have failed, result values are application dependant.
        """
        command = '''EXEC "%s"''' % (application)
        if options:
            if kwargs.pop('comma_delimiter', False) is True:
                delimiter = ","
            else:
                delimiter = "|"

            command += ' "%s"' % (
                delimiter.join([
                    str(x) for x in options
                ])
            )
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-2',
        )

    def getData(self, filename, timeout=2.000, maxDigits=None):
        """Playback file, collecting up to maxDigits or waiting up to timeout

        filename -- filename without extension to play
        timeout -- timeout in seconds (Asterisk uses milliseconds)
        maxDigits -- maximum number of digits to collect

        returns deferred (str(digits), bool(timedOut))
        """
        timeout *= 1000
        command = '''GET DATA "%s" %s''' % (filename, timeout)
        if maxDigits is not None:
            command = ' '.join([command, str(maxDigits)])
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultPlusTimeoutFlag)

    def getOption(self, filename, escapeDigits, timeout=None):
        """Playback file, collect 1 digit or timeout (return 0)

        filename -- filename to play
        escapeDigits -- digits which cancel playback/recording
        timeout -- timeout in seconds (Asterisk uses milliseconds)

        returns (chr(option) or '' on timeout, endpos)
        """
        command = '''GET OPTION "%s" %r''' % (filename, escapeDigits)
        if timeout is not None:
            timeout *= 1000
            command += ' %s' % (timeout,)

        def charFirst((c, position)):
            if not c:  # returns 0 on timeout
                c = ''
            else:
                c = chr(c)
            return c, position

        return self.sendCommand(command).addCallback(
            self.checkFailure,
        ).addCallback(
            self.onStreamingComplete
        ).addCallback(charFirst)

    def getVariable(self, variable):
        """Retrieve the given channel variable

        From the wiki, variables of interest:

            ACCOUNTCODE -- Account code, if specified
            ANSWEREDTIME -- Time call was answered
            BLINDTRANSFER -- Active SIP channel that dialed the number.
                This will return the SIP Channel that dialed the number when
                doing blind transfers
            CALLERID -- Current Caller ID (name and number) # deprecated?
            CALLINGPRES -- PRI Call ID Presentation variable for incoming calls
            CHANNEL -- Current channel name
            CONTEXT -- Current context name
            DATETIME -- Current datetime in format: DDMMYYYY-HH:MM:SS
            DIALEDPEERNAME -- Name of called party (Broken)
            DIALEDPEERNUMBER -- Number of the called party (Broken)
            DIALEDTIME -- Time number was dialed
            DIALSTATUS -- Status of the call
            DNID -- Dialed Number Identifier (limited apparently)
            EPOCH -- UNIX-style epoch-based time (seconds since 1 Jan 1970)
            EXTEN -- Current extension
            HANGUPCAUSE -- Last hangup return code on a Zap channel connected
                to a PRI interface
            INVALID_EXTEN -- Extension asked for when redirected to the i
                (invalid) extension
            LANGUAGE -- The current language setting. See Asterisk
                multi-language
            MEETMESECS -- Number of seconds user participated in a MeetMe
                conference
            PRIORITY -- Current priority
            RDNIS -- The current redirecting DNIS, Caller ID that redirected
                the call. Limitations apply.
            SIPDOMAIN -- SIP destination domain of an inbound call
                (if appropriate)
            SIP_CODEC -- Used to set the SIP codec for a call (apparently
                broken in Ver 1.0.1, ok in Ver. 1.0.3 & 1.0.4, not sure about
                1.0.2)
            SIPCALLID -- SIP dialog Call-ID: header
            SIPUSERAGENT -- SIP user agent header (remote agent)
            TIMESTAMP -- Current datetime in the format: YYYYMMDD-HHMMSS
            TXTCIDNAME -- Result of application TXTCIDName
            UNIQUEID -- Current call unique identifier
            TOUCH_MONITOR -- Used for "one touch record" (see features.conf,
                and wW dial flags). If is set on either side of the call then
                that var contains the app_args for app_monitor otherwise the
                default of WAV||m is used

        Returns deferred string value for the key
        """
        def stripBrackets(value):
            return value.strip()[1:-1]
        command = '''GET VARIABLE "%s"''' % (variable,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='0',
        ).addCallback(self.secondResultItem).addCallback(stripBrackets)

    def hangup(self, channel=None):
        """Cause the server to hang up on the channel

        Returns deferred integer response code

        Note: This command just doesn't seem to work with Asterisk 1.2.1,
        connected channels just remain connected.
        """
        command = "HANGUP"
        if channel is not None:
            command += ' "%s"' % (channel)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def noop(self, message=None):
        """Send a null operation to the server.  Any message sent
        will be printed to the CLI.

        Returns deferred integer response code
        """
        command = "NOOP"
        if message is not None:
            command += ' "%s"' % message
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def playback(self, filename, doAnswer=1):
        """Playback specified file in foreground

        filename -- filename to play
        doAnswer -- whether to:
                -1: skip playback if the channel is not answered
                 0: playback the sound file without answering first
                 1: answer the channel before playback, if not yet answered

        Note: this just wraps the execute method to issue
        a PLAYBACK command.

        Returns deferred integer response code
        """
        try:
            option = {-1: 'skip', 0: 'noanswer', 1: 'answer'}[doAnswer]
        except KeyError:
            raise TypeError("doAnswer accepts values -1, 0, "
                            "1 only (%s given)" % doAnswer)
        command = 'PLAYBACK "%s"' % (filename,)
        if option:
            command += ' "%s"' % (option,)
        return self.execute(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def receiveChar(self, timeout=None):
        """Receive a single text char on text-supporting channels (rare)

        timeout -- timeout in seconds (Asterisk uses milliseconds)

        returns deferred (char, bool(timeout))
        """
        command = '''RECEIVE CHAR'''
        if timeout is not None:
            timeout *= 1000
            command += ' %s' % (timeout,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultPlusTimeoutFlag)

    def receiveText(self, timeout=None):
        """Receive text until timeout

        timeout -- timeout in seconds (Asterisk uses milliseconds)

        Returns deferred string response value (unaltered)
        """
        command = '''RECEIVE TEXT'''
        if timeout is not None:
            timeout *= 1000
            command += ' %s' % (timeout,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        )

    def recordFile(
            self, filename, format, escapeDigits, timeout=-1,
            offsetSamples=None, beep=True, silence=None,
        ):
        """Record channel to given filename until escapeDigits or silence

        filename -- filename on the server to which to save
        format -- encoding format in which to save data
        escapeDigits -- digits which end recording
        timeout -- maximum time to record in seconds, -1 gives infinite
            (Asterisk uses milliseconds)
        offsetSamples - move into file this number of samples before recording?
            XXX check semantics here.
        beep -- if true, play a Beep on channel to indicate start of recording
        silence -- if specified, silence duration to trigger end of recording

        returns deferred (str(code/digits), typeOfExit, endpos)

        Where known typeOfExits include:
            hangup, code='0'
            dtmf, code=digits-pressed
            timeout, code='0'
        """
        timeout *= 1000
        command = '''RECORD FILE "%s" "%s" %s %s''' % (
            filename, format, escapeDigits, timeout,
        )
        if offsetSamples is not None:
            command += ' %s' % (offsetSamples,)
        if beep:
            command += ' BEEP'
        if silence is not None:
            command += ' s=%s' % (silence,)

        def onResult(resultLine):
            value, type, endpos = resultLine.split(' ')
            type = type.strip()[1:-1]
            endpos = int(endpos.split('=')[1])
            return (value, type, endpos)

        return self.sendCommand(command).addCallback(
            self.onRecordingComplete
        )

    def sayXXX(self, baseCommand, value, escapeDigits=''):
        """Underlying implementation for the common-api sayXXX functions"""
        command = '%s %s %r' % (baseCommand, value, escapeDigits or '')
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def sayAlpha(self, string, escapeDigits=None):
        """Spell out character string to the user until escapeDigits

        returns deferred 0 or the digit pressed
        """
        string = "".join([x for x in string if x.isalnum()])
        return self.sayXXX('SAY ALPHA', string, escapeDigits)

    def sayDate(self, date, escapeDigits=None):
        """Spell out the date (with somewhat unnatural form)

        See sayDateTime with format 'ABdY' for a more natural reading

        returns deferred 0 or digit-pressed as integer
        """
        return self.sayXXX('SAY DATE', self.dateAsSeconds(date), escapeDigits)

    def sayDigits(self, number, escapeDigits=None):
        """Spell out the number/string as a string of digits

        returns deferred 0 or digit-pressed as integer
        """
        number = "".join([x for x in str(number) if x.isdigit()])
        return self.sayXXX('SAY DIGITS', number, escapeDigits)

    def sayNumber(self, number, escapeDigits=None):
        """Say a number in natural form

         returns deferred 0 or digit-pressed as integer
        """
        number = "".join([x for x in str(number) if x.isdigit()])
        return self.sayXXX('SAY NUMBER', number, escapeDigits)

    def sayPhonetic(self, string, escapeDigits=None):
        """Say string using phonetics

         returns deferred 0 or digit-pressed as integer
        """
        string = "".join([x for x in string if x.isalnum()])
        return self.sayXXX('SAY PHONETIC', string, escapeDigits)

    def sayTime(self, time, escapeDigits=None):
        """Say string using phonetics

         returns deferred 0 or digit-pressed as integer
        """
        return self.sayXXX('SAY TIME', self.dateAsSeconds(time), escapeDigits)

    def sayDateTime(self, time, escapeDigits='', format=None, timezone=None):
        """Say given date/time in given format until escapeDigits

        time -- datetime or float-seconds-since-epoch
        escapeDigits -- digits to cancel playback
        format -- strftime-style format for the date to be read
            'filename' -- filename of a soundfile (single ticks around the
                          filename required)
            A or a -- Day of week (Saturday, Sunday, ...)
            B or b or h -- Month name (January, February, ...)
            d or e -- numeric day of month (first, second, ..., thirty-first)
            Y -- Year
            I or l -- Hour, 12 hour clock
            H -- Hour, 24 hour clock (single digit hours preceded by "oh")
            k -- Hour, 24 hour clock (single digit hours NOT preceded by "oh")
            M -- Minute
            P or p -- AM or PM
            Q -- "today", "yesterday" or ABdY
                 (*note: not standard strftime value)
            q -- "" (for today), "yesterday", weekday, or ABdY
                 (*note: not standard strftime value)
            R -- 24 hour time, including minute

            Default format is "ABdY 'digits/at' IMp"
        timezone -- optional timezone name from /usr/share/zoneinfo

        returns deferred 0 or digit-pressed as integer
        """
        command = 'SAY DATETIME %s %r' % (self.dateAsSeconds(time),
                                          escapeDigits)
        if format is not None:
            command += ' %s' % (format,)
            if timezone is not None:
                command += ' %s' % (timezone,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def sendImage(self, filename):
        """Send image on those channels which support sending images (rare)

        returns deferred integer result code
        """
        command = 'SEND IMAGE "%s"' % (filename,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def sendText(self, text):
        """Send text on text-supporting channels (rare)

        returns deferred integer result code
        """
        command = "SEND TEXT %r" % (text)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def setAutoHangup(self, time):
        """Set channel to automatically hang up after time seconds

        time -- time in seconds in the future to hang up...

        returns deferred integer result code
        """
        command = """SET AUTOHANGUP %s""" % (time,)
        return self.sendCommand(command).addCallback(
            # docs don't show a failure case, actually
            self.checkFailure, failure='-1',
        ).addCallback(self.resultAsInt)

    def setCallerID(self, number):
        """Set channel's caller ID to given number

        returns deferred integer result code
        """
        command = "SET CALLERID %s" % (number)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def setContext(self, context):
        """Move channel to given context (no error checking is performed)

        returns deferred integer result code
        """
        command = """SET CONTEXT %s""" % (context,)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def setExtension(self, extension):
        """Move channel to given extension (or 'i' if invalid)

        The call will drop if neither the extension or 'i' are there.

        returns deferred integer result code
        """
        command = """SET EXTENSION %s""" % (extension,)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def setMusic(self, on=True, musicClass=None):
        """Enable/disable and/or choose music class for channel's music-on-hold

        returns deferred integer result code
        """
        command = """SET MUSIC %s""" % (['OFF', 'ON'][on],)
        if musicClass is not None:
            command += " %s" % (musicClass,)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def setPriority(self, priority):
        """Move channel to given priority or drop if not there

        returns deferred integer result code
        """
        command = """SET PRIORITY %s""" % (priority,)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def setVariable(self, variable, value):
        """Set given channel variable to given value

        variable -- the variable name passed to the server
        value -- the variable value passed to the server, will have
            any '"' characters removed in order to allow for " quoting
            of the value.

        returns deferred integer result code
        """
        value = '''"%s"''' % (str(value).replace('"', ''),)
        command = 'SET VARIABLE "%s" "%s"' % (variable, value)
        return self.sendCommand(command).addCallback(self.resultAsInt)

    def streamFile(self, filename, escapeDigits="", offset=0):
        """Stream given file until escapeDigits starting from offset

        returns deferred (str(digit), int(endpos)) for playback

        Note: streamFile is apparently unstable in AGI, may want to use
        execute('PLAYBACK', ...) instead (according to the Wiki)
        """
        command = 'STREAM FILE "%s" %r' % (filename, escapeDigits)
        if offset is not None:
            command += ' %s' % (offset)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(self.onStreamingComplete, skipMS=offset)

    def tddMode(self, on=True):
        """Set TDD mode on the channel if possible (ZAP only ATM)

        on -- ON (True), OFF (False) or MATE (None)

        returns deferred integer result code
        """
        if on is True:
            on = 'ON'
        elif on is False:
            on = 'OFF'
        elif on is None:
            on = 'MATE'
        command = 'TDD MODE %s' % (on,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',  # failure
        ).addCallback(
            # planned eventual failure case (not capable)
            self.checkFailure, failure='0',
        ).addCallback(
            self.resultAsInt,
        )

    def verbose(self, message, level=None):
        """Send a logging message to the asterisk console for debugging etc

        message -- text to pass
        level -- 1-4 denoting verbosity level

        returns deferred integer result code
        """
        command = 'VERBOSE %r' % (message,)
        if level is not None:
            command += ' %s' % (level)
        return self.sendCommand(command).addCallback(
            self.resultAsInt,
        )

    def waitForDigit(self, timeout):
        """Wait up to timeout seconds for single digit to be pressed

        timeout -- timeout in seconds or -1 for infinite timeout
            (Asterisk uses milliseconds)

        returns deferred 0 on timeout or digit
        """
        timeout *= 1000
        command = "WAIT FOR DIGIT %s" % (timeout,)
        return self.sendCommand(command).addCallback(
            self.checkFailure, failure='-1',
        ).addCallback(
            self.resultAsInt,
        )

    def wait(self, duration):
        """Wait for X seconds

        (just a wrapper around callLater, doesn't talk to server)

        returns deferred which fires some time after duration seconds have
        passed
        """
        df = defer.Deferred()
        reactor.callLater(duration, df.callback, 0)
        return df


class InSequence(object):
    """Single-shot item creating a set of actions to run in sequence"""
    def __init__(self):
        self.actions = []
        self.results = []
        self.finalDF = None

    def append(self, function, *args, **named):
        """Append an action to the set of actions to process"""
        self.actions.append((function, args, named))

    def __call__(self):
        """Return deferred that fires when finished processing all items"""
        return self._doSequence()

    def _doSequence(self):
        """Return a deferred that does each action in sequence"""
        finalDF = defer.Deferred()
        self.onActionSuccess(None, finalDF=finalDF)
        return finalDF

    def recordResult(self, result):
        """Record the result for later"""
        self.results.append(result)
        return result

    def onActionSuccess(self, result, finalDF):
        """Handle individual-action success"""
        log.debug('onActionSuccess: %s', result)
        if self.actions:
            action = self.actions.pop(0)
            log.debug('action %s', action)
            df = defer.maybeDeferred(action[0], *action[1], **action[2])
            df.addCallback(self.recordResult)
            df.addCallback(self.onActionSuccess, finalDF=finalDF)
            df.addErrback(self.onActionFailure, finalDF=finalDF)
            return df
        else:
            finalDF.callback(self.results)

    def onActionFailure(self, reason, finalDF):
        """Handle individual-action failure"""
        log.debug('onActionFailure')
        reason.results = self.results
        finalDF.errback(reason)


class FastAGIFactory(protocol.Factory):
    """Factory generating FastAGI server instances
    """
    protocol = FastAGIProtocol

    def __init__(self, mainFunction):
        """Initialise the factory

        mainFunction -- function taking a connected FastAGIProtocol instance
            this is the function that's run when the Asterisk server connects.
        """
        self.mainFunction = mainFunction
