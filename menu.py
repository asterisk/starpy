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

"""IVR-based menuing system with retry, exit, and similar useful features

You use the menuing system by instantiating Interaction and Option sub-classes
as a tree of options that make up an IVR menu.  Calling the top-level menu
produces a Deferred that fires with a list of [(Option,value),...] pairs,
where Option is the thing chosen and value is the value entered by the user
for choosing that option.

When programming an IVR you will likely want to make Option sub-classes that
are callable to accomplish the task indicated by the user.

XXX allow for starting the menu system anywhere in the hierarchy
XXX add the reject/accept menus to the CollectDigits (requires soundfiles
in standard locations on the server, complicates install)
"""
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi, utilapplication, error
import os, logging, pprint, time
from basicproperty import common, propertied, basic

log = logging.getLogger( 'menu' )
log.setLevel( logging.DEBUG )

class Interaction( propertied.Propertied ):
    """Base class for user-interaction operations"""
    ALL_DIGITS = '0123456789*#'
    timeout = common.FloatProperty(
        "timeout", """Duration to wait for response before repeating message""",
        defaultValue = 5,
    )
    maxRepetitions = common.IntegerProperty(
        "maxRepetitions", """Maximum number of times to play before failure""",
        defaultValue = 5,
    )
    onSuccess = basic.BasicProperty(
        "onSuccess", """Optional callback for success with signature method( result, runner )""",
    )
    onFailure = basic.BasicProperty(
        "onFailure", """Optional callback for failure with signature method( result, runner )""",
    )
    runnerClass = None
    def __call__( self, agi, *args, **named ):
        """Initiate AGI-based interaction with the user"""
        return self.runnerClass( model=self,agi=agi )( *args, **named )

class Runner( propertied.Propertied ):
    """User's interaction with a given Interaction-type"""
    agi = basic.BasicProperty(
        "agi", """The AGI instance we use to communicate with the user""",
    )
    def defaultFinalDF( prop, client ):
        """Produce the default finalDF with onSuccess/onFailure support"""
        df = defer.Deferred()
        model = client.model
        if hasattr( model, 'onSuccess' ):
            log.debug( 'register onSuccess: %s', model.onSuccess )
            df.addCallback( model.onSuccess, runner=client )
        if hasattr( model, 'onFailure' ):
            log.debug( 'register onFailure: %s', model.onFailure )
            df.addErrback( model.onFailure, runner=client )
        return df
    finalDF = basic.BasicProperty(
        "finalDF", """Final deferred we will callback/errback on success/failure""",
        defaultFunction = defaultFinalDF,
    )
    del defaultFinalDF

    alreadyRepeated = common.IntegerProperty(
        "alreadyRepeated", """Number of times we've repeated the message...""",
        defaultValue = 0,
    )
    model = basic.BasicProperty(
        "model", """The data-model that we are presenting to the user (e.g. Menu)""",
    )
    def returnResult( self, result ):
        """Return result of deferred to our original caller"""
        log.debug( 'returnResult: %s %s', self.model,result )
        if not self.finalDF.called:
            self.finalDF.debug = True
            self.finalDF.callback( result )
        else:
            log.debug( 'finalDF already called, ignoring %s', result )
        return result
    def returnError( self, reason ):
        """Return failure of deferred to our original caller"""
        log.debug( 'returnError: %s', self.model )
        if not isinstance( reason.value, error.MenuExit ):
            log.warn( """Failure during menu: %s""", reason.getTraceback())
        if not self.finalDF.called:
            self.finalDF.debug = True
            self.finalDF.errback( reason )
        else:
            log.debug( 'finalDF already called, ignoring %s', reason.getTraceback() )

    def promptAsRunner( self, prompt ):
        """Take set of prompt-compatible objects and produce a PromptRunner for them"""
        realPrompt = []
        for p in prompt:
            if isinstance( p, (str,unicode)):
                p = AudioPrompt( p )
            elif isinstance( p, int ):
                p = NumberPrompt( p )
            elif not isinstance( p, Prompt ):
                raise TypeError( """Unknown prompt element type on %r: %s"""%(
                    p, p.__class__,
                ))
            realPrompt.append( p )
        return PromptRunner(
            elements = realPrompt,
            escapeDigits = self.escapeDigits,
            agi = self.agi,
            timeout = self.model.timeout,
        )

