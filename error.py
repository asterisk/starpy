"""Collection of StarPy-specific error classes"""

class AMICommandFailure(Exception):
    """AMI Command failure of some description"""

class AGICommandFailure(Exception):
    """AGI Command failure of some description"""

class MenuFinished(Exception):
    """Base class for reporting non-standard exits (i.e. not a choice) from a menu"""

class MenuExit(MenuFinished):
    """User exited from the menu voluntarily"""

class MenuTimeout(MenuFinished):
    """User didn't complete selection from menu in reasonable time period"""

class MenuUnexpectedOption(MenuFinished):
    """Somehow the user managed to select an option that doesn't exist?"""
