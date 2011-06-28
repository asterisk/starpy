#
# StarPy -- Asterisk Protocols for Twisted
# 
# Copyright (c) 2006, Michael C. Fletcher
#
# Michael C. Fletcher <mcfletch@vrplumber.com>
#
# See http://asterisk-org.github.org/starpy for more information about the
# StarPy project. Please do not directly contact any of the maintainers of this
# project for assistance; the project provides a web site, mailing lists and
# IRC channels for your use.
#
# This program is free software, distributed under the terms of the
# BSD 3-Clause License. See the LICENSE file at the top of the source tree for
# details.

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