class CollectDigitsRunner( Runner ):
    """User's single interaction to enter a set of digits

    Note: Asterisk is hard-coded to use # to exit the entry-mode...
    """
    def __call__( self, *args, **named ):
        """Begin the AGI processing for the menu"""
        self.readDigits()
        return self.finalDF
    def readDigits( self, result=None ):
        """Begin process of reading digits from the user"""
        soundFile = getattr( self.model, 'soundFile', None )
        if soundFile:
            # easiest possibility, just read out the file...
            return self.agi.getData(
                soundFile, timeout=self.model.timeout,
                maxDigits = getattr( self.model, 'maxDigits', None ),
            ).addCallback( self.onReadDigits ).addErrback( self.returnError )
        else:
            raise NotImplemented( """Haven't got non-soundfile menus working yet""" )

        self.agi.getData( self.menu. filename, timeout=2.000, maxDigits=None )
    def validEntry( self, digits ):
        """Determine whether given digits are considered a "valid" entry"""
        minDigits = getattr( self.model, 'minDigits', None )
        if minDigits is not None:
            if len(digits) < minDigits:
                return False, 'Too few digits'
        return True, None
    def onReadDigits( self, (digits,timeout) ):
        """Deal with succesful result from reading digits"""
        log.info( """onReadDigits: %r, %s""", digits, timeout )
        valid, reason = self.validEntry( digits )
        if (not digits) and (not timeout):
            # user pressed #
            raise error.MenuExit(
                self.model,
                """User cancelled entry of digits""",
            )
        if not valid:
            if self.model.tellInvalid:
                # this should be a menu, letting the user decide to re-enter,
                # or cancel entry
                pass
            self.alreadyRepeated += 1
            if self.alreadyRepeated >= self.model.maxRepetitions:
                log.warn( """User did not complete digit-entry for %s, timing out""", self.model )
                raise error.MenuTimeout(
                    self.model,
                    """User did not finish digit-entry in %s passes of collection"""%(
                        self.alreadyRepeated,
                    )
                )
            return self.readDigits()
        else:
            # Yay, we got a valid response!
            return self.returnResult( [(self, digits) ] )

class CollectPasswordRunner( CollectDigitsRunner ):
    """Password-runner, checks validity versus expected value"""
    expected = common.StringLocaleProperty(
        "expected", """The value expected/required from the user for this run""",
    )
    def __call__( self, expected, *args, **named ):
        """Begin the AGI processing for the menu"""
        self.expected = expected
        return super( CollectPasswordRunner, self ).__call__( *args, **named )
    def validEntry( self, digits ):
        """Determine whether given digits are considered a "valid" entry"""
        for digit in self.model.escapeDigits:
            if digit in digits:
                raise error.MenuExit(
                    self.model,
                    """User cancelled entry of password""",
                )
        if digits != self.expected:
            return False, "Password doesn't match"
        return True, None

class CollectAudioRunner( Runner ):
    """Audio-collection runner, records user audio to a file on the asterisk server"""
    escapeDigits = common.StringLocaleProperty(
        "escapeDigits", """Set of digits which escape from recording""",
        defaultFunction = lambda prop,client: client.model.escapeDigits,
        setDefaultOnGet = False,
    )
    def __call__( self, *args, **named ):
        """Begin the AGI processing for the menu"""
        self.readPrompt()
        return self.finalDF
    def readPrompt( self, result=None ):
        """Begin process of reading audio from the user"""
        if self.model.prompt:
            # wants us to read a prompt to the user before recording...
            runner = self.promptAsRunner( self.model.prompt )
            runner.timeout = 0.1
            return runner().addCallback( self.onReadPrompt ).addErrback( self.returnError )
        else:
            return self.collectAudio().addErrback( self.returnError )
    def onReadPrompt( self, result ):
        """We've finished reading the prompt to the user, check for escape"""
        log.info( 'Finished reading prompt for collect audio: %r', result )
        if result and result in self.escapeDigits:
            raise error.MenuExit(
                self.model,
                """User cancelled entry of audio during prompt""",
            )
        else:
            return self.collectAudio()
    def collectAudio( self ):
        """We're supposed to record audio from the user with our model's parameters"""
        # XXX use a temporary file for recording the audio, then move to final destination
        log.debug( 'collectAudio' )
        if hasattr( self.model, 'temporaryFile' ):
            filename = self.model.temporaryFile
        else:
            filename = self.model.filename
        df = self.agi.recordFile(
            filename=filename,
            format=self.model.format,
            escapeDigits=self.escapeDigits,
            timeout=self.model.timeout,
            offsetSamples=None,
            beep=self.model.beep,
            silence=self.model.silence,
        ).addCallbacks(
            self.onAudioCollected, self.onAudioCollectFail,
        )
        if hasattr( self.model, 'temporaryFile' ):
            df.addCallback( self.moveToFinal )
        return df
    def onAudioCollected( self, result ):
        """Process the results of collecting the audio"""
        digits, typeOfExit, endpos = result
        if typeOfExit in ('hangup','timeout'):
            # expected common-case for recording...
            return self.returnResult( (self,(digits,typeOfExit,endpos)) )
        elif typeOfExit =='dtmf':
            raise error.MenuExit(
                self.model,
                """User cancelled entry of audio""",
            )
        else:
            raise ValueError( """Unrecognised recordFile results: (%s, %s %s)"""%(
                digits, typeOfExit, endpos,
            ))
    def onAudioCollectFail( self, reason ):
        """Process failure to record audio"""
        log.error(
            """Failure collecting audio for CollectAudio instance %s: %s""",
            self.model, reason.getTraceback(),
        )
        return reason # re-raise the error...
    def moveToFinal( self, result ):
        """On succesful recording, move temporaryFile to final file"""
        log.info(
            'Moving recorded audio %r to final destination %r',
            self.model.temporaryFile, self.model.filename
        )
        import os
        try:
            os.rename(
                '%s.%s'%(self.model.temporaryFile,self.model.format),
                '%s.%s'%(self.model.filename,self.model.format),
            )
        except (OSError, IOError), err:
            log.error(
                """Unable to move temporary recording file %r to target file %r: %s""",
                self.model.temporaryFile, self.model.filename,
                # XXX would like to use getException here...
                err,
            )
            raise
        return result


