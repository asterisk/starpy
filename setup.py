#!/usr/bin/env python
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

"""Installs StarPy using distutils

Run:
    python setup.py install
to install the package from the source archive.
"""

if __name__ == "__main__":
    import sys,os, string
    from distutils.sysconfig import *
    from distutils.core import setup

    ##############
    ## Following is from Pete Shinners,
    ## apparently it will work around the reported bug on
    ## some unix machines where the data files are copied
    ## to weird locations if the user's configuration options
    ## were entered during the wrong phase of the moon :) .
    from distutils.command.install_data import install_data
    class smart_install_data(install_data):
        def run(self):
            #need to change self.install_dir to the library dir
            install_cmd = self.get_finalized_command('install')
            self.install_dir = getattr(install_cmd, 'install_lib')
            # should create the directory if it doesn't exist!!!
            return install_data.run(self)
    ##############
    def npFilesFor( dirname ):
        """Return all non-python-file filenames in dir"""
        result = []
        allResults = []
        for name in os.listdir(dirname):
            path = os.path.join( dirname, name )
            if os.path.isfile( path) and os.path.splitext( name )[1] not in ('.py','.pyc','.pyo') and name!='starpy.conf':
                result.append( path )
            elif os.path.isdir( path ) and name.lower() !='cvs':
                allResults.extend( npFilesFor(path))
        if result:
            allResults.append( (dirname, result))
        return allResults
    dataFiles = npFilesFor( 'doc') + npFilesFor( 'examples') + [('.',('license.txt',))]
    dataFiles = [
        (os.path.join('starpy',directory), files)
        for (directory,files) in dataFiles
    ]

    from sys import hexversion
    if hexversion >= 0x2030000:
        # work around distutils complaints under Python 2.2.x
        extraArguments = {
            'classifiers': [
                """License :: OSI Approved :: BSD License""",
                """Programming Language :: Python""",
                """Topic :: Software Development :: Libraries :: Python Modules""",
                """Intended Audience :: Developers""",
            ],
            'keywords': 'asterisk,fastagi,twisted,protocol,manager,ami',
            'long_description' : """Twisted Protocols for interaction with Asterisk PBX

Provides Asterisk AMI and Asterisk FastAGI protocols under Twisted,
allowing for fairly extensive customisation of Asterisk operations
from a Twisted process.""",
            'platforms': ['Any'],
        }
    else:
        extraArguments = {
        }
    ### Now the actual set up call
    setup (
        name = "starpy",
        version = '1.0.0b1',
        url = "http://starpy.sourceforge.net",
        download_url = "http://sourceforge.net/project/showfiles.php?group_id=164040",
        description = "Twisted Protocols for interaction with the Asterisk PBX",
        author = "Mike C. Fletcher",
        author_email = "mcfletch@vrplumber.com",
        license = "BSD",

        package_dir = {
            'starpy':'.',
        },
        packages = [
            'starpy',
            'starpy.examples',
        ],
        options = {
            'sdist':{'force_manifest':1,'formats':['gztar','zip'],},
        },
        data_files = dataFiles,
        cmdclass = {'install_data':smart_install_data},
        **extraArguments
    )

