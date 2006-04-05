"""Twisted Protocols for Communication with the Asterisk PBX

StarPy allows you to communicate with an Asterisk PBX using an
Asterisk Manager Interface (AMI) client or a Fast Asterisk 
Gateway Interface (FastAGI) server.

The protocols are designed to be included in applications that
want to allow for multi-protocol communication using the Twisted 
protocol.  Their integration with Asterisk does not require any 
modification to the Asterisk source code (though a manager account
is obviously required for the AMI interface, and you have to 
actually call the FastAGI server from the dialplan).
"""