class MenuRunner( Runner ):
    """User's single interaction with a given menu"""
    def defaultEscapeDigits( prop, client ):
        """Return the default escape digits for the given client"""
        if client.model.tellInvalid:
            escapeDigits = client.model.ALL_DIGITS
        else:
            escapeDigits = "".join( [o.option for o in client.model.options] )
        return escapeDigits
    escapeDigits = common.StringLocaleProperty(
        "escapeDigits", """Set of digits which escape from prompts to choose option""",
        defaultFunction = defaultEscapeDigits,
    )
    del defaultEscapeDigits # clean up namespace

    def __call__( self, *args, **named ):
        """Begin the AGI processing for the menu"""
        self.readMenu()
        return self.finalDF
    def readMenu( self, result=None ):
        """Read our menu to the user"""
        runner = self.promptAsRunner( self.model.prompt )
        return runner().addCallback( self.onReadMenu ).addErrback( self.returnError )
    def onReadMenu( self, pressed ):
        """Deal with succesful result from reading menu"""
        log.info( """onReadMenu: %r""", pressed )
        if not pressed:
            self.alreadyRepeated += 1
            if self.alreadyRepeated >= self.model.maxRepetitions:
                log.warn( """User did not complete menu selection for %s, timing out""", self.model )
                if not self.finalDF.called:
                    raise error.MenuTimeout(
                        self.model,
                        """User did not finish selection in %s passes of menu"""%(
                            self.alreadyRepeated,
                        )
                    )
                return None
            return self.readMenu()
        else:
            # Yay, we got an escape-key pressed
            for option in self.model.options:
                if pressed in option.option:
                    if callable( option ):
                        # allow for chaining down into sub-menus and the like...
                        # we return the result of calling the option via self.finalDF
                        return defer.maybeDeferred( option, pressed, self ).addCallbacks(
                            self.returnResult, self.returnError
                        )
                    elif hasattr(option, 'onSuccess' ):
                        return defer.maybeDeferred( option.onSuccess, pressed, self ).addCallbacks(
                            self.returnResult, self.returnError
                        )
                    else:
                        return self.returnResult( [(option,pressed),] )
            # but it wasn't anything we expected...
            if not self.model.tellInvalid:
                raise error.MenuUnexpectedOption(
                    self.model, """User somehow selected %r, which isn't a recognised option?"""%(pressed,),
                )
            else:
                return self.agi.getOption(
                    self.model.INVALID_OPTION_FILE, self.escapeDigits,
                    timeout=0,
                ).addCallback( self.readMenu ).addErrback( self.returnError )

