StarPy Asterisk Protocols for Twisted
=====================================

StarPy is a Python + Twisted protocol that provides access to the Asterisk
PBX's Manager Interface (AMI) and Fast Asterisk Gateway Interface (FastAGI).
Together these allow you write both command-and-control interfaces (used, for
example to generate new calls) and to customise user interactions from the
dialplan. You can readily write applications that use the AMI and FastAGI
protocol together with any of the already available Twisted protocols.

StarPy is primarily intended to allow Twisted developers to add Asterisk
connectivity to their Twisted applications. It isn't really targeted at the
normal AGI-writing populace, as it requires understanding Twisted's
asynchronous programming model. That said, if you do know Twisted, it can
readily be used to write stand-alone FastAGIs.

StarPy is Open Source and we are interested in contributions, bug reports and
feedback.
