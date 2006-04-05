"""Simple HTTP Server using twisted.web2"""
from nevow import rend, appserver, inevow, tags, loaders
from twisted.application import service, internet
from twisted.internet import reactor, defer
from starpy import manager, fastagi, utilapplication
from basicproperty import common, basic, propertied, weak
import os, logging, pprint, time

log = logging.getLogger( 'autosurvey' )

class Application( utilapplication.UtilApplication ):
	"""Services provided at the application level"""
	surveys = common.DictionaryProperty(
		"surveys", """Set of surveys indexed by survey/extension number""",
	)



class Survey( propertied.Propertied ):
	"""Models a single survey to be completed"""
	surveyId = common.IntegerProperty(
		"surveyId", """Unique identifier for this survey""",
	)
	owner = basic.BasicProperty(
		"owner", """Owner's phone number to which to connect""",
	)
	questions = common.ListProperty(
		"questions", """Set of questions which make up the survey""",
	)
	YOU_CURRENTLY_HAVE = 'vm-youhave'
	QUESTIONS_IN_YOUR_SURVEY = 'vm-messages'
	QUESTION_IN_YOUR_SURVEY = 'vm-message'
	TO_LISTEN_TO_SURVEY_QUESTION = 'to-listen-to-it'
	TO_RECORD_A_NEW_SURVEY_QUESTION = 'to-rerecord-it'
	TO_FINISH_SURVEY_SETUP = 'vm-helpexit'
	def setupSurvey( self, agi ):
		"""AGI application to allow the user to set up the survey
		
		Screen 1:
			You have # questions.
			To listen to a question, press the number of the question.
			To record a new question, press pound.
			To finish setup, press star.
		"""
		seq = fastagi.InSequence( )
		seq.append( agi.wait, 2 )
		base = """You currently have %s question%s.
		To listen to a question press the number of the question.
		To record a new question, press pound.
		To finish survey setup, press star.
		"""%(
			len(self.questions),
			['','s'][len(self.questions)==1],
		)
		if len(base) != 1:
			base += 's'
		base = " ".join(base.split())
		seq.append( agi.execute, 'Festival', base )
		seq.append( agi.finish, )
		return seq()
		seq.append( agi.streamFile, self.YOU_CURRENTLY_HAVE )
		seq.append( agi.sayNumber, len(self.questions))
		if len(self.questions) == 1:
			seq.append( agi.streamFile, self.QUESTION_IN_YOUR_SURVEY )
		else:
			seq.append( agi.streamFile, self.QUESTIONS_IN_YOUR_SURVEY )
		seq.append( agi.streamFile, self.TO_LISTEN_TO_SURVEY_QUESTION )
		seq.append( agi.streamFile, self.TO_RECORD_A_NEW_SURVEY_QUESTION )
		seq.append( agi.streamFile, self.TO_FINISH_SURVEY_SETUP )
		seq.append( agi.finish, )
		return seq()
	def newQuestionId( self ):
		"""Return a new, unique, question id"""
		import random, sys
		bad = True
		while bad:
			bad = False
			id = random.randint(0,sys.maxint)
			for question in self.questions:
				if id == question.__dict__.get('questionId'):
					bad = True
		return id
class Question( propertied.Propertied ):
	survey = weak.WeakProperty(
		"survey", """Our survey object""",
	)
	questionId = common.IntegerProperty(
		"questionId", """Unique identifier for our question""",
		defaultFunction = lambda prop,client: client.survey.newQuestionId(),
	)
	def recordQuestion( self, agi, number=None ):
		"""Record a question (number)"""
		return agi.recordFile( 
			'%s.%s'%(self.survey.surveyId,self.questionId),
			'gsm',
			'#*',
			timeout=60,
			beep = True,
			silence=5,
		).addCallback( 
			self.onRecorded, agi=agi
		).addErrback(self.onRecordAborted, agi=agi )
	def onRecorded( self, result, agi ):
		"""Handle recording of the question"""
		

def getManagerAPI( username, password, server='127.0.0.1', port=5038 ):
	"""Retrieve a logged-in manager API"""

class SurveySetup(rend.Page):
	"""Page displaying the survey setup"""
	addSlash = True
	docFactory = loaders.htmlfile( 'index.html' )

class RecordFunction( rend.Page ):
	"""Page/application to record survey via call to user"""
	def renderHTTP( self, ctx ):
		"""Process rendering of the request"""
		# process request parameters...
		request = inevow.IRequest( ctx )
		# XXX sanitise and check value...
		channel = 'SIP/%s'%( request.args['ownerName'][0], )
		
		df = APPLICATION.amiSpecifier.login()
		def onLogin( ami ):
			# Note that the connect comes in *before* the originate returns,
			# so we need to wait for the call before we even send it...
			userConnectDF = APPLICATION.waitForCallOn( '23', timeout=15 )
			APPLICATION.surveys['23'] = survey = Survey()
			userConnectDF.addCallback( 
				survey.setupSurvey, 
			)
			def onComplete( result ):
				return ami.logoff()
			ami.originate(# don't wait for this to complete...
				# XXX handle case where the originate fails differently
				# from the case where we just don't get a connection?
				channel,
				APPLICATION.agiSpecifier.context,
				'23',
				'1',
				timeout=14,
			).addCallbacks( onComplete, onComplete )
			return userConnectDF
		return df.addCallback( onLogin )




def main():
	"""Create the web-site"""
	s = SurveySetup()
	s.putChild( 'record', RecordFunction() )
	site = appserver.NevowSite(s)
	webServer = internet.TCPServer(8080, site)
	webServer.startService()

if __name__ == "__main__":
	logging.basicConfig()
	log.setLevel( logging.DEBUG )
	manager.log.setLevel( logging.DEBUG )
	fastagi.log.setLevel( logging.DEBUG )
	APPLICATION = Application()
	APPLICATION.agiSpecifier.run( APPLICATION.dispatchIncomingCall )
	from twisted.internet import reactor
	reactor.callWhenRunning( main )
	reactor.run()