class Menu( Interaction ):
    """IVR-based menu, returns options selected by the user and keypresses

    The Menu holds a collection of Option instances along with a prompt
    which presents those options to the user.  The menu will attempt to
    collect the user's selected option up to maxRepetitions times, playing
    the prompt each time.

    If tellInvalid is true, will allow any character being pressed to stop
    the playback, and will tell the user if the pressed character is not
    recognised.  Otherwise will simply ignore a pressed character which isn't
    part of an Option object's 'option' property.

    The menu will chain into callable Options, so that SubMenu and ExitOn can
    be used to produce effects such as multi-level menus with options to
    return to the parent menu level.

    Returns [(option,char(pressedKey))...] for each level of menu explored
    """
    INVALID_OPTION_FILE = 'pm-invalid-option'
    prompt = common.ListProperty(
        "prompt", """(Set of) prompts to run, can be Prompt instances or filenames

        Used by the PromptRunner to produce prompt selections
        """,
    )
    textPrompt = common.StringProperty(
        "textPrompt", """Textual prompt describing the option""",
    )
    options = common.ListProperty(
        "options", """Set of options the user may select""",
    )
    tellInvalid = common.IntegerProperty(
        "tellInvalid", """Whether to tell the user that their selection is unrecognised""",
        defaultValue = True,
    )
    runnerClass = MenuRunner
class Option( propertied.Propertied ):
    """A single menu option that can be chosen by the user"""
    option = common.StringLocaleProperty(
        "option", """Keypad values which select this option (list of characters)""",
    )
class SubMenu( Option ):
    """A menu-holding option, just forwards call to the held menu"""
    menu = basic.BasicProperty(
        "menu", """The sub-menu we are presenting to the user""",
    )
    def __call__( self, pressed, parent ):
        """Get result from the sub-menu, add ourselves into the result"""
        def onResult( result ):
            log.debug( """Child menu %s result: %s""", self.menu, result )
            result.insert( 0, (self,pressed) )
            return result
        def onFailure( reason ):
            """Trap voluntary exit and re-start the parent menu"""
            reason.trap( error.MenuExit )
            log.warn( """Restarting parent menu: %s""", parent )
            return parent.model( parent.agi )
        return self.menu( parent.agi ).addCallbacks( onResult, onFailure )
class ExitOn( Option ):
    """An option which exits from the current menu level"""
    def __call__( self, pressed, parent ):
        """Raise a MenuExit error"""
        raise error.MenuExit(
            self, pressed, parent,  """User selected ExitOn option""",
        )

class CollectDigits( Interaction ):
    """Collects some number of digits (e.g. an extension) from user"""
    soundFile = common.StringLocaleProperty(
        "soundFile", """File (name) for the pre-recorded blurb""",
    )
    textPrompt = common.StringProperty(
        "textPrompt", """Textual prompt describing the option""",
    )
    readBack = common.BooleanProperty(
        "readBack", """Whether to read the entered value back to the user""",
        defaultValue = False,
    )
    minDigits = common.IntegerProperty(
        "minDigits", """Minimum number of digits to collect (only restricted if specified)""",
    )
    maxDigits = common.IntegerProperty(
        "maxDigits", """Maximum number of digits to collect (only restricted if specified)""",
    )
    runnerClass = CollectDigitsRunner
    tellInvalid = common.IntegerProperty(
        "tellInvalid", """Whether to tell the user that their selection is unrecognised""",
        defaultValue = True,
    )

class CollectPassword( CollectDigits ):
    """Collects some number of password digits from the user"""
    runnerClass = CollectPasswordRunner
    escapeDigits = common.StringLocaleProperty(
        "escapeDigits", """Set of digits which escape from password entry""",
        defaultValue = '',
    )
    soundFile = common.StringLocaleProperty(
        "soundFile", """File (name) for the pre-recorded blurb""",
        defaultValue = 'vm-password',
    )

class CollectAudio( Interaction ):
    """Collects audio file from the user"""
    prompt = common.ListProperty(
        "prompt", """(Set of) prompts to run, can be Prompt instances or filenames

        Used by the PromptRunner to produce prompt selections
        """,
    )
    textPrompt = common.StringProperty(
        "textPrompt", """Textual prompt describing the option""",
    )
    temporaryFile = common.StringLocaleProperty(
        "temporaryFile", """Temporary file into which to record the audio before moving to filename""",
    )
    filename = common.StringLocaleProperty(
        "filename", """Final filename into which to record the file...""",
    )
    deleteOnFail = common.BooleanProperty(
        "deleteOnFail", """Whether to delete failed attempts to record a file""",
        defaultValue = True
    )
    escapeDigits = common.StringLocaleProperty(
        "escapeDigits", """Set of digits which escape from recording the file""",
        defaultValue = '#*0123456789',
    )
    timeout = common.FloatProperty(
        "timeout", """Duration to wait for recording (maximum record time)""",
        defaultValue = 60,
    )
    silence = common.FloatProperty(
        "silence", """Duration to wait for recording (maximum record time)""",
        defaultValue = 5,
    )
    beep = common.BooleanProperty(
        "beep", """Whether to play a "beep" sound at beginning of recording""",
        defaultValue = True,
    )
    runnerClass = CollectAudioRunner

