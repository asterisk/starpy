#! /usr/bin/env python
"""Sample application to test the menuing utility classes"""
from twisted.internet import reactor
from starpy import fastagi
import utilapplication
import menu
import logging

log = logging.getLogger('menutest')

mainMenu = menu.Menu(
    prompt='/home/mcfletch/starpydemo/soundfiles/menutest-toplevel',
    textPrompt='''Top level of the menu test example

    Pressing Star will exit this menu at any time.
    Options zero and pound will exit with those options selected.
    Option one will start a submenu.
    Option two will start a digit-collecting sub-menu.
    We'll tell you if you make an invalid selection here.''',
    options=[
        menu.Option(option='0'),
        menu.Option(option='#'),
        menu.ExitOn(option='*'),
        menu.SubMenu(
            option='1',
            menu=menu.Menu(
                prompt='/home/mcfletch/starpydemo/soundfiles/menutest-secondlevel',
                textPrompt='''A second-level menu in the menu test example

                Pressing Star will exit this menu at any time. Options zero
                and pound will exit the whole menu with those options selected.
                We won't tell you if you make an invalid selection here.
                ''',
                tellInvalid=False,  # don't report incorrect selections
                options=[
                    menu.Option(option='0'),
                    menu.Option(option='#'),
                    menu.ExitOn(option='*'),
                ],
            ),
        ),
        menu.SubMenu(
            option='2',
            menu=menu.CollectDigits(
                textPrompt='''Digit collection example,
                Please enter three to 5 digits.
                ''',
                soundFile='/home/mcfletch/starpydemo/soundfiles/menutest-digits',
                maxDigits=5,
                minDigits=3,
            ),
        ),
    ],
)


class Application(utilapplication.UtilApplication):
    """Application for the call duration callback mechanism"""

    def onS(self, agi):
        """Incoming AGI connection to the "s" extension (start operation)"""
        log.info("""New call tracker""")

        def onComplete(result):
            log.info("""Final result: %r""", result)
            agi.finish()
        return mainMenu(agi).addCallbacks(onComplete, onComplete)


APPLICATION = Application()

if __name__ == "__main__":
    logging.basicConfig()
    log.setLevel(logging.DEBUG)
    # manager.log.setLevel(logging.DEBUG)
    fastagi.log.setLevel(logging.DEBUG)
    menu.log.setLevel(logging.DEBUG)
    APPLICATION.handleCallsFor('s', APPLICATION.onS)
    APPLICATION.agiSpecifier.run(APPLICATION.dispatchIncomingCall)
    reactor.run()
