#!/usr/bin/env python
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

from setuptools import setup, find_packages

VERSION = '1.0.2'

setup(
    name='starpy',
    version=VERSION,
    author='Mike C. Fletcher',
    author_email='mcfletch@vrplumber.com',
    description='Twisted Protocols for interaction with the Asterisk PBX',
    license='BSD',
    long_description=open('README.rst').read(),
    keywords='asterisk manager fastagi twisted AMI',
    url='https://github.com/asterisk/starpy',
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ],

)