class PromptRunner( propertied.Propertied ):
    """Prompt formed from list of sub-prompts
    """
    elements = common.ListProperty(
        "elements", """Sub-elements of the prompt to be presented""",
    )
    agi = basic.BasicProperty(
        "agi", """The FastAGI instance we're controlling""",
    )
    escapeDigits = common.StringLocaleProperty(
        "escapeDigits", """Set of digits which escape from playing the prompt""",
    )
    timeout = common.FloatProperty(
        "timeout", """Timeout on data-entry after completed reading""",
    )
    def __call__( self ):
        """Return a deferred that chains all of the sub-prompts in order

        Returns from the first of the sub-prompts that recevies a selection

        returns str(digit) for the key the user pressed
        """
        return self.onNext( None )
    def onNext( self, result, index=0 ):
        """Process the next operation"""
        if result is not None:
            return result
        try:
            element = self.elements[index]
        except IndexError, err:
            # okay, do a waitForDigit from timeout seconds...
            return self.agi.waitForDigit( self.timeout ).addCallback(
                self.processKey
            ).addCallback( self.processLast )
        else:
            df = element.read( self.agi, self.escapeDigits )
            df.addCallback( self.processKey )
            df.addCallback( self.onNext, index=index+1)
            return df
    def processKey( self, result ):
        """Does the pressed key belong to escapeDigits?"""
        if isinstance( result, tuple ):
            # getOption result...
            if result[1] == 0:
                # failure during load of the file...
                log.warn( """Apparent failure during load of audio file: %s""", self.value )
                result = 0
            else:
                result = result[0]
            if isinstance( result, str ):
                if result:
                    result = ord( result )
                else:
                    result = 0
        if result: # None or 0
            # User pressed a key during the reading...
            key = chr( result )
            if key in self.escapeDigits:
                log.info( 'Exiting early due to user press of: %r', key )
                return key
            else:
                # we don't warn user in this menu if they press an unrecognised key!
                log.info( 'Ignoring user keypress because not in escapeDigits: %r', key )
            # completed reading without any escape digits, continue reading
        return None
    def processLast( self,result ):
        if result is None:
            result = ''
        return result

class Prompt( propertied.Propertied ):
    """A Prompt to be read to the user"""
    value = basic.BasicProperty(
        "value", """Filename to be read to the user""",
    )
    def __init__( self, value, **named ):
        named['value'] = value
        super(Prompt,self).__init__( **named )
class AudioPrompt( Prompt ):
    """Default type of prompt, reads a file"""
    def read( self, agi, escapeDigits ):
        """Read the audio prompt to the user"""
        # There's no "say file" operation...
        return agi.getOption( self.value, escapeDigits, 0.001 )
class TextPrompt( Prompt ):
    """Prompt produced via festival text-to-speech reader (built-in command)"""
    def read( self, agi, escapeDigits ):
        return agi.execute( "Festival", self.value, escapeDigits )
class NumberPrompt( Prompt ):
    """Prompt that reads a number as a number"""
    value = common.IntegerProperty(
        "value", """Integer numeral to read""",
    )
    def read( self, agi, escapeDigits ):
        """Read the audio prompt to the user"""
        return agi.sayNumber( self.value, escapeDigits )
class DigitsPrompt( Prompt ):
    """Prompt that reads a number as digits"""
    def read( self, agi, escapeDigits ):
        """Read the audio prompt to the user"""
        return agi.sayDigits( self.value, escapeDigits )
class AlphaPrompt( Prompt ):
    """Prompt that reads alphabetic string as characters"""
    def read( self, agi, escapeDigits ):
        """Read the audio prompt to the user"""
        return agi.sayAlpha( self.value, escapeDigits )
class DateTimePrompt( Prompt ):
    """Prompt that reads a date/time as a date"""
    format = basic.BasicProperty(
        "format", """Format in which to read the date to the user""",
        defaultValue = None
    )
    def read( self, agi, escapeDigits ):
        """Read the audio prompt to the user"""
        return agi.sayDateTime( self.value, escapeDigits, format=self.format )
