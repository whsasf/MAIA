#:interpreter:HarnessLanguage.py

import java.lang
import java    # Give access to any standard Java library (using fully qualified names)
import java.util
import java.net
import string  # for string.replace
import quopri  # for quopri.decode
import random
import os.path
import java.util.Random
import sys

import threading
import time
import os
import hashlib
import urllib

from threading import Thread
from java.util.concurrent import TimeUnit
from java.util.concurrent import Executors, ExecutorCompletionService
from java.util.concurrent import Callable

from jarray import zeros, array  # for Java Arrays
from java.util import HashMap

from net.cp.MobileTest             import Base64Coder, XMLParserHelper
from net.cp.MobileTest.Server      import MMSServer, SMTPServer, SMPPRx, SMPPTx, SimpleHTTPServer, TcpServer, SMASIServer, MM7Server, NotifyHTTPServer
from net.cp.MobileTest.harness     import Message, TestCase
from net.cp.MobileTest.management  import ManagementClient, ManagementClientException
from net.cp.MobileTest.Client      import MMSClient, SMTPClient, MsgHandler, CannedMsgClient, POPClient, IMAPClient, CPPABClient, CPWebDavClient, SyncClient, CSAPIClient, MM7Client, UMCAtomClient, CPCardDAVClient, MOSClient, EurekaApplication
from net.cp.MobileTest.Message     import HarnessMessage
from net.cp.maia                   import Util
from net.cp.maia.clients.http      import AuthCredentials, CpHttpClient, CpHttpServer
from net.cp.maia.clients.http.xml  import PSXMLHttpClient, XMLHttpClient, XMLItem, XMLList, XMLParam, XMLResult, XMLRoot
from net.cp.maia.clients.http.json import JSONHttpClient
from net.cp.maia.clients.ups       import UPSClient
from net.cp.maia.clients.locator       import LocatorClient
from net.cp.maia.clients.ssh       import SSHClient
from net.cp.maia.clients.jmx       import JMXRMIClient
from net.cp.maia.clients.couchbase import CouchbaseClient
from net.cp.maia.clients.caldav    import CalDAVClient

from net.cp.ups import Attributes, EntryIntf, UPSLocatorException, UPSNoSuchEntryException
from net.cp.ups.EntryIntf import AttributeModificationType
from com.logica.smpp.test import SMPPClient

FALSE = 0
TRUE = 1
true = "true"
false = "false"


# 2 level dictionary i.e. a dictionary containing dictionaries
# Used to store config data
class Config:
    # borg pattern - to make sure all Config's are one
    __shared_state = {} # or org.python.core.PyStringMap in jython

    def __init__(self, name=None):
        self.__dict__ = self.__shared_state
        self._nodes = {}  # a dictionary
        self._name = name

    def set (self, name, key, value):
         if self._nodes.has_key(name) :
            self._nodes[name][key] = value
         else :
            self._nodes[name] = { 'name' : name, key : value }

    def get (self, name=None, key=None, default=None):
            if name is None:
                ret = self._nodes
                _log ('Config.get(name='+repr(name)+', key='+repr(key)+', default='+repr(default)+') returns '+repr(ret))
                return ret
            if self._nodes.has_key(name) :
                if key is not None:
                    ret = self._nodes[name].get(key,default)
                    _log ('Config.get(name='+repr(name)+', key='+repr(key)+', default='+repr(default)+') returns '+repr(ret))
                    return ret
                else:
                    ret = self._nodes[name]
                    _log ('Config.get(name='+repr(name)+', key='+repr(key)+', default='+repr(default)+') returns '+repr(ret))
                    return ret
            else :
                _log ('Config.get(name='+repr(name)+', key='+repr(key)+', default='+repr(default)+') not found - return supplied default')
                return default

######################################################################################
# class with a __call__ method, which delegates calls to another callable it holds
# Don't really understand how this works but it is a python way to have static functions in a class
class Callable:
    def __init__(self, anycallable):
        self.__call__ = anycallable

class MessageServer:
    """Class designed to give standard API to harness servers.
    This is a wrapper for net.cp.MobileTest.Server.MessageServer sub-classes
    All harness servers should inherit from this class
    Keeps a cache of servers so they can be re-used in different test cases
    It's too slow to stop and restart servers for each test
    """
    _serverlist = {}  # dictionary to store all servers - this is a class static

    def __init__(self, cfgname, type, classname):
        """
        cfgname is the name of the configuration stored in global cfg
        type is EAIF, MM7, SMTP or SMPP
        classname is the name of implementing subclass
        """

        # if already created, just reset queue
        try: getattr(self, '_server')
        except AttributeError:
            _log('MessageServer.__init__ server(%s)' % (cfgname))
            pass
        else :
            _log('MessageServer.__init__ server(%s) returning as createSvr has already be executed \"%s\"' % (cfgname))
            return
        if not hasattr(self, "getMessage"):
             raise AttributeError("MessageServer must implement getMessage")
        if not hasattr(self, "createSvr"):
             raise AttributeError("MessageServer must implement createSvr")

        _log('MessageServer.__init__ checking attributes for (%s) <classname=%s>' % (cfgname,classname))

        if classname is None or classname == "" :
            raise ValueError, "<classname> value not specified for MessageServer subclass"
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for", classname
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to %s" % (cfgname, classname)
        if cfg.get(cfgname, "port") == None:
            raise ValueError, "Configuration \"%s\" supplied to %s does not specify listen port" % (cfgname, classname)
        if not self.reuseSvr(cfgname) :
            self.createSvr(cfgname, type)
            self._cfgname=cfgname
            if not hasattr(self._server, "reset"):
                raise AttributeError('MessageServer <classname=%s> must implement reset()' % (classname))


    def reuseSvr(self, cfgname):
        if self._serverlist.has_key(cfgname) :
            _log('Reusing server called \"%s\"' % (cfgname))
            self._server = self._serverlist.get(cfgname)
            #self._server.reset()  # this was hiding errors
            qSize = self._server.queueSize()
            if qSize != 0:
                exp = 'server \"%s\" has %d messages already in queue' % (cfgname,qSize)
                while self._server.queueSize() > 0:
                    message = self._server.getMessage(1)
                    if message != None:
                        exp = '%s\n%s' % (exp,message.toString())
                raise ValueError, exp
            return TRUE
        else :
            return FALSE

    def reset(self, cfgname):
        if self._serverlist.has_key(cfgname) :
            _log('Reset server called \"%s\"' % (cfgname))
            self._server = self._serverlist.get(cfgname)
            self._server.reset()
            return TRUE

    def reset(self):
        if self._server == None:
            _log("reset called for server that is not initialized")
            return TRUE
        try: cfgname = getattr(self, '_cfgname')
        except AttributeError: cfgname='unknown'
        qsize = self._server.queueSize()
        self._server.reset()
        _log ('reset() Clears queue of %d messages for %s' % (qsize,cfgname))
        return TRUE

    def queueSize(self):
        """return number of messages in queue """
        _log ('queueSize()')
        if self._server == None:
            raise ValueError, "queueSize: Error - Server is not initialized"
        try: cfgname = getattr(self, '_cfgname')
        except AttributeError: cfgname='unknown'
        if not hasattr(self._server, "queueSize"):
            return 0  # server has no queue methods
        qsize = self._server.queueSize()
        _log ('queueSize() returns %d for %s' % (qsize,cfgname))
        return qsize


    def shutdown(self):
        try: cfgname = getattr(self, '_cfgname')
        except AttributeError: cfgname='unknown'
        self._server = self._serverlist.get(cfgname)
        if self._server is not None:
            _log('Shutting down server called \"%s\"' % (cfgname))
            self._server.shutdown()
            try:
                del self._serverlist[cfgname]
                _log('Removing server called \"%s\" from reuse list' % (cfgname))
            except KeyError: pass

    # returns list of servers that have messages in their queues
    # It is normally an error if message left in queue at end of test. It causes problems for later tests so adding
    # automatic check for this condition to script wrapper at end of this file
    # Will aslo empty queues
    def checkqueues():
        nonemptyqueues = None
        for i in MessageServer._serverlist:
            server = MessageServer._serverlist.get(i)
            if hasattr(server, "queueSize"):
                qsize = server.queueSize()
                if qsize > 0:
                    if nonemptyqueues:
                        nonemptyqueues = "%s,%s" % (nonemptyqueues, i)
                    else:
                        nonemptyqueues = i
                    while (server.queueSize() > 0):
                        message = server.getMessage(1)
                        if message:
                            _log('Found message in %s harness queue\n%s' % (i, message.toString()))
                    _log('non-empty queues: %s' % (nonemptyqueues))
            server.reset()

        _log('checkqueues() returns %s' % (nonemptyqueues))
        return nonemptyqueues

    # trick to make it static method
    checkqueues = Callable(checkqueues)

    # testcase class takes care of logging
    # if server not initialized during test, it won't have reference to current testcase oject
    # testcase is jython global set by harness before every test
    def setTestcase4all():
        for i in MessageServer._serverlist:
            server = MessageServer._serverlist.get(i)
            if hasattr(server, "setTestcase"):
                server.setTestcase(testcase)

    setTestcase4all = Callable(setTestcase4all)


######################################################################################
# MMS Server Wrapper

class MMS_Server(MessageServer):
    def __init__(self, cfgname, type = "EAIF"):
        _log("MMS_Server.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        MessageServer.__init__(self, cfgname, type, 'MMS_Server')

    def createSvr(self, cfgname, type):
        """
        Called from super class init() method
        cfgname is the name of the configuration stored in global cfg
        type is EAIF, MM7, SMTP or SMPP
        """
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._type = type
        #print 'cfgname=%s,port=%s' % (cfgname, self._port)
        self._server = MMSServer(testcase, self._type, "%u" % self._port)
        self._serverlist[cfgname] = self._server
        _log ('MMS_Server.createSvr() Created MMS server called \"%s\"' % (cfgname))

    def getMessage(self, wait):
        """return a HarnessMessage """
        _log ('MMS_Server.getMessage(wait=%s)' % (wait))
        if self._server == None:
            raise ValueError, "getMessage: Error - MMS_Server is not initialized"
        message = self._server.getMessage(wait)
        if message == None:
            raise ValueError, "getMessage: Error - MMS_Server failed to return a message"
        return message

    def queueSize(self):
        """return number of messages in queue """
        _log ('MMS_Server.queueSize()')
        if self._server == None:
            raise ValueError, "getQueueSize: Error - MMS_Server is not initialized"
        return self._server.queueSize()

    def GetMessage(self, wait):
        """return a MmsMessage. Legacy don't use this"""
        _log ('MMS_Server.GetMessage(wait=\"%s\")' % (wait))
        if self._server == None:
            raise ValueError, "GetMessage: Error - MMS_Server is not initialized"
        message = self._server.GetMessage(wait)
        if message == None:
            raise ValueError, "GetMessage: Error - MMS_Server failed to return a message"
        return message
######################################################################################
# SMTP Server Wrapper

class SMTP_Server(MessageServer):
    def __init__(self, cfgname, type = "SMTP"):
        _log ("SMTP_Server.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        MessageServer.__init__(self, cfgname, type, 'SMTP_Server')

    def createSvr(self, cfgname, type):
        self._port = int_convert(cfg.get(cfgname, "port"))

        #print 'cfgname=%s,port=%s' % (cfgname, self._port)
        self._server = SMTPServer(testcase, self._port, cfg.get(cfgname, "host"))
        self._serverlist[cfgname] = self._server
        _log('Created SMTP server called \"%s\"' % (cfgname))

    # wait in seconds
    def getMessage(self, wait):
        _log ('SMTP_Server.getMessage(wait=\"%s\")' % (wait))
        if self._server == None:
            raise ValueError, "GetMessage: Error - SMTP_Server is not initialized"
        message = self._server.getMessage(wait)
        if message == None:
            raise ValueError, "GetMessage: Error - SMTP_Server failed to return a message"
        return message


######################################################################################
# HTTP Server Wrapper

class HTTP_Server(MessageServer):
    def __init__(self, cfgname='HTTPd', type="HTTP", path='.'):
        _log ("HTTP_Server.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        self._path = path
        MessageServer.__init__(self, cfgname, type, 'HTTP_Server')

    def createSvr(self, cfgname, type):
        self._port = cfg.get(cfgname, "port")
        self._host = cfg.get(cfgname, "host")
        self._server = SimpleHTTPServer(testcase, self._host, self._port, self._path)
        self._serverlist[cfgname] = self._server
        _log('Created Simple HTTP server called \"%s\"' % (cfgname))

    def updateSrvURL(self, old_url, new_url):
        self._server.updateSrvURL(old_url, new_url)
        _log('Change the URL : \"%s\" into \"%s\"' % (old_url, new_url))

    def getMessage(self, wait):
        _log ('HTTP_Server.getMessage(wait=\"%s\")' % (wait))
        raise ValueError, "HTTP Server method not available"
        return None

######################################################################################
# Notify HTTP Server Wrapper

class Notify_HTTP_Server(MessageServer):
    def __init__(self, cfgname='HTTPNotify', type="HTTP", path='.'):
        _log ("HTTP_Server.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        self._path = path
        MessageServer.__init__(self, cfgname, type, 'Notify_HTTP_Server')

    def createSvr(self, cfgname, type):
        self._port = cfg.get(cfgname, "port")
        self._host = cfg.get(cfgname, "host")
        self._server = NotifyHTTPServer(testcase, self._host, self._port, self._path)
        self._serverlist[cfgname] = self._server
        _log('Created Notify HTTP server called \"%s\"' % (cfgname))

    def updateSrvURL(self, old_url, new_url):
        self._server.updateSrvURL(old_url, new_url)
        _log('Change Notify HTTP Server URL : \"%s\" into \"%s\"' % (old_url, new_url))

    # wait in milliseconds
    def getMessage(self, wait):
        if self._server == None:
            raise ValueError, "getMessage: Error - Notify_HTTP_Server is not initialized"
        message = self._server.getMessage(wait)
        if message == None:
            raise ValueError, "getMessage: Error - Notify_HTTP_Server failed to return a message"
        return message

    # delay in milliseconds
    def testNotifications(self, notifs, delay = 30000):

        if self._server == None:
            raise ValueError, "testNotifications: Error - Notify_HTTP_Server is not initialized"

        success = TRUE

        if notifs is None:
            _log("Expecting no notif ...")
            try:
                msg = self.getMessage(delay)
                if msg is not None:
                    success = FALSE
            except:
                _log("Got no message as expected")

        else:

            success = TRUE
            ncount = len(notifs)
            s = "Expecting %s notif(s) (%s=%s, ...)" % (ncount, notifs[0][0], notifs[0][1])
            for i in range(1, ncount):
                s = "%s (%s=%s, ...)" % (ncount, notifs[i][0], notifs[i][1])
            _log(s)

            for i in range(ncount):

                found = FALSE
                try:
                    _log("Getting message %s ..." % i)

                    msg = self._server.getMessage(delay)

                    if msg is not None:
                        for i in range(len(notifs)):
                            if notifs[i] is None:
                                continue

                            goal = ""
                            for j in range(len(notifs[i])/2):
                                goal = "%s%s=%s " % (goal, notifs[i][2*j], notifs[i][2*j + 1])

                            _log("Expected='%s'" % goal)

                            res = ""
                            for j in range(len(notifs[i])/2):
                                try:
                                    value = msg.getHeader(notifs[i][2*j])
                                    if value is None:
                                        value = ""
                                except:
                                    value = ""

                                res = "%s%s=%s " % (res, notifs[i][2*j], urllib.unquote(value))


                            _log("Received='%s'" % (res))

                            if res == goal:
                                found = TRUE
                                break

                        if found:
                            _log("Notif (%s=%s) found" % (notifs[i][0], notifs[i][1]))
                            notifs[i] = None
                        else:
                            _log("Got an unexpected notify message")
                            success = FALSE

                    else:
                        _log("Got a null notify message")
                        success = FALSE
                        break

                except:
                    _log("Failed to get %s notification" % ncount)
                    success = FALSE
                    break

        return testIsTrue(success, description = "Test notifications")

######################################################################################
# MM7 Server Wrapper

class MM7_Server(MessageServer):
    def __init__(self, cfgname, type = 'MM7'):
        _log("MM7_Server.__init__(cfgname=\"%s\")" % (cfgname) )
        MessageServer.__init__(self, cfgname, type, 'MM7_Server')

    def createSvr(self, cfgname, type):
        """
        Called from super class init() method
        cfgname is the name of the configuration stored in global cfg
        type is EAIF, MM7, SMTP or SMPP
        """
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._type = type
        self._server = MM7Server(testcase, cfg.get(cfgname, "host"), cfg.get(cfgname, "port"), cfg.get(cfgname, "path"))
        self._serverlist[cfgname] = self._server
        _log ('MM7_Server.createSvr() Created MM7 server called \"%s\"' % (cfgname))

    def getMessage(self, wait):
        """return a HarnessMessage """
        _log ('MM7_Server.getMessage(wait=%s)' % (wait))
        if self._server == None:
            raise ValueError, "getMessage: Error - MM7_Server is not initialized"
        message = self._server.getMessage(wait)
        if message == None:
            raise ValueError, "getMessage: Error - MM7_Server failed to return a message"
        return message

    def queueSize(self):
        """return number of messages in queue """
        _log ('MM7_Server.queueSize()')
        if self._server == None:
            raise ValueError, "getQueueSize: Error - MM7_Server is not initialized"
        return self._server.queueSize()

######################################################################################
# Generic TCP Server
# No message methods. No queue

class GenericServer:
    def __init__(self, cfgname = None, port=0):

        _log ("GenericServer.__init__(port=\"%d\")" % (port) )
        if cfgname is None or cfgname == "" :
            self._port = port
        else:
            if cfg.get(cfgname) == None:
                raise ValueError, "Unknown cfgname \"%s\" supplied to GenericServer" % (cfgname)
            self._port = cfg.get(cfgname, "port")
            if self._port == None:
                raise ValueError, "Configuration \"%s\" supplied to GenericServer does not specify listen port" % (cfgname)
        if  self._port == 0:
            raise ValueError, "GenericServer requires port number"

        try:
            self._server = TcpServer(testcase, self._port)
            self._server.start()
        except java.io.IOException:
            raise ValueError, "GenericServer cannot open [port:%u]" % (self._port)

    def getClientRequest(self, wait):
        #print ''
        _log('GenericServer.getClientRequest()')
        result = self._server.getClientRequest(wait*1000)
        _log ('GenericServer.getClientRequest() returns \n\'%s\'' % result)
        return result

    def sendRawResponse(self, response):
        _log('GenericServer.sendRawResponse()')
        self._server.sendRawResponse(response)

    def sendHttpResponse(self, httpCode, contentType = None, response=None):
        _log('GenericServer.sendHttpResponseStr()')
        self._server.sendHttpResponseStr(httpCode, contentType, response)

    def close(self):
        self._server.close()

######################################################################################
# SMASI Server
# No message methods. No queue

class SMASI_Server:
    def __init__(self, cfgname=None, port=0, gmi2=True):

        _log ("SMASIServer.__init__(port=\"%d\") (gmi2=\"%s\")" % (port, gmi2))
        if cfgname is None or cfgname == "" :
            self._port = port
            self._host = "localhost"
        else:
            if cfg.get(cfgname) == None:
                raise ValueError, "Unknown cfgname \"%s\" supplied to SMASIServer" % (cfgname)
            self._port = cfg.get(cfgname, "port")
            self._host = cfg.get(cfgname, "host")
            if self._port == None:
                raise ValueError, "Configuration \"%s\" supplied to SMASIServer does not specify listen port" % (cfgname)

        if  self._port == 0:
            raise ValueError, "SMASIServer requires port number"

        if getGlobal("globalSMASIServer") is None:
            try:
                self._server = SMASIServer(testcase, self._port, self._host, gmi2)
                self._server.start()
                setGlobal("globalSMASIServer", self._server)
            except java.io.IOException:
                raise ValueError, "SMASIServer cannot open [port:%u, host:%s]" % (self._port,self._host)
        else:
            self._server = getGlobal("globalSMASIServer")
            self._server.setTestcase(testcase)

    def getClientRequest(self, wait):
        #print ''
        _log('SMASIServer.getClientRequest()')
        result = self._server.getClientRequest(wait)
        if result is not None:
            result = result.encode('ascii', 'replace')
        return result

    def close(self):
        self._server.close()
        setGlobal("globalSMASIServer", None)

    def reset(self):
        self._server.reset()

######################################################################################
# SMPP Server Wrapper

class SMPP_Server(MessageServer):
    def __init__(self, cfgname, type = "SMPP"):
        _log ("SMPP_Server.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        MessageServer.__init__(self, cfgname, type, 'SMPP_Server')

    def createSvr(self, cfgname, type):
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._user = cfg.get(cfgname, "user")
        self._password = cfg.get(cfgname, "password")
        #print 'cfgname=%s,port=%s' % (cfgname, self._port)
        self._server = SMPPRx(self._port, self._user, self._password, testcase)

        self._serverlist[cfgname] = self._server
        _log('Created SMPP server called \"%s\"' % (cfgname))

    def getMessage(self, wait):
        _log ('SMPP_Server.getMessage(wait=\"%s\")' % (wait))
        if self._server == None:
            raise ValueError, "GetMessage: Error - SMPP_Server is not initialized"
        message = self._server.getMessage(wait)
        if message == None:
            raise ValueError, "GetMessage: Error - SMPP_Server failed to return a message"
        return message

    def getShortMessage(self, wait):
        _log ('SMPP_Server.getShortMessage(wait=\"%s\")' % (wait))
        if self._server == None:
            raise ValueError, "getShortMessage: Error - SMPP_Server is not initialized"
        message = self._server.getShortMessage(wait)
        if message == None:
            raise ValueError, "getShortMessage: Error - SMPP_Server failed to return a short message"
        return message

    def getConcatenatedMessage(self, wait):
        _log ('SMPP_Server.getConcatenatedMessage(wait=\"%s\")' % (wait))
        if self._server == None:
            raise ValueError, "getConcatenatedMessage: Error - SMPP_Server is not initialized"
        message = self._server.getConcatenatedMessage(wait)
        if message == None:
            raise ValueError, "getConcatenatedMessage: Error - SMPP_Server failed to return a short message"
        return message

    # Server will return an error for every 'count' submissions
    def setSubmitErrorProfile(self, count, status):
        _log ('SMPP_Server.setSubmitErrorProfile(count=\"%s\", status=\"%s\")' % (count, status))
        if self._server == None:
            raise ValueError, "setSubmitErrorProfile: Error - SMPP_Server is not initialized"
        self._server.setSubmitErrorProfile(count, status)


###############################################################################
# WebDAV Server
#
# TODO: Refactor the management protocol functions and combine common code

class WebDAV_Server:
    def __init__(self,
                 webdav_host = "WEBDAV1_HOST",
                 webdav_port = "WEBDAV1_PORT",
                 service_install_path = "SERVICE1_INSTALL",
                 webdav_install_path = "WEBDAV1_INSTALL",
                 webdav_mgmt_cfg = "WEBDAV1_MGMT",
                 service_mgmt_cfg = "SERVICE1_MGMT",
                 ssh_cfg = "WEBDAVSSH1"):
        self._webdav_host = getGlobal(webdav_host)
        self._webdav_port = getGlobal(webdav_port)
        self._webdav_mgmt_cfg = webdav_mgmt_cfg
        self._service_install_path = getGlobal(service_install_path)
        self._webdav_install_path = getGlobal(webdav_install_path)
        self._service_mgmt_cfg = service_mgmt_cfg
        self._ssh_cfg = ssh_cfg

    def restartServer(self):
        ssh = None
        try:
            try:
                ssh = SSH_Client(self._ssh_cfg)
                resp = ssh.executeCommand("/bin/bash " +
                                          self._service_install_path +
                                          "/service/bin/servicerc restart")
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Restart failed: Exception=" + ex)
                return FALSE

            print "----- Response Start -----"
            print resp
            print "----- Response End -----"

            exitCode = ssh.getExitCode()
            if exitCode != 0:
                testSetResultFail(details = "Restart failed. Exit Code=" +
                                  str(exitCode))
                return FALSE

            return TRUE
        finally:
            if ssh:
                ssh.close()

    def setProxyMode(self, mode):
        mgr = None
        try:
            cmd = "SET EnableNonProxyMode " + str(mode)
            try:
                mgr = MGR_Client(self._service_mgmt_cfg, 5)
                result = mgr.send(cmd)
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + ex)
                return FALSE

            if not testTelnetSuccess(result, description = cmd):
                testSetResultFail(details = "Command (" + cmd + ") failed. " +
                                  "Result=" + str(result))
                return FALSE

            try:
                result = mgr.close()
                mgr = None
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="MGR_Client.close() failed " +
                                  "Exception=" + ex)
                return FALSE

            return TRUE
        finally:
            if mgr:
                mgr.close()

    def setStandAloneMode(self, mode):
        mgr = None
        try:
            cmd = "SET StandAloneMode " + str(mode)
            try:
                mgr = MGR_Client(self._service_mgmt_cfg, 5)
                result = mgr.send(cmd)
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + ex)
                return FALSE

            if not testTelnetSuccess(result, description = cmd):
                testSetResultFail(details = "Command (" + cmd + ") failed. " +
                                  "Result=" + str(result))
                return FALSE

            try:
                result = mgr.close()
                mgr = None
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="MGR_Client.close() failed " +
                                  "Exception=" + ex)
                return FALSE

            return TRUE
        finally:
            if mgr:
                mgr.close()

    def addDomain(self, domain, ups="LOC1"):
        mgr = None
        try:
            cmd = "DOMAIN ADD " + domain + " UPS=" + ups
            try:
                mgr = MGR_Client(self._webdav_mgmt_cfg, 5)
                result = mgr.send(cmd)
                if not testTelnetSuccess(result):
                    testSetResultFail(details = "Command (" + cmd + ") " +
                                      "failed. Result=" + str(result))
                    return FALSE
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + str(ex))
                return FALSE

            return TRUE

        finally:
            if mgr:
                mgr.close()

    def deleteDomain(self, domain):
        mgr = None
        try:
            cmd = "DOMAIN DELETE " + domain
            try:
                mgr = MGR_Client(self._webdav_mgmt_cfg, 5)
                result = mgr.send(cmd)
                if not testTelnetSuccess(result):
                    testSetResultFail(details = "Command (" + cmd + ") " +
                                      "failed. Result=" + str(result))
                    return FALSE
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + str(ex))
                return FALSE
            return TRUE
        finally:
            if mgr:
                mgr.close()

    def addUser(self, domain, user, userLocation, userPassword, ups="LOC1"):
        mgr = None
        try:
            cmd = "USER " + domain + " ADD " + user + " UPS=" + ups + \
                  " IFSLOCATION=" + userLocation + "/" + domain + "/" + user
            try:
                mgr = MGR_Client(self._webdav_mgmt_cfg, 5)
                result = mgr.send(cmd)
                if not testTelnetSuccess(result):
                    testSetResultFail(details = "Command (" + cmd + ") " +
                                      "failed. Result=" + str(result))
                    return FALSE

                cmd = "PASSWORD " + domain + " USER " + user + " SET " + \
                      userPassword
                result = mgr.send(cmd)
                if not testTelnetSuccess(result):
                    testSetResultFail(details = "Command (" + cmd + ") " +
                                      "failed. Result=" + str(result))
                    return FALSE

            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + str(ex))
                return FALSE
            return TRUE
        finally:
            if mgr:
                mgr.close()

    def deleteUser(self, domain, user, eraseFlag):
        mgr = None
        try:
            cmd = "USER " + domain + " DELETE " + user
            if eraseFlag:
                cmd = cmd + " ERASE"
            try:
                mgr = MGR_Client(self._webdav_mgmt_cfg, 5)
                result = mgr.send(cmd)
                if not testTelnetSuccess(result):
                    testSetResultFail(details = "Command (" + cmd + ") " +
                                      "failed. Result=" + str(result))
                    return FALSE
            except:
                ex = str(sys.exc_info()[0])
                testSetResultFail(details="Command (" + cmd + ") failed. " +
                                  "Exception=" + str(ex))
                return FALSE
            return TRUE
        finally:
            if mgr:
                mgr.close()

######################################################################################
# SMPP RX bind or un-bind request Wrapper
class SMPP_RX_Client:
    def __init__(self, cfgPath, cfgname, port):
        _log ("SMPP_Client.__init__(cfgPath=\"%s\)" % (cfgPath) )
        if cfgPath is None or cfgPath == "" :
            raise ValueError, "<cfgPath> value not specified for SMPP_RX_Client"
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for SMPP_RX_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to SMPP_Client" % cfgname
        if cfg.get(cfgname, "ip") == None:
            raise ValueError, "Host Ip is not defined for cfgname \"%s\" supplied to SMPP_RX_Client" % cfgname
        self._client = SMPPClient(cfgPath)
        self._client.init(cfg.get(cfgname, "ip"), port)

    def exit(self):
        self._client.exit()

    def bindRx(self):
        return self._client.bindRx()

    def unbindRx(self):
        return self._client.unbindRx()

######################################################################################
# SMPP Message Client Wrapper

class SMPP_Client:
    # borg pattern - to make sure all SMPP clients share this MAP
    # Allows just 1 client to be reused instead of connecting and disconnecting
    # because it's not really a client at all, it's a server that sends
    _serverlist = {}  # store all servers - this is a class static

    def __init__(self, cfgname, type = 'SMPP'):
        _log ("SMPP_Client.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        if type is None or type == "" :
            raise ValueError, "<type> value not specified for SMPP_Client"
        self._type = type
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for SMPP_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to SMPP_Client" % cfgname
        if type == 'SMPP':
            if cfg.get(cfgname, "port") == None:
                raise ValueError, "Port not defined for cfgname \"%s\" supplied to SMPP_Client" % cfgname
            self._port = int_convert(cfg.get(cfgname, "port"))
            if cfg.get(cfgname, "user") == None:
                raise ValueError, "User not defined for cfgname \"%s\" supplied to SMPP_Client" % cfgname
            self._user = cfg.get(cfgname, "user")
            if cfg.get(cfgname, "password") == None:
                raise ValueError, "Password not defined for cfgname \"%s\" supplied to SMPP_Client" % cfgname
            self._password = cfg.get(cfgname, "password")
            if not self.reuseSvr(cfgname) :
                self._client = SMPPTx(self._port, self._user, self._password, testcase)
                self._serverlist[cfgname] = self._client
                _log ('SMPP_Client() Created SMS client (actually server) called \"%s\"' % (cfgname))

        else:
            raise ValueError, "Unknown type \"%s\" supplied to SMPP_Client" % type

    def reuseSvr(self, cfgname):
        if self._serverlist.has_key(cfgname) :
            _log('Reusing smpp client called \"%s\"' % (cfgname))
            self._client = self._serverlist.get(cfgname)
            self._client.setTestcase(testcase)
            return TRUE
        else :
            return FALSE

    def NewMessage(self):
        _log ("SMPP_Client.NewMessage()")
        message = HarnessMessage(HarnessMessage.SMS_MESSAGE_TYPE)
        return message

    def SendMessage(self, message, timeout=0):
        _log ("SMPP_Client.SendMessage")
        src = message.from
        dst = message.to
        txt = message.getFirstTextPart()
        return self.SendTextMessage(src, dst, txt, timeout)

    def SendTextMessage(self, src, dst, txt, timeout = 0):
        _log ("SMPP_Client.SendTextMessage(src=%s, dst=%s, txt=%s)" % (src, dst, repr(txt)))
        return self._client.SendTextMessage(src, dst, txt, timeout)

    def SendSegmentedTextMessage(self, src, dst, txt, seg, timeout = 0):
        _log ("SMPP_Client.SendSegmentedTextMessage(src=%s, dst=%s, txt=%s, seg=%d)" % (src, dst, repr(txt), seg))
        return self._client.SendSegmentedTextMessage(src, dst, txt, seg, timeout)

    def SendTextMessageSegment(self, src, dst, txt, ref, seg, total, timeout = 0):
        _log ("SMPP_Client.SendTextMessageSegment(src=%s, dst=%s, txt=%s, ref=%d, seg=%d, total=%d)" % (src, dst, repr(txt), ref, seg, total))
        return self._client.SendTextMessageSegment(src, dst, txt, ref, seg, total, timeout)

    def close(self):
        _log ("SMPP_Client.close()")
        #self._client.close()

    # testcase class takes care of logging
    # if server not initialized during test, it won't have reference to current testcase oject
    # testcase is jython global set by harness before every test
    def setTestcase4all():
        for i in SMPP_Client._serverlist:
            server = MessageServer._serverlist.get(i)
            if hasattr(server, "setTestcase"):
                server.setTestcase(testcase)

    setTestcase4all = Callable(setTestcase4all)

# All harness clients should inherit from HarnessClient
class HarnessClient:

  def __init__(self):
    if not hasattr(self, "send"):
         raise AttributeError("HarnessClient must implement send")

  def send(self,msg):
    if self.clnt is not None:
        return self.clnt.send(msg)

######################################################################################
# Sync Client Wrapper
#
class Sync_Client:
    def __init__(self, cfgname, username, password, devid, memcardid=None, maxMsgSize=0):
        _log ("Sync_Client.__init__(cfgname=\"%s\", username=\"%s\", password=\"%s\", devid=\"%s\", memcardid=\"%s\", maxMsgSize=%u" % (cfgname, username, password, devid, memcardid, maxMsgSize) )

        if ( (devid is None) or (devid == "") ) :
            raise ValueError, "<devid> value not specified for Sync_Client"

        host = cfg.get(cfgname, "host")
        port = cfg.get(cfgname, "port")
        client_path = cfg.get(cfgname, "client_path")
        self._client = SyncClient(testcase, getFullCurrentDir(), client_path, host, "%u" % port, username, password, devid, memcardid, maxMsgSize)

    def setDeviceInfo(self, deviceType, deviceManufacturer, deviceModel, applicationName=None, applicationVersion=None, softwareVersion=None, applicationCapabilityID=None):
        _log ("Sync_Client.setDeviceInfo(deviceType=\"%s\", deviceManufacturer=\"%s\", deviceModel=\"%s\", applicationName=\"%s\", applicationVersion=\"%s\", applicationCapabilityID=\"%s\"" % (deviceType, deviceManufacturer, deviceModel, applicationName, applicationVersion, applicationCapabilityID) )
        self._client.setDeviceInfo(deviceType, deviceManufacturer, deviceModel, applicationName, applicationVersion, softwareVersion, applicationCapabilityID)

    def setContactInfo(self, dir, syncType=1, conflictRes="client_wins", forceRev=FALSE, errorStatusCode=0, errorStatusData=None):
        _log ("Sync_Client.setContactInfo(dir=\"%s\", syncType=%d, conflictRes=\"%s\", forceRev=%u, errorStatusCode=%u, errorStatusData=\"%s\"" % (dir, syncType, conflictRes, forceRev, errorStatusCode, errorStatusData) )
        self._client.setContactInfo(dir, syncType, conflictRes, forceRev, errorStatusCode, errorStatusData)

    def setContentInfo(self, dir, syncType=1, errorStatusCode=0, errorStatusData=None, maxObjectSize=0):
        _log ("Sync_Client.setContentInfo(dir=\"%s\", syncType=%d, errorStatusCode=%u, errorStatusData=\"%s\", maxObjectSize=%u" % (dir, syncType, errorStatusCode, errorStatusData, maxObjectSize) )
        self._client.setContentInfo(dir, syncType, errorStatusCode, errorStatusData, maxObjectSize)

    def setSuspendInfo(self, suspendSendCount, suspendRecvCount, resumeDelay, errorOutputCount=0, errorInputCount=0):
        _log ("Sync_Client.setSuspendInfo(suspendSendCount=%u, suspendRecvCount=%u, resumeDelay=%u, errorOutputCount=%u, errorInputCount=%u" % (suspendSendCount, suspendRecvCount, resumeDelay, errorOutputCount, errorInputCount) )
        self._client.setSuspendInfo(suspendSendCount, suspendRecvCount, resumeDelay, errorOutputCount, errorInputCount)

    def setDisplayAlertInfo(self, status, delay=0):
        _log ("Sync_Client.setDisplayAlertInfo(status=%d, delay=%d" % (status, delay) )
        self._client.setDisplayAlertInfo(status, delay)

    def setHttpInfo(self, uri, httpHeaders = None):
        _log ("Sync_Client.setUri(uri='%s', httpHeaders='%s'" % (uri, httpHeaders) )
        self._client.setHTTPInfo(uri, httpHeaders)

    def sync(self, fileRep=TRUE):
        _log ("Sync_Client.sync(fileRep=%d)" % fileRep)
        return self._client.sync(fileRep)

    def getListener(self):
        _log ("Sync_Client.getListener()")
        return self._client.getListener()

    #   The following methods are deprecated.
    #   Should use getListener() instead

    def getAllOutgoingFailureCount(self, strict=FALSE):
        _log ("Sync_Client.getAllOutgoingFailureCount(strict=%s)" % strict)
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getAllOutgoingFailureCount(strict)

    def getAllOutgoingSuccessCount(self):
        _log ("Sync_Client.getAllOutgoingSuccessCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getAllOutgoingSuccessCount()

    def getIncomingAddCount(self):
        _log ("Sync_Client.getIncomingAddCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getIncomingAddCount()

    def getIncomingReplaceCount(self):
        _log ("Sync_Client.getIncomingReplaceCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getIncomingReplaceCount()

    def getIncomingDeleteCount(self):
        _log ("Sync_Client.getIncomingDeleteCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getIncomingDeleteCount()

    def getIncomingCopyCount(self):
        _log ("Sync_Client.getIncomingCopyCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getIncomingCopyCount()

    def getIncomingMoveCount(self):
        _log ("Sync_Client.getIncomingMoveCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getIncomingMoveCount()

    def getOutgoingAddCount(self):
        _log ("Sync_Client.getOutgoingAddCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingAddCount()

    def getOutgoingAddSuccessCount(self):
        _log ("Sync_Client.getOutgoingAddSuccessCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingAddSuccessCount()

    def getOutgoingAddFailCount(self):
        _log ("Sync_Client.getOutgoingAddFailCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingAddFailCount()

    def getOutgoingAddAlreadyExistsCount(self):
        _log ("Sync_Client.getOutgoingAddAlreadyExistsCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingAddAlreadyExistsCount()

    def getOutgoingReplaceSuccessCount(self):
        _log ("Sync_Client.getOutgoingReplaceSuccessCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingReplaceSuccessCount()

    def getOutgoingReplaceFailCount(self):
        _log ("Sync_Client.getOutgoingReplaceFailCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingReplaceFailCount()

    def outgoingDeleteSuccessCount(self):
        _log ("Sync_Client.outgoingDeleteSuccessCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.outgoingDeleteSuccessCount()

    def getOutgoingDeleteFailCount(self):
        _log ("Sync_Client.getOutgoingDeleteFailCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getOutgoingDeleteFailCount()

    def getAllOutgoingChangeCount(self, strict=FALSE):
        _log ("Sync_Client.getAllOutgoingChangeCount(strict=%d)" % strict)
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getAllOutgoingChangeCount(strict)

    def getAllIncomingChangeCount(self, strict=FALSE):
        _log ("Sync_Client.getAllIncomingChangeCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getAllIncomingChangeCount(strict)

    def getSuspendCount(self):
        _log ("Sync_Client.getSuspendCount()")
        listener = self._client.getListener()
        if listener is None:
            return -1
        return listener.getSuspendCount()


######################################################################################
# PAB Client Wrapper
#
class PAB_Client:
    def __init__(self, cfgname, devid, user, domain, password, ab = None, mapfile = None, timeout = 600, apiVersion = 6, acc_login = None, acc_password = None):

        _log ("PAB_Client.__init__(cfgname=\"%s\") (devid=\"%s\") (ab=\"%s\") (user=\"%s\") (domain=\"%s\") (pwd=\"%s\") (apiVersion=\"%s\") (acc_login=\"%s\") (acc_password=\"%s\")" % (cfgname, devid, ab, user, domain, password, apiVersion, acc_login, acc_password) )

        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._authuser = cfg.get(cfgname, "user")
        self._authpassword = cfg.get(cfgname, "password")

        if devid is None or devid == "" :
            raise ValueError, "<devid> value not specified for PAB_Client"

        if user is None or user == "" :
            raise ValueError, "<user> value not specified for PAB_Client"

        if acc_login is None:
            if domain is None or domain == "" :
                raise ValueError, "<domain> value not specified for PAB_Client"

            if mapfile is None or mapfile == "":
                mapfile = cfg.get(cfgname, "vcardmap")

            if ab is None or ab == "":
                ab = "Default"

        _log ("PAB_Client.__init__(cfgname=\"%s\") (devid=\"%s\") (ab=\"%s\") (user=\"%s\") (domain=\"%s\") (pwd=\"%s\") (mgr=\"%s\") (mgrpwd=\"%s\") (mapfile=\"%s\")"
                % (cfgname, devid, ab, user, domain, password, self._authuser, self._authpassword, mapfile) )

        self._client = CPPABClient(testcase, self._host, self._port, apiVersion, ab, devid, user, domain, password, self._authuser, "", self._authpassword, mapfile, timeout, acc_login, acc_password)

        _log("PAB_Client.__init__ done")

    def initUser(self, user, domain, password):
        _log ("PAB_Client.initUser (user=\"%s\") (domain=\"%s\")" % (user, domain) )
        password = self._authpassword
        result = self._client.initUser(user, domain, password)
        return result

    def getUser(self):
        _log("PAB_Client.getUser")
        result = self._client.getUser()
        return result

    def readContact(self, id):
        _log ("PAB_Client.readContact (id=\"%s\") " % (id) )
        result = self._client.readContact(id)
        return result

    def readGroup(self, id):
         _log ("PAB_Client.readGroup (id=\"%s\") " % (id) )
         result = self._client.readGroup(id)
         return result

    def searchContact(self, attr, value):
        _log ("PAB_Client.searchContact (attr=\"%s\") (value=\"%s\")" % (attr, value) )
        result = self._client.searchContact(attr, value)
        return result

    def searchGroup(self, attr, value):
        _log ("PAB_Client.searchGroup (attr=\"%s\") (value=\"%s\")" % (attr, value) )
        result = self._client.searchGroup(attr, value)
        return result

    def NewPageOptions(self):
        _log ("PAB_Client.NewPageOptions")
        result = self._client.NewPageOptions()
        return result

    def NewPageOptionsWithIndexDetails(self, start_index = 0, num_entries = 0):
        _log ("PAB_Client.NewPageOptionsWithIndexDetails (start_index=\"%d\" num_entries=\"%d\")" % (start_index,num_entries))
        result = self._client.NewPageOptionsWithIndexDetails(start_index,num_entries)
        return result

    def NewPageOptionsWithPageDetails(self, page_index = -1, page_size = -1):
        _log ("PAB_Client.NewPageOptionsWithPageDetails (page_index=\"%d\" page_size=\"%d\")" % (page_index,page_size))
        result = self._client.NewPageOptionsWithPageDetails(page_index,page_size)
        return result

    def NewEntry(self):
        _log ("PAB_Client.NewEntry")
        result = self._client.NewEntry()
        return result

    def NewContact(self, url = None, ab = None):
        _log ("PAB_Client.NewContact")
        result = self._client.NewContact(url, ab)
        return result

    def NewAggregatedContact(self, url = None, ab = None):
        _log ("PAB_Client.NewAggregatedContact")
        result = self._client.NewAggregatedContact(url, ab)
        return result

    def NewACE(self, user, group, domain, acetype, accesstype):
        _log ("PAB_Client.NewACE")
        result = self._client.NewACE(user, group, domain, acetype, accesstype)
        return result

    def NewSearchEntry(self):
        _log ("PAB_Client.NewSearchEntry")
        result = self._client.NewSearchEntry()
        return result

    def NewSearchContact(self):
        _log ("PAB_Client.NewSearchContact")
        result = self._client.NewSearchContact()
        return result

    def NewSearchGroup(self):
        _log ("PAB_Client.NewSearchGroup")
        result = self._client.NewSearchGroup()
        return result

    def NewGroup(self, url = None, ab = None):
        _log("PAB_Client.NewGroup")
        result = self._client.NewGroup(url, ab)
        return result

    def NewSafetyEntry(self, type, value, friendly_name, bToRcpt, msgids):
        _log("PAB_Client.NewSafetyEntry")
        result = self._client.NewSafetyEntry(type, value, friendly_name, bToRcpt, msgids)
        return result

    def dabTemplateSet(self, user, name, attrs):
        _log("PAB_Client.dabTemplateSet (name=\"%s\")" % (name))
        self._client.dabTemplateSet(user, name, attrs)

    def dabTemplateGet(self, user, name):
        _log("PAB_Client.dabTemplateGet (name=\"%s\")" % (name))
        result = self._client.dabTemplateGet(user, name)
        return result

    def dabUserRelationshipGet(self, user, local, domain):
        _log("PAB_Client.dabUserRelationshipGet")
        result = self._client.dabUserRelationshipGet(user, local, domain)
        return result

    def dabEmailRelationshipGet(self, user, email):
        _log("PAB_Client.dabEmailRelationshipGet")
        result = self._client.dabEmailRelationshipGet(user, email)
        return result

    def dabMobileRelationshipGet(self, user, mobile):
        _log("PAB_Client.dabMobileRelationshipGet")
        result = self._client.dabMobileRelationshipGet(user, mobile)
        return result

    def dabTemplateList(self, user):
        _log("PAB_Client.dabTemplateList")
        result = self._client.dabTemplateList(user)
        return result

    def recvNotfList(self, user):
        _log("PAB_Client.recvNotfList")
        result = self._client.recvNotfList(user)
        return result

    def dabPrivacyTemplateSet(self, user, name, template):
        _log("PAB_Client.dabPrivacyTemplateSet (name=\"%s\") (template=\"%s\")" % (name, template))
        self._client.dabPrivacyTemplateSet(user, name, template)

    def dabPrivacyTemplateGet(self, user, name):
        _log("PAB_Client.dabPrivacyTemplateGet (name=\"%s\")" % (name))
        result = self._client.dabPrivacyTemplateGet(user, name)
        return result

    def setSearchEntryAttribute(self, entry, attr, value, criteria, matchAll = TRUE):
        _log ("PAB_Client.setSearchEntryAttribute attr=\"%s\") (value=\"%s\") (criteria=\"%s\")" % (attr, value, criteria) )
        self._client.setSearchEntryAttribute(entry, attr, value, criteria, matchAll)

    def setEntryAttribute(self, entry, attr, value):
        print_val = value.encode("ascii", "replace")
        _log ("PAB_Client.setEntryAttribute (attr=\"%s\") (value=\"%s\")" % (attr, print_val) )
        self._client.setEntryAttribute(entry, attr, value)

    def addEntryAttributeValue(self, entry, attr, value):
        print_val = value.encode("ascii", "replace")
        _log ("PAB_Client.addEntryAttributeValue (attr=\"%s\") (value=\"%s\")" % (attr, print_val) )
        self._client.addEntryAttributeValue(entry, attr, value)

    def setEntryBinAttribute(self, entry, attr, filename):
        _log ("PAB_Client.setEntryBinAttribute (attr=\"%s\") (filename=\"%s\")" % (attr, filename) )
        self._client.setEntryBinAttribute(entry, attr, filename)

    def getAttributes(self, entry):
        _log ("PAB_Client.getAttributes" )
        result = self._client.getAttributes(entry)
        return result

    def verifyAttribute(self, attrs, name, value):
        _log("PAB_Client.verifyAttribute (name=\"%s\") (value=\"%s\")" % (name, value))
        result = self._client.verifyAttribute(attrs, name, value);
        return result

    def setProfile(self, user, entry):
        _log("PAB_Client.setProfile")
        self._client.setProfile(user, entry)

    def getProfile(self, user):
        _log("PAB_Client.getProfile")
        result = self._client.getProfile(user)
        return result

    def accessProfile(self, user, local, domain):
        _log("PAB_Client.accessProfile (local=\"%s\") (domain=\"%s\")" % (local, domain))
        result = self._client.accessProfile(user, local, domain)
        return result

    def searchProfile(self, user, sentry, bMatchAll=TRUE):
        _log("PAB_Client.searchProfile")
        result = self._client.searchProfile(user, sentry, bMatchAll)
        return result

    def checkSearchResult(self, res, entry):
        _log("PAB_Client.checkSearchResult")
        found = self._client.checkSearchResult(res, entry)
        return found

    def checkTemplateListResult(self, res, name):
        _log("PAB_Client.checkTemplateListResult")
        found = self._client.checkTemplateListResult(res, name)
        return found

    def checkTemplateAttrResult(self, res, name):
        _log("PAB_Client.checkTemplateAttrResult")
        found = self._client.checkTemplateAttrResult(res, name)
        return found

    def checkRecvNotfListResult(self, res, type, address, events):
        _log("PAB_Client.checkRecvNotfListResult")
        found = self._client.checkRecvNotfListResult(res, type, address, events)
        return found

    def getEntryAttribute(self, entry, attr):
        _log ("PAB_Client.getEntryAttribute (attr=\"%s\")" % (attr))
        result = self._client.getEntryAttribute(entry, attr)
        return result

    def getEntryBinAttribute(self, entry, attr):
        _log ("PAB_Client.getEntryBinAttribute (attr=\"%s\")" % (attr))
        result = self._client.getEntryBinAttribute(entry, attr)
        return result

    def dabUserInvite(self, user, local, domain, profile = None, msg = None):
        _log ("PAB_Client.dabUserInvite (local=\"%s\") (domain=\"%s\") (profile=\"%s\") (msg=\"%s\")" % (local, domain, profile, msg))
        result = self._client.dabUserInvite(user, local, domain, profile, msg)
        return result

    def dabUserInviteResp(self, user, local, domain, profile, bAccept):
        _log ("PAB_Client.dabUserInvite (local=\"%s\") (domain=\"%s\") (profile=\"%s\") (bAccept=%d)" % (local, domain, profile, bAccept))
        self._client.dabUserInviteResp(user, local, domain, profile, bAccept)

    def dabUserLinkDelete(self, user, local, domain):
        _log ("PAB_Client.dabUserLinkDelete (local=\"%s\") (domain=\"%s\")" % (local, domain))
        self._client.dabUserLinkDelete(user, local, domain)

    def dabMobileInvite(self, user, mobile, profile = None, msg = None):
        _log ("PAB_Client.dabMobileInvite (mobile=\"%s\") (profile=\"%s\") (msg=\"%s\")" % (mobile, profile, msg))
        self._client.dabMobileInvite(user, mobile, profile, msg)

    def dabMobileInviteResp(self, user, mobile, bAccept):
        _log ("PAB_Client.dabMobileInviteResp (mobile=\"%s\") (bAccept=%d)" % (mobile, bAccept))
        self._client.dabMobileInviteResp(user, mobile, bAccept)

    def dabMobileLinkDelete(self, user, mobile):
        _log ("PAB_Client.dabMobileLinkDelete (mobile=\"%s\")" % (mobile))
        self._client.dabMobileLinkDelete(user, mobile)

    def dabEmailInvite(self, user, email, profile = None, msg = None):
        _log ("PAB_Client.dabEmailInvite (email=\"%s\") (profile=\"%s\") (msg=\"%s\")" % (email, profile, msg))
        self._client.dabEmailInvite(user, email, profile, msg)

    def dabEmailInviteResp(self, user, email, bAccept):
        _log ("PAB_Client.dabEmailInviteResp (email=\"%s\") (bAccept=%d)" % (email, bAccept))
        self._client.dabEmailInviteResp(user, email, bAccept)

    def dabEmailLinkDelete(self, user, email):
        _log ("PAB_Client.dabEmailLinkDelete (email=\"%s\")" % (email))
        self._client.dabEmailLinkDelete(user, email)

    def dabInviteList(self, user, type, status):
        _log ("PAB_Client.dabInviteList (type=\"%s\") (status=\"%s\")" % (type, status))
        result = self._client.dabInviteList(user, type, status)
        return result

    def dabEventList(self, user, lfrom = -1, lto = -1):
        _log ("PAB_Client.dabEventList")
        result = self._client.dabEventList(user, lfrom, lto)
        return result

    def dabProfileLinkList(self, user):
        _log ("PAB_Client.dabProfileLinkList")
        result = self._client.dabProfileLinkList(user)
        return result

#    def recvNotfSet(self, user, method, address, events):
#        _log("PAB_Client.recvNotfSet (method=\"%s\") (address=\"%s\") (events=\"%s\")" % (method, address, events))
#        self._client.recvNotfSet(user, method, address, events)

    def checkKnownProfiles(self, known_profiles, local, domain, url, bIgnored):
        _log ("PAB_Client.checkKnownProfiles (local=\"%s\") (domain=\"%s\") (url=\"%s\") (bIgnored=%d)" % (local, domain, url, bIgnored))
        result = self._client.checkKnownProfiles(known_profiles, local, domain, url, bIgnored)
        return result

    def checkUserInvites(self, user, invites, local, domain, status):
        _log ("PAB_Client.checkUserInvites (local=\"%s\") (domain=\"%s\") (status=\"%s\")" % (local, domain, status))
        result = self._client.checkUserInvites(user, invites, local, domain, None, None, status)
        return result

    def checkSocialNetworkEntry(self, sn_entry, attr, value):
        _log ("PAB_Client.checkSocialNetworkEntry (attr=\"%s\") (value=\"%s\")" % (attr, value))
        result = self._client.checkSocialNetworkEntry(sn_entry, attr, value)
        return result

    def checkCIFStatus(self, cif_status, uid, status, entry_url):
        _log ("PAB_Client.checkCIFStatus (uid=\"%s\") (status=\"%s\") (entry_url=\"%s\")" % (uid, status, entry_url))
        result = self._client.checkCIFStatus(cif_status, uid, status, entry_url)
        return result

    def checkEmailInvites(self, user, invites, email, status):
        _log ("PAB_Client.checkEmailInvites (email=\"%s\") (status=\"%s\")" % (email, status))
        result = self._client.checkUserInvites(user, invites, None, None, email, None, status)
        return result

    def checkMobileInvites(self, user, invites, mobile, status):
        _log("PAB_Client.checkMobileInvites (mobile=\"%s\") (status=\"%s\")" % (mobile, status))
        result = self._client.checkUserInvites(user, invites, None, None, None, mobile, status)
        return result

    def checkInviteSentEvent(self, user, events, local, domain, address):
        _log ("PAB_Client.checkInviteSentEvent (local=\"%s\") (domain=\"%s\") (address=\"%s\")" % (local, domain, address))
        result = self._client.checkInviteSentEvent(user, events, local, domain, address)
        return result

    def checkInviteRecvEvent(self, user, events, local, domain, msg):
        _log ("PAB_Client.checkInviteRecvEvent (local=\"%s\") (domain=\"%s\") (msg=\"%s\")" % (local, domain, msg))
        result = self._client.checkInviteRecvEvent(user, events, local, domain, msg)
        return result

    def checkUserInviteStatusEvent(self, user, events, local, domain, status):
        _log ("PAB_Client.checkInviteStatusEvent (local=\"%s\") (domain=\"%s\") (status=\"%s\")" % (local, domain, status))
        result = self._client.checkInviteStatusEvent(user, events, local, domain, None, None, status)
        return result

    def checkEmailInviteStatusEvent(self, user, events, email, status):
        _log ("PAB_Client.checkInviteStatusEvent (email=\"%s\") (status=\"%s\")" % (email, status))
        result = self._client.checkInviteStatusEvent(user, events, None, None, email, None, status)
        return result

    def checkMobileInviteStatusEvent(self, user, events, mobile, status):
        _log ("PAB_Client.checkInviteStatusEvent (mobile=\"%s\") (status=\"%s\")" % (mobile, status))
        result = self._client.checkInviteStatusEvent(user, events, None, None, None, mobile, status)
        return result

    def checkUserProfileUpdateEvent(self, user, events, local, domain, mod_attrs_schema, mod_attrs_display):
        _log ("PAB_Client.checkUserProfileUpdateEvent (local=\"%s\") (domain=\"%s\") (mod_attrs_schema=\"%s\") (mod_attrs_display=\"%s\")" % (local, domain, mod_attrs_schema, mod_attrs_display))
        result = self._client.checkUserProfileUpdateEvent(user, events, local, domain, mod_attrs_schema, mod_attrs_display)
        return result

    def checkUserStatusUpdateEvent(self, user, events, local, domain, status):
        _log ("PAB_Client.checkUserStatusUpdateEvent (local=\"%s\") (domain=\"%s\") (status=\"%s\")" % (local, domain, status))
        result = self._client.checkUserStatusUpdateEvent(user, events, local, domain, status)
        return result

    def checkConvertLinkEvent(self, user, events, addressType, address, local, domain):
        _log ("PAB_Client.checkConvertLinkEvent (addressType=\"%d\") (address=\"%s\") (local=\"%s\") (domain=\"%s\")"% (addressType, address, local, domain))
        result = self._client.checkConvertLinkEvent(user, events, addressType, address, local, domain)
        return result

    def checkNewFriendFoundEvent(self, user, events, connector, acc_name, num_friends):
        _log ("PAB_Client.checkNewFriendFoundEvent (connector=\"%s\") (accname=\"%s\") (num_friends=%d)" % (connector, acc_name, num_friends))
        result = self._client.checkNewFriendFoundEvent(user, events, connector, acc_name, num_friends)
        return result

    def checkUserProfileLinkList(self, user, links, local, domain):
        _log ("PAB_Client.checkProfileLinkList (local=\"%s\") (domain=\"%s\")" % (local, domain))
        result = self._client.checkProfileLinkList(user, links, local, domain, None, None)
        return result

    def checkEmailProfileLinkList(self, user, links, email):
        _log ("PAB_Client.checkProfileLinkList (email=\"%s\")" % (email))
        result = self._client.checkProfileLinkList(user, links, None, None, email, None)
        return result

    def checkMobileProfileLinkList(self, user, links, mobile):
        _log ("PAB_Client.checkProfileLinkList (mobile=\"%s\")" % (mobile))
        result = self._client.checkProfileLinkList(user, links, None, None, None, mobile)
        return result

    def checkACL(self, acl, user, domain, ace_type, access_type):
        _log("PAB_Client.checkACL (user=\"%s\") (domain=\"%s\") (type=%d) (access=%d)" % (user, domain, ace_type, access_type))
        result = self._client.checkACL(acl, user, domain, ace_type, access_type)
        return result

    def getEntryFromList(self, entries, name, value):
        _log("PAB_Client.getEntryFromList (name=\"%s\") (value=\"%s\")" % (name, value))
        result = self._client.getEntryFromList(entries, name, value)
        return result

    def updateContact(self, contact):
        _log ("PAB_Client.updateContact (contact=\"%s\")" % (contact.toString()) )
        self._client.updateContact(contact)

    def loadContact(self, vcf):
        _log ("PAB_Client.loadContact (vcf=\"%s\")" % (vcf) )
        return self._client.loadContact(vcf)

    def saveContact(self, contact, vcf):
        _log ("PAB_Client.saveContact (contact=\"%s\") vcf=\"%s\")" % (contact.toString(), vcf) )
        return self._client.saveContact(contact, vcf)

    def addContact(self, vcardfilename):
        self._client.addContact(vcardfilename)

    def deleteContact(self, attr, value):
        self._client.deleteContact(attr, value)

    def createab(self, addressbookname):
        self._client.createAB(addressbookname)

    def deleteab(self, addressbookurl):
        self._client.deleteAB(addressbookurl)

    def isab(self, addressbookurl):
        return self._client.isAB(addressbookurl)

    def dumpEntry(self, entry):
        _log("Dumping entry %s" % entry.getURL())
        attributes = entry.getAttributes()
        if attributes is not None:
            for i in range(len(attributes)):
                attr = attributes[i]
                buf = "   %s: " % attr.getName()

                values = attr.getValues()
                if values is not None:
                    for j in range(len(values)):
                        buf = "%s'%s' " % (buf, values[j])
                _log(buf)

#######################################################################################
# SSH Client

class SSH_Client:
    def __init__(self, cfgname, timeout=300000):
        _log("SSH_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._hostname = cfg.get(cfgname, "host")
        self._username = cfg.get(cfgname, "user")
        self._password = cfg.get(cfgname, "password")
        self._certificate_file = cfg.get(cfgname, "certificate")

        self._timeout = timeout
        self._client = SSHClient(testcase, self._hostname, self._username, self._password, self._certificate_file, self._timeout)

    def close(self):
        _log("SSH_Client.close")
        self._client.close()

    def setEnv(self, name, value):
        _log("SSH_Client.setEnv (name=\"%s\", value\"%s\")" % (name, value))
        return self._client.setEnv(name, value)

    def getExitCode(self):
        _log("SSH_Client.getExitCode")
        return self._client.getExitCode()

    def executeCommand(self, cmd):
        _log("SSH_Client.executeCommand (cmd=\"%s\")" % (cmd))
        return self._client.executeCommand(cmd)

    def executePutFile(self, localSource, remoteDest, recursive = FALSE):
        _log("SSH_Client.executePutFile \"%s\" -> \"%s\" (recursive=%s)" % (localSource, remoteDest, recursive))
        return self._client.executePutFile(localSource, remoteDest, recursive)

######################################################################################
# CP HTTP Client Wrapper (uses 'HttpApp' external application for testing the new HTTP stack)
#
class CP_HTTP_Client:
    def __init__(self, cfgname, baseDir, httpVersion="1.1", maxParallelConnections=5, maxCachedConnections=50, cacheTime=60, sendTimeout=10, readTimeout=10, connectTimeout=30, noDelay=FALSE, noKeepAlive=FALSE):
        _log ("CP_HTTP_Client.__init__(cfgname=\"%s\", baseDir=\"%s\", httpVersion=\"%s\", maxParallelConnections=%u, maxCachedConnections=%u, cacheTime=%u, sendTimeout=%u, readTimeout=%u, connectTimeout=%u, noDelay=%u, noKeepAlive=%u)" % (cfgname, baseDir, httpVersion, maxParallelConnections, maxCachedConnections, cacheTime, sendTimeout, readTimeout, connectTimeout, noDelay, noKeepAlive) )
        app_path = cfg.get(cfgname, "application_path")
        self._client = CpHttpClient(testcase, app_path, baseDir, httpVersion, maxParallelConnections, maxCachedConnections, cacheTime, sendTimeout, readTimeout, connectTimeout, noDelay, noKeepAlive)

    def startClient(self):
        _log ("CP_HTTP_Client.startClient()")
        return self._client.startClient()

    def stopClient(self):
        _log ("CP_HTTP_Client.stopClient()")
        return self._client.stopClient()

    def setCredentials(self, username, password):
        _log ("CP_HTTP_Client.setCredentials(username=\"%s\", password=\"%s\")" % (username, password) )
        self._client.setCredentials(username, password)

    def doGetRequest(self, url, toFilePath, httpVersion=None, bodyGenSize=-1, unknownBodyLength=FALSE):
        _log ("CP_HTTP_Client.doGetRequest(url=\"%s\", toFilePath=\"%s\", httpVersion=\"%s\", bodyGenSize=%d, unknownBodyLength=%u)" % (url, toFilePath, httpVersion, bodyGenSize, unknownBodyLength) )
        return self._client.doRequest("GET", url, httpVersion, None, bodyGenSize, unknownBodyLength, FALSE, toFilePath)

    def doHeadRequest(self, url, httpVersion=None, bodyGenSize=-1, unknownBodyLength=FALSE):
        _log ("CP_HTTP_Client.doHeadRequest(url=\"%s\", httpVersion=\"%s\")" % (url, httpVersion) )
        return self._client.doRequest("HEAD", url, httpVersion, None, bodyGenSize, unknownBodyLength, FALSE, None)

    def doPutRequest(self, url, fromFilePath, httpVersion=None, bodyGenSize=-1, unknownBodyLength=FALSE, expect100continue=FALSE):
        _log ("CP_HTTP_Client.doPutRequest(url=\"%s\", fromFilePath=\"%s\", httpVersion=\"%s\", bodyGenSize=%d, unknownBodyLength=%u, expect100continue=%u)" % (url, httpVersion, fromFilePath, bodyGenSize, unknownBodyLength, expect100continue) )
        return self._client.doRequest("PUT", url, httpVersion, fromFilePath, bodyGenSize, unknownBodyLength, expect100continue, None)

    def getRequestHeader(self, name):
        _log ("CP_HTTP_Client.getRequestHeader(name=\"%s\")" % (name) )
        return self._client.getRequestHeader(name)

    def getResponseStatus(self):
        _log ("CP_HTTP_Client.getResponseStatus()")
        return self._client.getResponseStatusCode()

    def getResponseHeader(self, name):
        _log ("CP_HTTP_Client.getResponseHeader(name=\"%s\")" % (name) )
        return self._client.getResponseHeader(name)

    def doCleanup(self):
        _log ("CP_HTTP_Client.doCleanup()")
        self._client.doCleanup()

    def doStatus(self):
        _log ("CP_HTTP_Client.doStatus()")
        self._client.doStatus()

    def getCounterValue(self, name):
        _log ("CP_HTTP_Client.getCounterValue(name=\"%s\")" % (name) )
        return self._client.getCounterValue(name)


######################################################################################
# CP HTTP Server Wrapper (uses 'HttpApp' external application for testing the new HTTP stack)
#
class CP_HTTP_Server:
    def __init__(self, cfgname, baseDir, proxyHost=None, proxyPort=0, proxySsl=FALSE, minHttpVersion="0.9", maxHttpVersion="1.1", maxActiveConnections=100, sendTimeout=10, readTimeout=10, noDelay=FALSE, noKeepAlive=FALSE):
        _log ("CP_HTTP_Server.__init__(cfgname=\"%s\", baseDir=\"%s\", proxyHost=\"%s\", proxyPort=%u, proxySsl=%u, minHttpVersion=\"%s\", maxHttpVersion=\"%s\", maxActiveConnections=%u, sendTimeout=%u, readTimeout=%u, noDelay=%u, noKeepAlive=%u)" % (cfgname, baseDir, proxyHost, proxyPort, proxySsl, minHttpVersion, maxHttpVersion, maxActiveConnections, sendTimeout, readTimeout, noDelay, noKeepAlive) )
        self._serverUrl = None
        self._cfgname = cfgname
        self._baseDir = baseDir
        app_path = cfg.get(cfgname, "application_path")
        self._server = CpHttpServer(testcase, app_path, baseDir, proxyHost, proxyPort, proxySsl, minHttpVersion, maxHttpVersion, maxActiveConnections, sendTimeout, readTimeout, noDelay, noKeepAlive)

    def startServer(self, listenPort=8880, listenSsl=FALSE):
        _log ("CP_HTTP_Server.startServer(listenPort=\"%u\", listenSsl=\"%u\")" % (listenPort, listenSsl) )
        self._hostname = "localhost"
        self._listenPort = listenPort
        self._listenSsl = listenSsl
        if listenSsl is TRUE:
            self._serverUrl = "https://localhost:%u" % (listenPort)
        else:
            self._serverUrl = "http://localhost:%u" % (listenPort)
        return self._server.startServer(listenPort, listenSsl)

    def startProxyServer(self, listenPort=8881, listenSsl=FALSE):
        _log ("CP_HTTP_Server.startProxyServer()")
        proxy_server = CP_HTTP_Server(self._cfgname, self._baseDir, self._hostname, self._listenPort, self._listenSsl)
        proxy_server.startServer(listenPort, listenSsl)
        return proxy_server

    def stopServer(self):
        _log ("CP_HTTP_Server.stopServer()")
        return self._server.stopServer()

    def getServerUrl(self):
        _log ("CP_HTTP_Server.getServerUrl()")
        return self._serverUrl

    def doCleanup(self):
        _log ("CP_HTTP_Server.doCleanup()")
        self._server.doCleanup()

    def doStatus(self):
        _log ("CP_HTTP_Server.doStatus()")
        self._server.doStatus()

    def getCounterValue(self, name):
        _log ("CP_HTTP_Server.getCounterValue(name=\"%s\")" % (name) )
        return self._server.getCounterValue(name)


#######################################################################################
#base64encoder/decoder

def Base64encode(data):
    return Base64Coder.encode(data)

def Base64decode(data):
    _log('Base64decode() data=\"%s\" ' % (data))
    return Base64Coder.decode(data)

######################################################################################
# Test routines

def testHeader(header, msg1, msg2, description="testHeader"):
    _log('testHeader() header=\"%s\" msg1=\"%s\" msg2=\"%s\"' % (header, msg1, msg2))
    if testcase is None:
        raise ValueError, "No testcase object found when executing testHeader()"
    if header is None:
        testcase.addResult(TestCase.FAILED,'testHeader: - invalid header parameter')
        return 0
    if msg1 is None:
        testcase.addResult(TestCase.FAILED,'testHeader: - invalid msg1 parameter')
        return 0
    if msg2 is None:
        testcase.addResult(TestCase.FAILED,'testHeader: - invalid msg2 parameter')
        return 0

    # compare headers
    try:
        hdr1 = getattr(msg1, header)
    except AttributeError:
        testcase.addResult(TestCase.FAILED,'%s: Failed to retrieve header [%s] from msg1' % (description, header))
        return 0;

    try:
        hdr2 = getattr(msg2, header)
    except AttributeError:
        testcase.addResult(TestCase.FAILED,'$s: Failed to retrieve header [%s] from msg2' % (description, header))
        return 0;
    else:
        if type(hdr1) == type(hdr2):
            if hdr1 == hdr2:
                testcase.addResult(TestCase.PASSED,'%s: [%s] headers are identical. Value = \"%s\"' % (description, header, hdr1))
                return 1
            else:
                testcase.addResult(TestCase.FAILED,'%s: [%s] headers are not identical. hdr1 = \"%s\", hdr2 = \"%s\"' % (description, header, hdr1, hdr2))
                return 0
        else:
            #print hdr1 , type(hdr1)
            #print hdr2 , type(hdr2)
            testcase.addResult(TestCase.FAILED,'%s: [%s] headers are of different type' % (description, header))
            return 0

def testTelnetSuccess(response, description="testTelnetSuccess"):
    _log('testTelnetSuccess() response=%s description=\"%s\"' % (repr(response.toString()), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testTelnetSuccess()"
    if response is None:
        testcase.addResult(TestCase.FAILED,'testTelnetSuccess: - invalid test parameter')
        return 0
    else:
        str = response.getLastLineResponse()
        if len(str) > 1 and str[0:1] == 'O' and str[1:2] == 'K':
            testcase.addResult(TestCase.PASSED, '%s' % (description))
            return TestCase.PASSED

    testcase.addResult(TestCase.FAILED, '%s' % (description))
    return TestCase.FAILED

def testTelnetResponse(response, expected, result=None, action=None, description="testTelnetResponse"):
    _log('testTelnetResponse() response=%s expected=%s description=\"%s\"' % (repr(response.toString()), repr(expected), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testTelnetResponse()"
    if response is None or expected is None:
        testcase.addResult(TestCase.FAILED,'testTelnetResponse: - invalid test parameter')
        return 0
    else:
        if response.checkResponse(expected):
            testcase.addResult(TestCase.PASSED,'%s - Got expected response. Value = \"%s\"' % (description, expected) )
            return TestCase.PASSED
        else:
            responseStr = response.toString()
            if responseStr[len(responseStr)-1] == '\n':
                responseStr = responseStr[0:len(responseStr)-1]
            if result is None:
                testcase.addResult(TestCase.FAILED,'%s - Got unexpected response. Looking for \"%s\". Got \"%s\"'% (description, expected, responseStr))
                res = TestCase.FAILED
            else:
                testcase.addResult(result,'%s - Got unexpected response. Looking for \"%s\". Got \"%s\"' % (description, expected, responseStr))
                res = result

#            print action , type(action)
#            if action == "QUIT":
#               sys.exit()

            return res;

def testTelnetExtendedResponse(response, expected, result=None, action=None, description="testTelnetExtendedResponse"):
    _log('testTelnetExtendedResponse() response=%s expected=%s description=\"%s\"' % (repr(response.toString()), repr(expected), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testTelnetExtendedResponse()"
    if response is None or expected is None:
        testcase.addResult(TestCase.FAILED,'testTelnetResponse: - invalid test parameter')
        return 0
    else:
        if response.checkExtendedResponse(expected):
            testcase.addResult(TestCase.PASSED,'%s - Got expected response. Value = \"%s\"' % (description, response.getExtended()))
            return 1
        else:
            testcase.addResult(TestCase.FAILED,'%s - Got unexpected response. Looking for \"%s\". Got \"%s\"' % (description, expected, response.getExtended()) )
            return 1

def testTelnetResponseCount(response, expected, description="testTelnetResponseCount"):
    _log('testTelnetResponseCount() response=%s expected=%s description=\"%s\"' % (repr(response.getResponse()), repr(expected), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testTelnetResponseCount()"
    if response is None or expected is None:
        testcase.addResult(TestCase.FAILED,'testTelnetResponseCount: - invalid test parameter')
        return 0

    if expected == response.getResponseCount():
        testcase.addResult(TestCase.PASSED,'%s: - Got expected response count \"%s\"' % (description, expected) )
        return 1

    testcase.addResult(TestCase.FAILED,'%s: - Got unexpected response count. Looking for \"%s\" responses. Got \"%s\"' % (description, expected, response.getResponse()))
    return 1

def testSearchTelnetResponseList(response, expected, description="testSearchTelnetResponseList", ignorecase=FALSE, fail_on_match=FALSE):
    if fail_on_match == FALSE:
        _log('testSearchTelnetResponseList() response=%s expected=%s description=\"%s\" ignorecase=%u' % (repr(response.toString()), repr(expected), description, ignorecase))
    else:
        _log('testSearchTelnetResponseList() response=%s expected=%s description=\"%s\" ignorecase=%u, fail_on_match=TRUE' % (repr(response.toString()), repr(expected), description, ignorecase))
    if testcase is None:
        raise ValueError, "No testcase specified for testSearchTelnetResponseList()"
    if response is None or expected is None:
        testcase.addResult(TestCase.FAILED,'testSearchTelnetResponseList: - invalid test parameter')
        return 0
    else:
        if ignorecase == TRUE:
            if response.searchResponseList(expected, 1):
                if fail_on_match == FALSE:
                    testcase.addResult(TestCase.PASSED,'%s: - Got expected response. Value = \"%s\"' % (description,expected) )
                    return 1
            else:
                if fail_on_match == TRUE:
                    testcase.addResult(TestCase.PASSED,'%s: - Got expected response. Value = \"%s\"' % (description,expected) )
                    return 1
        else:
            if response.searchResponseList(expected, 0):
                if fail_on_match == FALSE:
                    testcase.addResult(TestCase.PASSED,'%s: - Got expected response. Value = \"%s\"' % (description,expected) )
                    return 1
            else:
                if fail_on_match == TRUE:
                    testcase.addResult(TestCase.PASSED,'%s: - Got expected response. Value = \"%s\"' % (description,expected) )
                    return 1

        responseStr = response.toString()
        if responseStr[len(responseStr)-1] == '\n':
            responseStr = responseStr[0:len(responseStr)-1]
        testcase.addResult(TestCase.FAILED,'%s: - Got unexpected response. Looking for \"%s\". Got \"%s\"' % (description, expected, responseStr))
        return 0

def testSearchString(str1, srchstr, description="testSearchString", fail_on_match = FALSE ):
    if fail_on_match:
        _log('testSearchString() string=%s srchstr=%s description=\"%s\" fail_on_match=TRUE' % (repr(str1), repr(srchstr), description))
    else:
        _log('testSearchString() string=%s srchstr=%s description=\"%s\"' % (repr(str1), repr(srchstr), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testSearchString()"
    if str1 is None:
        testcase.addResult(TestCase.FAILED, "testSearchString - invalid parameter str1 is null")
        return FALSE
    if srchstr is None:
        testcase.addResult(TestCase.FAILED, "testSearchString - invalid parameter srchstr is null")
        return FALSE

    # trim strings for display
    if len(srchstr) > 20:
        disp_srchstr = "[%0.20s...]" % repr(srchstr)
    else :
        disp_srchstr = "[%s]" % repr(srchstr)

    if len(str1) > 20:
        disp_str1 = "[%0.20s...]" % repr(str1)
    else :
        disp_str1 = "[%s]" % repr(str1)

    indx = str1.find(srchstr)

    if indx == -1:
        if fail_on_match != 0:
            testcase.addResult(TestCase.PASSED, '%s - as expected did not find %s in %s' % (description, disp_srchstr, disp_str1) )
            return TRUE
        else:
            testcase.addResult(TestCase.FAILED, '%s - did not find %s in %s' % (description, disp_srchstr, disp_str1) )
            return FALSE
    else:
        if fail_on_match != 0:
            testcase.addResult(TestCase.FAILED, '%s - unexpectedly found %s in %s' % (description, disp_srchstr, disp_str1) )
            return FALSE
        else:
            testcase.addResult(TestCase.PASSED, '%s - found %s in %s' % (description, disp_srchstr, disp_str1) )
            return TRUE

def testMatchString(str1, srchstr, description="testMatchString", fail_on_match = FALSE, startsWithMatch = FALSE ):
    """do an exact match
    """
    if fail_on_match:
        _log('testMatchString() string=%s srchstr=%s description=\"%s\" fail_on_match=TRUE startsWithMatch=%u' % (repr(str1), repr(srchstr), description, startsWithMatch))
    else:
        _log('testMatchString() string=%s srchstr=%s description=\"%s\" startsWithMatch=%u' % (repr(str1), repr(srchstr), description,  startsWithMatch))

    if testcase is None:
        raise ValueError, "No testcase specified for testMatchString()"
    if str1 is None or srchstr is None:
        testcase.addResult(TestCase.FAILED, "testMatchString - invalid test parameter")
        return FALSE

    if len(srchstr) > 20:
        disp_srchstr = "[%0.20s...]" % repr(srchstr)
    else :
        disp_srchstr = "[%s]" % repr(srchstr)

    if len(str1) > 20:
        disp_str1 = "[%0.20s...]" % repr(str1)
    else :
        disp_str1 = "[%s]" % repr(str1)


    # the jython match method matches patterns at the beginning of the string
    # and the search function examines the whole string.
    # Paul - removed regexp matching here.
    # if we used regexp matching the user must know that and write srch string as regexp
    # or else we escape all special regexp characters
    #match = re.match(srchstr, str1)

   # make it an exact match
    if not startsWithMatch :
        if len(srchstr) != len(str1) :
            if fail_on_match == 0:
                testcase.addResult(TestCase.FAILED, '%s - lengths do not match (len(srchstr)=%i != %i). Matching %s in %s' % (description, len(srchstr),len(str1), disp_srchstr, disp_str1) )
                return FALSE

    indx = str1.find(srchstr)

    # must be at start - this is difference to search
    if indx != 0:
        if fail_on_match != 0:
            testcase.addResult(TestCase.PASSED, '%s - as expected did not match %s in %s' % (description, disp_srchstr, disp_str1) )
            return TRUE
        else:
            for i in range(min(len(srchstr),len(str1))):
                if srchstr[i] != str1[i]:
                    break
            testcase.addResult(TestCase.FAILED, '%s - mismatch at character %i of [%0.20s...] in [%0.20s...]' % (description, i, repr(srchstr[i:]), repr(str1[i:])) )
            return FALSE
    else:
        if fail_on_match != 0:
            testcase.addResult(TestCase.FAILED, '%s - unexpectedly matched %s in %s' % (description, disp_srchstr, disp_str1) )
            return FALSE
        else:
            testcase.addResult(TestCase.PASSED, '%s - matched %s in %s' % (description, disp_srchstr, disp_str1) )
            return TRUE

def testStartsWithString(str1, srchstr, description="testStartsWithString"):
    _log('testStartsWithString() string=%s srchstr=%s description=\"%s\"' % (repr(str1), repr(srchstr), description))
    return testMatchString(str1, srchstr, description, startsWithMatch=TRUE)

def testIsTrue(value, description="testIsTrue"):
    """this function adds a PASS result if supplied value is true
    """
    _log('testIsTrue() value=%s description=\"%s\"' % (repr(value), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testIsTrue()"

    if value is None:
        testcase.addResult(TestCase.FAILED,'%s  - value is null' % description)
        return FALSE
    else:
        if value == 1:
            testcase.addResult(TestCase.PASSED,'%s - value is true' % description)
            return TRUE
        else:
            if value == TRUE or value == true:
                testcase.addResult(TestCase.PASSED,'%s - value is true' % description)
                return TRUE
            else:
                testcase.addResult(TestCase.FAILED,'%s  - value is not true' % description)
                return FALSE

def testIsFalse(value, description="testIsFalse"):
    """this function adds a PASS result if supplied value is FALSE
    """
    _log('testIsFalse() value=%s description=\"%s\"' % (repr(value), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testIsTrue()"
    if value is None:
        testcase.addResult(TestCase.FAILED,'%s  - value is null' % description)
    else:
        if value == 0:
            testcase.addResult(TestCase.PASSED,'%s - value is false' % description)
            return TRUE
        else:
            if value == FALSE or value == false:
                testcase.addResult(TestCase.PASSED,'%s - value is FALSE' % description)
                return TRUE
            else:
                testcase.addResult(TestCase.FAILED,'%s  - value is not FALSE' % description)
                return FALSE

def testNotNull(value, description="testNotNull"):
    """this function adds a PASS result if supplied value is NOT Null
    """
    _log('testNotNull() value=%r description=\"%s\"' % (repr(value), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNotNull()"
    if value is None:
        testcase.addResult(TestCase.FAILED,'%s  - value is null' % description)
        return FALSE
    else:
        testcase.addResult(TestCase.PASSED,'%s - value is not null' % description)
        return TRUE

def testIsNull(value, description="testIsNull"):
    """this function adds a PASS result if value is Null
    """
    _log('testIsNull() value=%s description=\"%s\"' % (repr(value), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNotNull()"
    if value is None:
        testcase.addResult(TestCase.PASSED,'%s - value is null' % description)
        return TRUE
    else:
        testcase.addResult(TestCase.FAILED,'%s  - value [%s] not null' % (description, value) )
        return FALSE

def testIsEmpty(value, description="testIsEmpty"):
    """this function adds a PASS result if the vector is empty
    """
    _log('testIsEmpty value=%s description=\"%s\"' % (repr(value), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNotNull()"
    if value.size() == 0:
        testcase.addResult(TestCase.PASSED,'%s - value is empty' % description)
        return TRUE
    else:
        testcase.addResult(TestCase.FAILED,'%s  - value [%s] not empty' % (description, value) )
        return FALSE


def testSetResultFail(passed=TestCase.FAILED, details = "FAIL result set by test script", description="testSetResultFail"):
    """this function should not normally be called from user script.
    Use one of the testBlahblah() functions above instead
    If an appropriate test function does not exist then add one
    """
    return testSetResult(FALSE, details, description)

def testSetResultPass(details = "PASS result set by test script", description="testSetResultPass"):
    """this function should not normally be called from user script.
    Use one of the testBlahblah() functions above instead
    If an appropriate test function does not exist then add one
    """
    return testSetResult(TRUE, details, description)

def testSetResultSkipped(details = "SKIPPED result set by test script"):
    """call this function before exiting a script which cannot be run
    """
    return testSetResult(2, details, "")

def testSetResultBroken(details = "BROKEN result set by test script"):
    """call this function before exiting a script which will not be run
    due to a known issue with either the code or the test
    """
    return testSetResult(3, details, "")

def testSetResult(passed, details = "testSetResult()", description="testSetResult"):
    """this function should not normally be called from user script.
    Use one of the testBlahblah() functions above instead
    If an appropriate test function does not exist then add one
    """
    _log('testSetResult() passed=\"%s\" details=\"%s\" description=\"%s\"' % (str(passed), details, description))
    if testcase is None:
        raise ValueError, "No testcase specified for testSetResult()"
    if passed is None:
        testcase.addResult(TestCase.FAILED,'testSetResult: - invalid parameter \"passed\"')
        return FALSE
    passed = str(passed).upper()
    if passed in [ '0', 'FAIL', 'FAILED', 'FALSE', 'N', 'NO' ] :
        testcase.addResult(TestCase.FAILED,'%s  - %s' % (description, details))
        return FALSE
    elif passed in [ '1', 'PASS', 'PASSED', 'TRUE', 'Y', 'YES', 'SUCCESS' ] :
        testcase.addResult(TestCase.PASSED,'%s  - %s' % (description, details))
        return TRUE
    elif passed in [ '2', 'SKIP', 'SKIPPED', 'NORESULT' ] :
        testcase.addResult(TestCase.SKIPPED,'%s' % (details))
        return TRUE
    elif passed in [ '3', 'BROKEN' ] :
        testcase.addResult(TestCase.BROKEN,'%s' % (details))
        return TRUE
    else:
        testcase.addResult(TestCase.FAILED,'testSetResult: - Don\'t know how to interpret parameter \"passed\" = \"%s\"' % passed)
        return FALSE


def testNumEquals(num, expected, description="testNumEquals"):
    _log('testNumEquals() num=%s expected=%s description=\"%s\"' % (str(num), repr(expected), description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNumEquals()"
    if num is None or expected is None:
        testcase.addResult(TestCase.FAILED, "testNumEquals - invalid test parameter")
        return FALSE
    try:
        inum = int(num)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumEquals - invalid [num] parameter:",num)
        return FALSE

    try:
        iexp = int(expected)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumEquals - invalid [expected] parameter:",expected)
        return FALSE

    if inum == iexp:
        testcase.addResult(TestCase.PASSED, '%s  - %d is expected value' % (description,inum))
        return TRUE
    else:
        testcase.addResult(TestCase.FAILED, '%s  - %d not equal to expected value %d' % (description,inum,iexp))
        return FALSE

def testNumPositive(num, nullallowed = FALSE, description="testNumPositive"):
    _log('testNumPositive() num=%s nullallowed=%d description=\"%s\"' % (str(num), nullallowed, description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNumPositive()"
    if num is None:
        testcase.addResult(TestCase.FAILED, "testNumPositive - invalid test parameter")
        return FALSE
    try:
        inum = int(num)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumPositive - invalid [num] parameter:",num)
        return FALSE

    if nullallowed:
        if inum >= 0:
            testcase.addResult(TestCase.PASSED, '%s  - %d is a positive or null value' % (description, num))
            return TRUE
        else:
            testcase.addResult(TestCase.FAILED, '%s  - %d is not a positive or null value' % (description, num))
            return FALSE

    else:
        if inum > 0:
            testcase.addResult(TestCase.PASSED, '%s  - %d is a strictly positive value' % (description, num))
            return TRUE
        else:
            testcase.addResult(TestCase.FAILED, '%s  - %d is not a strictly positive value' % (description, num))
            return FALSE


# useful for testing HTTP response
def testNumInRange(num, start, end, description="testNumInRange", fail_on_match = FALSE):
    _log('testNumInRange() num=%s start=%s end=%s fail_on_match=%s description=\"%s\"' % (str(num), str(start), str(end), fail_on_match, description))
    if testcase is None:
        raise ValueError, "No testcase specified for testNumInRange()"
    if num is None or start is None or end is None:
        testcase.addResult(TestCase.FAILED, "testNumInRange - invalid test parameter")
        return FALSE
    try:
        inum = int(num)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumInRange - invalid [num] parameter:",num)
        return FALSE

    try:
        istart = int(start)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumInRange - invalid [start] parameter:",expected)
        return FALSE

    try:
        iend = int(end)
    except ValueError:
        testcase.addResult(TestCase.FAILED, "testNumInRange - invalid [end] parameter:",num)
        return FALSE

    if inum >= istart and inum <= iend:
        if fail_on_match:
            testcase.addResult(TestCase.FAILED, '%s  - %d unexpectedly in range [%d..%d]' % (description,num,start,end))
            return FALSE
        testcase.addResult(TestCase.PASSED, '%s  - %d in range [%d..%d]' % (description,num,start,end))
        return TRUE
    else:
        if fail_on_match:
            testcase.addResult(TestCase.PASSED, '%s  - %d not in range [%d..%d] as expected' % (description,num,start,end))
            return TRUE
        testcase.addResult(TestCase.FAILED, '%s  - %d not in range [%d..%d]' % (description,num,start,end))
        return FALSE


def testIsStringInArray(str, strings, mustBeFound = TRUE, description="testIsStringInArray"):
    _log('testIsStringInArray() str=\"%s\" strings=%s description=\"%s\"' % (str, strings, description))
    count = 0
    if strings is None:
        if mustBeFound:
            testcase.addResult(TestCase.FAILED, '%s  - %s is not in [%s]' % (description, str, strings))
            return FALSE
        else:
            testcase.addResult(TestCase.PASSED, '%s  - %s not found in [%s]' % (description, str, strings))
            return TRUE
    else:
        while count < len(strings):
            if strings[count] == str:
                if mustBeFound:
                    testcase.addResult(TestCase.PASSED, '%s  - %s is in [%s]' % (description, str, strings))
                    return TRUE
                else:
                    testcase.addResult(TestCase.FAILED, '%s  - %s must not be found in [%s]' % (description, str, strings))
                    return FALSE
                return
            count = count + 1
    if mustBeFound:
        testcase.addResult(TestCase.FAILED, '%s  - %s is not in [%s]' % (description, str, strings))
        return FALSE
    else:
        testcase.addResult(TestCase.PASSED, '%s  - %s not found in [%s]' % (description, str, strings))
        return TRUE

def testMrsQueusAreEmpty(description="test all MRS queues are empty"):
    _log('testMrsQueusAreEmpty() description=\"%s\"' % (description))
    if testcase is None:
        raise ValueError, "No testcase available for testMrsQueusAreEmpty()"
    nonemptyqueues = mrsNonEmptyQueues(clear=TRUE) # empty the queus as well
    if nonemptyqueues is None:
        testcase.addResult(TestCase.PASSED, 'All queues are empty')
        return TRUE
    else:
        testcase.addResult(TestCase.FAILED, "MRS queues not empty - %s" % nonemptyqueues)
        return FALSE


# return queue name of non empty queue
def mrsNonEmptyQueues(clear=FALSE):
    ret = None
    empty=TRUE
    if isAvailable("MRSTELNET1"):
        mgr = MGR_Client("MRSTELNET1", 30)
        qlist = mgr.getListString("MQ SUMMARY")
        for q in qlist:
            if not q.endswith(' 0 0 0'):
                empty = FALSE
        if empty:
            return ret
        # messages in queue- list them
        outlist = mgr.getListString("PLUGIN OUTBOUND LIST")
        for outbound in outlist:
            msglist = mgr.getListString("MQ LIST %s" % outbound)
            if len(msglist) > 0:
                if ret:
                    ret = "%s,%s" % (ret, outbound)
                else:
                    ret = outbound
                trace("re=%s" % (ret))
                for msg in msglist:
                    # E.g. * PD smpp 467BAF58 14 1
                    start = msg.find(outbound)
                    if start >= 0 :
                        end = msg.find(' ',start+len(outbound)+1)
                        if end >= 0 :
                            msgtext = mgr.send("MQ SHOW %s" % msg[start:end]).toString()
                            _log(msgtext)
                if clear:
                    _log("MQ clear %s" % outbound)
                    _log(mgr.send("MQ clear %s" % outbound).toString())
    return ret

def checkTelnetSuccess(response, description="checkTelnetSuccess"):
    _log('checkTelnetSuccess() response=%s description=\"%s\"' % (repr(response.toString()), description))

    if response is None:
        return TestCase.FAILED

    else:
        str = response.getLastLineResponse()
        if len(str) > 1 and str[0:1] == 'O' and str[1:2] == 'K':
            return TestCase.PASSED

    return TestCase.FAILED



######################################################################################
#  HELPFUL Message Routines

def getMMSCmdText(msg):
    text = MsgHandler.getMMSCommandTextResponse(msg)
    if text is None:
        disp_text = "null"
    else :
        disp_text = "[%s]" % text
    _log("getMMSCmdText() returns %s" % (disp_text) )
    return text

def setMMSCmdText(msg, text):
    ret = MsgHandler.addMMSTextPart(msg, text)
    if len(text) > 100:
        disp_text = "[%0.100s...]" % repr(text)
    else :
        disp_text = "[%s]" % text
    _log("setMMSCmdText(text=%s) returns %s" % (disp_text,ret) )
    return ret

def setMMSFrom(msg, address):
    ret = MsgHandler.setMMSFrom(msg, address)
    _log("setMMSFrom(address=\"%s\") returns [%s]" % (address, ret) )
    return ret

def getMMSFrom(msg):
    ret=  MsgHandler.getMMSFrom(msg)
    _log("getMMSFrom() returns [%s]" % (ret) )
    return ret

def setMMSSubject(msg, subject):
    ret = MsgHandler.setMMSSubject(msg, subject)
    if len(subject) > 100:
        disp_text = "[%0.100s...]" % repr(subject)
    else :
        disp_text = "[%s]" % subject
    _log("setMMSSubject(subject=%s) returns [%s]" % (disp_text, ret) )
    return ret

def getMMSSubject(msg):
    ret=  MsgHandler.getMMSSubject(msg)
    _log("getMMSSubject() returns [%s]" % (ret) )
    return ret

def setMMSTo(msg, address):
    ret = MsgHandler.setMMSTo(msg, address)
    _log("setMMSTo(address=%s) returns [%s]" % (address, ret) )
    return ret

def setMMSCc(msg, address):
    ret = MsgHandler.setMMSCc(msg, address)
    _log("setMMSCc(address=%s) returns [%s]" % (address, ret) )
    return ret

def tostringMMS(msg):
    return MsgHandler.printMMS(msg)

######################################################################################
# POP Client Wrapper

class POP_Client:
    def __init__(self, cfgname, login, password, apop = FALSE, ssl = FALSE):
        _log ("POP_Client.__init__(cfgname=\"%s\", login=\"%s\", pwd=\"%s\", apop=%d, ssl=%d" % (cfgname, login, password, apop, ssl) )

        self._host = cfg.get(cfgname, "host")
        self._port = cfg.get(cfgname, "port")
        self._client = POPClient(testcase, self._host, "%u" % self._port, login, password, apop, ssl )

    def getMessageCount(self):
        """return the Message count"""
        _log ('POP_Client.getMessageCount()')
        if self._client == None:
            raise ValueError, "getMessageCount: Error - POP_Client is not initialized"

        count = self._client.getMessageCount()
        if count < 0:
            raise ValueError, "getMessageCount: Error - POP_Client failed to return message count"
        _log ('POP_Client.getMessageCount() returns %d' % count)
        return count

    def deleteMessage(self, count):
        """delete the Message count"""
        _log ('POP_Client.deleteMessage()')
        if self._client == None:
            raise ValueError, "deleteMessage: Error - POP_Client is not initialized"

        if self._client.deleteMessage(count):
            return TRUE
        raise ValueError, "deleteMessage: Error - POP_Client failed to delete message count"


    def unDeleteMessage(self, count):
        """undelete the Message count"""
        _log ('POP_Client.unDeleteMessage()')
        if self._client == None:
            raise ValueError, "unDeleteMessage: Error - POP_Client is not initialized"

        if self._client.unDeleteMessage(count):
            return TRUE
        raise ValueError, "unDeleteMessage: Error - POP_Client failed to undelete message count"

    def getMessages(self):
        """return a HarnessMessage list """
        _log ('POP_Client.getMessages()')
        if self._client == None:
            raise ValueError, "getMessages: Error - POP_Clients is not initialized"

        messages = self._client.getMessages()
        if messages == None:
            raise ValueError, "getMessages: Error - POP_Client failed to return message list"

        return messages

    def getMessage(self, msgno):
        """return a HarnessMessage by its msgno"""
        _log (('POP_Client.getMessage(%s)') % (msgno))

        if self._client == None:
            raise ValueError, "getMessage: Error - POP_Client is not initialized"

        message = self._client.getMessage(msgno)
        if message == None:
            raise ValueError, "getMessage: Error - POP_Client failed to return message list"

        return message

    def getUIDs(self):
        """return POPUIDs"""
        _log ('POP_Client.getUIDs()')

        if self._client == None:
            raise ValueError, "getUIDs: Error - POP_Client is not initialized"

        uids = self._client.getUIDs()
        if uids == None:
            raise ValueError, "getUIDs: Error - POP_Client failed to return UID list"

        return uids

    def getSizes(self):
        """return POP message sizes"""
        _log ('POP_Client.getSizes()')

        if self._client == None:
            raise ValueError, "getSizes: Error - POP_Client is not initialized"

        sizes = self._client.getSizes()
        if sizes == None:
            raise ValueError, "getSizes: Error - POP_Client failed to return size list"

        return sizes

    def close(self, expunge = TRUE):
        _log ("POP_Client.close()")
        self._client.close(expunge)


######################################################################################
# IMAP Client Wrapper

class IMAP_Client:
    def __init__(self, cfgname, login, password, ssl = FALSE):
        _log ("IMAP_Client.__init__(cfgname=\"%s\", login=\"%s\", pwd=\"%s\", ssl=%d" % (cfgname, login, password, ssl) )

        self._host = cfg.get(cfgname, "host")
        self._port = cfg.get(cfgname, "port")
        self._client = IMAPClient(testcase, self._host, "%u" % self._port, login, password,  ssl )

    def getMessageCount(self):
        """return the Message count"""
        _log ('IMAP_Client.getMessageCount()')
        if self._client == None:
            raise ValueError, "getMessageCount: Error - IMAP_Client is not initialized"

        count = self._client.getMessageCount()
        if count < 0:
            raise ValueError, "getMessageCount: Error - IMAP_Client failed to return message count"

        _log ('IMAP_Client.getMessageCount() returns %d' % count)
        return count

    def deleteMessage(self, count):
        """delete the Message count"""
        _log ('IMAP_Client.deleteMessage(%d) ' % count)
        if self._client == None:
            raise ValueError, "deleteMessage: Error - IMAP_Client is not initialized"

        if self._client.deleteMessage(count):
            return TRUE
        raise ValueError, "deleteMessage: Error - IMAP_Client failed to delete message count"

    def unDeleteMessage(self, count):
        """undelete the Message count"""
        _log ('IMAP_Client.unDeleteMessage()')
        if self._client == None:
            raise ValueError, "unDeleteMessage: Error - IMAP_Client is not initialized"

        if self._client.unDeleteMessage(count):
            return TRUE
        raise ValueError, "unDeleteMessage: Error - IMAP_Client failed to undelete message count"

    def expungeMessages(self):

        """expunge messages"""
        _log ('IMAP_Client.expungeMessages()')
        if self._client == None:
            raise ValueError, "expungeMessages: Error - IMAP_Client is not initialized"

        return self._client.expungeMessages()

    def getMessages(self):
        """return a HarnessMessage list """
        _log ('IMAP_Client.getMessages()')
        if self._client == None:
            raise ValueError, "getMessages: Error - IMAP_Clients is not initialized"

        messages = self._client.getMessages()
        if messages == None:
            raise ValueError, "getMessages: Error - IMAP_Client failed to return message list"

        return messages

    def getMessage(self, msgno):
        """return a HarnessMessage by its msgno"""
        _log ('IMAP_Client.getMessage(%d)' % (msgno))

        if self._client == None:
            raise ValueError, "getMessage: Error - IMAP_Client is not initialized"

        message = self._client.getMessage(msgno)
        if message == None:
            raise ValueError, "getMessage: Error - IMAP_Client failed to return message list"

        return message

    def copyMessages(self, folderFrom, folderTo):
        _log ("IMAP_Client.copyMesssages()")
        if self._client.copyMessages(folderFrom, folderTo):
            return TRUE
        return FALSE

    def getUIDs(self):
        """return IMAPUIDs"""
        _log ('IMAP_Client.getUIDs()')

        if self._client == None:
            raise ValueError, "getUIDs: Error - IMAP_Client is not initialized"

        uids = self._client.getUIDs()
        if uids == None:
            raise ValueError, "getUIDs: Error - IMAP_Client failed to return UID list"

        return uids

    def close(self, expunge = TRUE):
        _log ("IMAP_Client.close()")
        self._client.close(expunge)

    def createFolder(self, name):
        _log ("IMAP_Client.createFolder()")
        if self._client.createFolder(name):
            return TRUE
        return FALSE

    def deleteFolder(self, name, recurse = FALSE):
        _log ("IMAP_Client.deleteFolder()")
        if self._client.deleteFolder(name, recurse):
            return TRUE
        return FALSE

    def renameFolder(self, oldname, newname):
        _log ("IMAP_Client.renameFolder()")
        if self._client.renameFolder(oldname, newname):
            return TRUE
        return FALSE

    def selectFolder(self, foldername):
        _log ("IMAP_Client.selectFolder()")
        if self._client.selectFolder(foldername):
            return TRUE
        return FALSE

    def listFolders(self, root = None):
        if root == None:
            _log ('IMAP_Client.listFolders(top-level)')
        else:
            _log ('IMAP_Client.listFolders(%s)' % root)

        if self._client == None:
            raise ValueError, "listFolders: Error - IMAP_Client is not initialized"

        return self._client.listFolders(root)

    def getFolder(self, name):
        _log ("IMAP_Client.getFolder(%s)" % name)
        return self._client.getFolder(name)

    def createMessage(self):
        _log ("IMAP_Client.createMessage()")
        return self._client.createMessage()

    def appendMessage(self, message):
        _log ("IMAP_Client.appendMessage()")
        return self._client.appendMessage(message)

    def listSubscribed(self, root = None):
        _log ("IMAP_Client.listSubscribed()")
        return self._client.listSubscribed(root)

######################################################################################
# SMTP Client Wrapper

class SMTP_Client:
    """ Use smtpfrom to explicitly set the SMTP FROM: attribute when sending a message
        Otherwise from: field in message will be used"""
    def __init__(self, cfgname='SMTPIn1', smtpfrom = None):
        _log ("SMTP_Client.__init__(cfgname=\"%s\", smtpfrom=\"%s\")" % (cfgname,smtpfrom) )
        self._host = cfg.get(cfgname, "host")
        self._port = cfg.get(cfgname, "port")
        self._client = SMTPClient(testcase, self._host, "%u" % self._port, smtpfrom )

    def NewMessage(self, type = HarnessMessage.MAIL_MESSAGE_TYPE):
        _log ("SMTP_Client.NewMessage()")
        message = self._client.NewMessage(type)
        return message

    def SendMessage(self, message):
        _log ("SMTP_Client.SendMessage()")
        return self._client.Send(message)

    def close(self):
        _log ("SMTP_Client.close()")
        self._client.close()

######################################################################################
# MMS Client Wrapper

class MMS_Client:
    def __init__(self, cfgname, type = 'EAIF'):
        _log ("MMS_Client.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        if type is None or type == "" :
            raise ValueError, "<type> value not specified for MMS_Client"
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for MMS_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to MMS_Client" % cfgname
        if cfg.get(cfgname, "URL") == None:
            raise ValueError, "URL not defined for cfgname \"%s\" supplied to MMS_Client" % cfgname
        self._url = cfg.get(cfgname, "URL")
        self._type = type
        self._client = MMSClient(self._type, self._url, testcase)

    def NewMessage(self):
        _log ("MMS_Client.NewMessage()")
        message = self._client.NewMessage()
        return message

    def SendMessage(self, message):
        _log ("MMS_Client.SendMessage()\n"+tostringMMS(message))
        return self._client.SendMessage(message)

    def close(self):
        _log ("MMS_Client.close()")
        self._client.close()

######################################################################################
# MM7 Client Wrapper

class MM7_Client:
    def __init__(self, cfgname):
        _log ("MM7_Client.__init__(cfgname=\"%s\")" % (type) )
        if type is None or type == "" :
            raise ValueError, "<type> value not specified for MM7_Client"
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for MM7_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to MM7_Client" % cfgname
        if cfg.get(cfgname, "URL") == None:
            raise ValueError, "URL not defined for cfgname \"%s\" supplied to MM7_Client" % cfgname
        self._url = cfg.get(cfgname, "URL")
        self._client = MM7Client(self._url, testcase)

    def newMessage(self):
        _log ("MM7_Client.newMessage()")
        message = self._client.newMessage()
        return message

    def deliverMessage(self, message):
        _log ("MM7_Client.DeliverMessage()\n" + message.toString())
        return self._client.deliverMessage(message)

    def submitMessage(self, message):
        _log ("MM7_Client.DeliverMessage()\n" + message.toString())
        return self._client.submitMessage(message)

    def close(self):
        _log ("MM7_Client.close()")
        self._client.close()

######################################################################################
# WebDav Wrapper
class WEBDAV_Client:
    def __init__(self, cfgname, user, password, domain = None, host_header_port = None, prefix = "files", local_ip = None):
        _log ("Client.__init__(cfgname=\"%s\")" % (cfgname) )
        self._protocol=cfg.get(cfgname,"protocol")
        self._host=cfg.get(cfgname,"host")
        self._port=int_convert(cfg.get(cfgname,"port"))
        self._secured = cfg.get(cfgname,"secured")
        self._local_ip = local_ip

        _log ("WebDAV_Client.__init _host=\"%s\", _port=\"%s\", _secured=\"%s\", _local_ip=\"%s\")" %  (self._host, self._port, self._secured, self._local_ip))

        if self._secured is None:
            self._secured = FALSE

        if domain is not None:
          self._host_header_domain = prefix + "." + domain
        else:
          self._host_header_domain = self._host

        if host_header_port is not None:
          self._host_header_port = host_header_port
        else:
          self._host_header_port = self._port

        _log ("WebDAV_Client.__init host_header_domain=\"%s\", _host_header_port=\"%s\", _secured=\"%s\")" %  (self._host_header_domain, self._host_header_port, self._secured))

        self._user=user
        self._password=password
        self._client=CPWebDavClient(testcase, self._protocol, self._host, self._port, self._user,
                                  self._password, self._host_header_domain, self._host_header_port, self._secured, self._local_ip)

    def setUserAgent(self, agent):
        self._client.setUserAgent(agent)

    def get(self, resourcePath, headers = None, authenticate = TRUE, quoteURL = TRUE):

        _log ("Client.get(resourcePath=\"%r\", headers=\"%s\" authenticate=\"%s\" quoteURL=\"%s\")" % (resourcePath, self.getDisplayHeaders(headers), authenticate, quoteURL) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.get(resourcePath, headers, authenticate, quoteURL)
        return result

    def head(self, resourcePath, headers = None, quoteURL = TRUE):
        _log ("Client.head(resourcePath=\"%r\", headers=\"%s\" quoteURL=\"%s\")" % (resourcePath, self.getDisplayHeaders(headers), quoteURL) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.head(resourcePath, headers, quoteURL)
        return result

    def getFile(self, resourcePath, fileLocation, quoteURL = TRUE):
        _log ("Client.getFile(resourcePath=\"%r\", fileLocation=\"%s\" quoteURL=\"%s\")" % (resourcePath, fileLocation, quoteURL) )
        return self._client.getFile(resourcePath, fileLocation, quoteURL)

    def put(self, fileLocation, resourcePath, chunked=FALSE, fileCharSet=None, ctype= None, headers = None):
        _log ("Client.put(fileLocation=\"%s\", resourcePath=\"%r\", fileCharSet=\"%s\", ctype=\"%s\", headers=\"%s\",  chunked=\"%s\")" % (fileLocation, resourcePath, fileCharSet, ctype, self.getDisplayHeaders(headers), chunked) )
        self._fileLocation = fileLocation
        self._resourcePath=resourcePath
        result = self._client.put(fileLocation, resourcePath, fileCharSet, ctype, headers, chunked)
        return result

    def putByString(self, resourcePath, ctype, body, headers = None, chunked=FALSE, authenticate = TRUE, quoteURL = TRUE):
        _log ("Client.putByString(resourcePath=\"%r\", ctype=\"%s\", headers=\"%s\", body=\"%s\", chunked=\"%s\" authenticate=\"%s\" quoteURL=\"%s\")" % (resourcePath, ctype, self.getDisplayHeaders(headers), self.getDisplayBody(body), chunked, authenticate, quoteURL) )
        result = self._client.putByString(resourcePath, ctype, headers, body, chunked, authenticate, quoteURL)
        return result

    def post(self, fileLocation, resourcePath, chunked=FALSE):
        self._fileLocation = fileLocation
        self._resourcePath=resourcePath
        result = self._client.post(fileLocation, resourcePath, chunked)
        return result

    def postByString(self, resourcePath, ctype, body, headers = None, chunked=FALSE, authenticate = TRUE, quoteURL = TRUE):
        _log ("Client.postByString(resourcePath=\"%r\", ctype=\"%s\", headers=\"%s\", body=\"%s\", chunked=\"%s\" authenticate=\"%s\" quoteURL=\"%s\")" % (resourcePath, ctype, self.getDisplayHeaders(headers), self.getDisplayBody(body), chunked, authenticate, quoteURL) )
        result = self._client.postByString(resourcePath, ctype, headers, body, chunked, authenticate, quoteURL)
        return result

    def delete(self, resourcePath, headers = None, authenticate = TRUE, quoteURL = TRUE):
        _log ("Client.delete(resourcePath=\"%r\", headers=\"%s\" authenticate=\"%s\" quoteURL=\"%s\")" % (resourcePath, self.getDisplayHeaders(headers), authenticate, quoteURL) )
        self._fileLocation = None
        self._resourcePath=resourcePath
        result = self._client.delete(resourcePath, headers, authenticate, quoteURL)
        return result

    def mkcol(self, resourcePath, quoteURL = TRUE):
        self._fileLocation = None
        self._resourcePath=resourcePath
        result = self._client.mkcol(resourcePath, quoteURL)
        return result

    def getStatusCode(self, response):
        result = self._client.getStatusCode(response)
        return result

    def getReasonPhrase(self, response):
     return self._client.getReasonPhrase(response)

    def move(self, srcURI, dstURI):
        self._srcURI = srcURI
        self._dstURI = dstURI
        result = self._client.move(srcURI, dstURI)
        return result

    def copy(self, srcURI, dstURI):
        self._srcURI = srcURI
        self._dstURI = dstURI
        result = self._client.copy(srcURI, dstURI)
        return result

    def proppatch(self, resourcePath, add_ns, add_names, add_values, del_ns, del_names, **newargs):
        result = self._client.proppatch(resourcePath, add_ns, add_names, add_values, del_ns, del_names)
        return result

    # This PROPFIND function was missing an argument for the Depth header.
    # Instead of adding a new argument and breaking existing tests,
    # we're using **keywords to extend the function. This function can now
    # be used as:
    #     client.propfind(path, ns, names)
    # OR
    #     client.propfind(path, ns, names, depth="infinity")
    #
    # For backwards compatibility with existing tests if a depth is not
    # specified a value of "0" is used.

    def propfind(self, resourcePath, name_spaces, property_names, **newargs):
        depth = "0"
        if newargs:
            keys = newargs.keys()
            if keys and keys[0].lower() == "depth":
                depth = newargs.values()[0]

        result = self._client.propfind(resourcePath, name_spaces, property_names, depth)
        return result

    def options(self, uri, quoteURL = TRUE):
        self._srcURI = uri
        result = self._client.options(uri, quoteURL)
        return result

    def extendedRequestByFile(self, method, uri, ctype, fname, headers = None, chunked = FALSE, quoteURL = TRUE):
        _log ("Client.extendedRequestByFile(method=\"%s\" uri=\"%r\" ctype=\"%s\" fname=\"%s\" headers=\"%s\" chunked=\"%s\" quoteURL=\"%s\")" % (method, uri, ctype, fname, self.getDisplayHeaders(headers), chunked, quoteURL) )
        result = self._client.extendedRequestByFile(method, uri, ctype, fname, headers, chunked, quoteURL)
        return result

    def extendedRequestByString(self, method, uri, ctype, body, headers = None, chunked = FALSE, authenticate = TRUE, quoteURL = TRUE):
        _log ("Client.extendedRequestByString(method=\"%s\" uri=\"%r\" ctype=\"%s\" headers=\"%s\" body=\"%s\" chunked=\"%s\" authenticate=\"%s\" quoteURL=\"%s\")" % (method, uri, ctype, self.getDisplayHeaders(headers), self.getDisplayBody(body), chunked, authenticate, quoteURL) )
        result = self._client.extendedRequestByString(method, uri, ctype, body, headers, authenticate, chunked, quoteURL)
        return result

    def getURL(self, fullUrl, headers = None, userName = None, pwd = None, authenticate = TRUE):
        _log ("Client.getURL(fullUrl\"%r\", headers=\"%s\", userName=\"%s\", pwd=\"%s\")" % (fullUrl, self.getDisplayHeaders(headers), userName, pwd) )
        result = self._client.getURL(fullUrl, headers, userName, pwd, authenticate)
        return result

    # Used for logging purpose only
    def getDisplayBody(self, body):
        if body is None:
            disp_body = "(Null)"
        elif len(body) > 20:
            disp_body = "[%0.20s...]" % repr(body)
        else :
            disp_body = "[%s]" % repr(body)

        return disp_body

    # Used for logging purpose only
    def getDisplayHeaders(self, headers):
        if headers is None:
            disp_headers = "(null)"
        elif len(headers) == 0:
            disp_headers = "[]"
        else:
            disp_headers = "["
            for i in range((len(headers)/2)):
                if i > 0:
                    disp_headers = disp_headers + ", "
                disp_headers = "%s%s=%s" % (disp_headers, headers[2*i], headers[1+(2*i)])
            if len(disp_headers) > 20:
                disp_headers = "[%0.20s...]" % repr(disp_headers)
            disp_headers = disp_headers + "]"

        return disp_headers
######################################################################################


######################################################################################
# CalDav Wrapper (can be used as an alternative to CSAPI_Client, which is not supported since CAL 9.2)
class CpCalDAV_Client:
    def __init__(self, cfgname, user, password, domain = None, host_header_port = None, local_ip = None):
        self._webdav = WEBDAV_Client(cfgname, user, password, domain, host_header_port, "files", local_ip)

    def getWebdavClient(self):
        return self._webdav

    def options(self, calendarId = None, resourceId = None, owner = None):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.options(resourcePath, quoteURL=FALSE)

    def get(self, calendarId, resourceId = None, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.get(resourcePath, headers, authenticate, quoteURL=FALSE)

    def head(self, calendarId, resourceId = None, owner = None, headers = None):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.head(resourcePath, headers, quoteURL=FALSE)

    def propfind(self, xmlBody, depth, calendarId = None, resourceId = None, owner = None, headers = None, 
            authenticate = TRUE):
        if (not headers):
            headers = []
        headers.append("Depth")
        headers.append("%s" % (depth))
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("PROPFIND", resourcePath, 'text/xml; charset="utf-8"', xmlBody, 
                headers, FALSE, authenticate, quoteURL=FALSE)

    def proppatch(self, xmlBody, calendarId = None, resourceId = None, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("PROPPATCH", resourcePath, 'text/xml; charset="utf-8"', xmlBody, 
                headers, FALSE, authenticate, quoteURL=FALSE)

    def report(self, xmlBody, calendarId = None, resourceId = None, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("REPORT", resourcePath, 'text/xml; charset="utf-8"', xmlBody, 
                headers, FALSE, authenticate, quoteURL=FALSE)

    def delete(self, calendarId, resourceId = None, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.delete(resourcePath, headers, authenticate, quoteURL=FALSE)

    def restore(self, calendarId, resourceId, owner = None, headers = None, authenticate = TRUE):
        if (not headers):
            headers = []
        headers.append("X-CP-Trash")
        headers.append("1")
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("MOVE", resourcePath, None, None, headers, FALSE, authenticate, 
                quoteURL=FALSE)

    def move(self, calendarId, resourceId, destinationUrl, owner = None, headers = None, authenticate = TRUE):
        if (not headers):
            headers = []
        headers.append("Destination")
        headers.append(destinationUrl)
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("MOVE", resourcePath, None, None, headers, FALSE, authenticate, 
                quoteURL=FALSE)

    def acl(self, xmlBody, calendarId, resourceId = None, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.extendedRequestByString("ACL", resourcePath, 'text/xml; charset="utf-8"', xmlBody, 
                headers, FALSE, authenticate, quoteURL=FALSE)

    def mkcalendar(self, calendarId, displayName = None, description = None, defaultTz = None, headers = None, 
            authenticate = TRUE):
        ctype = None
        body = None
        if (displayName or description or defaultTz):
            ctype = "text/xml";
            body = "<?xml version=\"1.0\" encoding=\"utf-8\" ?><C:mkcalendar xmlns:D=\"DAV:\" xmlns:C=\"urn:ietf:params:xml:ns:caldav\"><D:set><D:prop>";
            if (displayName):
                body = "%s<D:displayname>%s</D:displayname>" % (body, displayName)

            if (description):
                body = "%s<C:calendar-description xml:lang=\"en\">%s</C:calendar-description>" % (body, description)

            if (defaultTz):
                body = "%s<C:calendar-timezone><![CDATA[%s]]></C:calendar-timezone>" % (body, defaultTz)

            body = "%s</D:prop></D:set></C:mkcalendar>" % (body)

        resourcePath = self.getResourcePath(calendarId)
        return self._webdav.extendedRequestByString("MKCALENDAR", resourcePath, ctype, body, headers, FALSE, 
                authenticate, quoteURL=FALSE)

    def importIcal(self, calendarId, ical, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, None, owner)
        return self._webdav.postByString(resourcePath, 'text/calendar; charset="utf-8"', ical, headers, FALSE, 
                authenticate, quoteURL=FALSE)

    def put(self, calendarId, resourceId, ical, owner = None, headers = None, authenticate = TRUE):
        resourcePath = self.getResourcePath(calendarId, resourceId, owner)
        return self._webdav.putByString(resourcePath, 'text/calendar; charset="utf-8"', ical, headers, FALSE, 
                authenticate, quoteURL=FALSE)

    def putEvent(self, calendarId, summary, description, dtStart, dtEnd, tzid = None, tzIcal = None, location = None, 
            availability = None, attendees = None, rrule = None, exceptionDates = None, exceptionIds = None, 
            attachment = None, other = None, owner = None, headers = None, authenticate = TRUE):
        body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Openwave Messaging//Maia CpCalDAV Client//EN"

        # add timezone if one was specified
        tzidParam = ""
        if (tzIcal and tzid):
            tzidParam = ";TZID=%s" % (tzid)
            body = "%s\r\n%s" % (body, tzIcal)

        body = "%s\r\nBEGIN:VEVENT" % (body)

        # build the main body of the event
        uid = "event-%s-%s" % (getRandomInt(), getRandomInt())
        tstampNow = time.strftime("%Y%m%dT%H%M%SZ")
        commonBody = self._buildComponent(uid, summary, description, location, availability, attendees, rrule, 
                exceptionDates, exceptionIds, attachment)
        body = "%s\r\n%s" % (body, commonBody)

        body = "%s\r\nDTSTART%s:%s\r\nDTEND%s:%s" % (body, tzidParam, dtStart, tzidParam, dtEnd)

        if (other):
            body = "%s\r\n%s" % (body, other)

        body = "%s\r\nEND:VEVENT" % (body)

        # also add the optional exceptions to the recurrence
        if (rrule and exceptionIds and len(exceptionIds) > 0):
            index = 0
            for exceptionId in exceptionIds:
                index = index + 1
                exceptionEvent = "BEGIN:VEVENT\r\nUID:%s\r\nRECURRENCE-ID%s:%s\r\nSUMMARY:%s (Exception %s)\r\nDTSTAMP:%s\r\nDTSTART%s:%s\r\nDURATION:PT15M\r\nEND:VEVENT" % (uid,
                    tzidParam, exceptionId, summary, index, tstampNow, tzidParam, exceptionId)
                body = "%s\r\n%s" % (body, exceptionEvent)

        body = "%s\r\nEND:VCALENDAR" % (body)

        resourceId = "%s.ics" % (uid)
        response = self.put(calendarId, resourceId, body, owner, headers, authenticate)
        if (response and response.getStatusCode() >= 200 and response.getStatusCode() <= 299):
            return uid
        return None

    def putTodo(self, calendarId, summary, description, due, status, tzid = None, tzIcal = None, priority = None, 
            location = None, availability = None, attendees = None, rrule = None, exceptionDates = None, 
            exceptionIds = None, attachment = None, other = None, owner = None, headers = None, authenticate = TRUE):
        body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Openwave//Maia CpCalDAV Client//EN"

        # add timezone if one was specified
        tzidParam = ""
        if (tzIcal and tzid):
            tzidParam = ";TZID=%s" % (tzid)
            body = "%s\r\n%s" % (body, tzIcal)

        body = "%s\r\nBEGIN:VTODO" % (body)

        # build the main body of the event
        uid = "todo-%s-%s" % (getRandomInt(), getRandomInt())
        tstampNow = time.strftime("%Y%m%dT%H%M%SZ")
        commonBody = self._buildComponent(uid, summary, description, location, availability, attendees, rrule, 
                exceptionDates, exceptionIds, attachment)
        body = "%s\r\n%s" % (body, commonBody)

        body = "%s\r\nDUE%s:%s\r\nSTATUS:%s" % (body, tzidParam, due, status)

        if (priority):
            body = "%s\r\nPRIORITY:%s" % (body, priority)

        if (other):
            body = "%s\r\n%s" % (body, other)

        body = "%s\r\nEND:VTODO" % (body)

        # also add the optional exceptions to the recurrence
        if (rrule and exceptionIds and len(exceptionIds) > 0):
            index = 0
            for exceptionId in exceptionIds:
                index = index + 1
                exceptionEvent = "BEGIN:VTODO\r\nUID:%s\r\nRECURRENCE-ID%s:%s\r\nSUMMARY:%s (Exception %s)\r\nDTSTAMP:%s\r\nDUE:%s\r\nEND:VTODO" % (uid,
                    tzidParam, exceptionId, summary, index, tstampNow, exceptionId)
                body = "%s\r\n%s" % (body, exceptionEvent)

        body = "%s\r\nEND:VCALENDAR" % (body)

        resourceId = "%s.ics" % (uid)
        response = self.put(calendarId, resourceId, body, owner, headers, authenticate)
        if (response and response.getStatusCode() >= 200 and response.getStatusCode() <= 299):
            return uid
        return None

    def _buildComponent(self, uid, summary, description, location = None, availability = None, attendees = None, 
            rrule = None, exceptionDates = None, exceptionIds = None, attachment = None):
        # build the main body of the component
        tstampNow = time.strftime("%Y%m%dT%H%M%SZ")
        body = "UID:%s\r\nSUMMARY:%s\r\nDESCRIPTION:%s\r\nDTSTAMP:%s" % (uid, summary, description, tstampNow)

        # add any other optional fields
        if (location):
            body = "%s\r\nLOCATION:%s" % (body, location)

        if (availability and availability == "FREE"):
            body = "%s\r\nTRANSP:TRANSPARENT" % (body)
        elif (availability and availability == "BUSY"):
            body = "%s\r\nTRANSP:OPAQUE" % (body)

        if (attendees and len(attendees) > 0):
            organiser = self._webdav._user
            body = "%s\r\nORGANIZER;CN=%s:mailto:%s" % (body, organiser, organiser)
            for attendee in attendees:
                body = "%s\r\nATTENDEE;CN=%s;PARTSTAT=NEEDS-ACTION:mailto:%s" % (body, attendee, attendee)

        if (rrule):
            body = "%s\r\nRRULE:%s" % (body, rrule)
    
            if (exceptionDates and len(exceptionDates) > 0):
                for exceptionDate in exceptionDates:
                    body = "%s\r\nEXDATE:%s" % (body, exceptionDate)

        if (attachment):
            body = "%s\r\nATTACH:%s" % (body, attachment)

        return body

    def getResourcePath(self, calendarId, resourceId = None, owner = None):
        resourcePath = "/calendars"
        if (owner):
            owner = urllib.quote(owner, "")
            resourcePath = "%s/%s" % (resourcePath, owner)
        else:
            owner = urllib.quote(self._webdav._user, "")
            resourcePath = "%s/%s" % (resourcePath, owner)

        if (calendarId):
            calendarId = urllib.quote(calendarId, "")
            resourcePath = "%s/%s" % (resourcePath, calendarId)
            if (resourceId):
                resourceId = urllib.quote(resourceId, "")
                resourcePath = "%s/%s" % (resourcePath, resourceId)
            else:
                resourcePath = "%s/" % (resourcePath)
        else:
            resourcePath = "%s/" % (resourcePath)

        return resourcePath

######################################################################################


######################################################################################
# CardDav Wrapper
class CardDAV_Client:
    def __init__(self, cfgname, user, password, domain = None, host_header_port = None):
        _log ("Client.__init__(cfgname=\"%s\")" % (cfgname) )
        self._protocol=cfg.get(cfgname,"protocol")
        self._host=cfg.get(cfgname,"host")
        self._port=int_convert(cfg.get(cfgname,"port"))
        self._secured = cfg.get(cfgname,"secured")

        _log ("CardDAV_Client.__init _host=\"%s\", _port=\"%s\", _secured=\"%s\")" %  (self._host, self._port, self._secured))
        _log ("CardDAV_Client.__init _host=\"%s\", _user=\"%s\", _password=\"%s\")" %  (self._host, user, password))

        if self._secured is None:
            self._secured = FALSE

        self._host_header_domain = self._host

        if host_header_port is not None:
          self._host_header_port = host_header_port
        else:
          self._host_header_port = self._port

        _log ("CardDAV_Client.__init host_header_domain=\"%s\", _host_header_port=\"%s\", _secured=\"%s\")" %  (self._host_header_domain, self._host_header_port, self._secured))

        self._user=user
        self._password=password
        self._client=CPCardDAVClient(testcase, self._protocol, self._host, self._port, self._user,
                                  self._password, self._host_header_domain, self._host_header_port, self._secured)

    def doauth(self, auth):
    	self._fileLocation = None
    	self._client.set_default_auth(auth)

    def report(self, resourcePath, queryall = TRUE, limit = 0, body = None, headers = None):

        _log ("Client.report(resourcePath=\"%r\", headers=\"%s\" authenticate=\"%s\")" % (resourcePath, self.getDisplayHeaders(headers), true) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.report(resourcePath, queryall, limit, body, headers, FALSE)
        return result

    def delete(self, resourcePath):
        _log ("Client.delete(resourcePath=\"%r\")" % (resourcePath) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.delete(resourcePath)
        return result

    def put(self, resourcePath, body, headers = None, chunked = FALSE):
        _log ("Client.put(resourcePath=\"%r\", headers=\"%s\",  chunked=\"%s\")" % (resourcePath, self.getDisplayHeaders(headers), chunked) )
        return self._client.put(resourcePath, body, headers, chunked)

    def addAddressBook(self, resourcePath, noprops = TRUE, body = None, headers = None, chunked = FALSE):
        _log ("Client.mkcol(resourcePath=\"%r\")" % (resourcePath) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.mkcol(resourcePath, noprops, body, headers, chunked)
        return result

    def addContact(self, resourcePath):
        _log ("Client.addContact(resourcePath=\"%r\")" % (resourcePath) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.addContact (resourcePath)
        return result

    def getContact(self, resourcePath, href, headers):
        _log ("Client.updateContact(resourcePath=\"%r\")" % (resourcePath) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.getContact (resourcePath, href, headers, TRUE)
        return result

    def updateContact(self, resourcePath, updatestr, headers):
        _log ("Client.updateContact(resourcePath=\"%r\")" % (resourcePath) )

        self._fileLocation = None
        self._resourcePath = resourcePath
        result = self._client.updateContact (resourcePath, updatestr, headers)
        return result

    def getuid(self):
        result = self._client.get_last_uid()
        return result

    def getStatusCode(self, response):
        result = self._client.getStatusCode(response)
        return result

    def getReasonPhrase(self, response):
     return self._client.getReasonPhrase(response)

    def proppatch(self, resourcePath, xmlns_values, add_values, del_values, **newargs):
    	depth = "0"
        result = self._client.proppatch(resourcePath, xmlns_values, add_values, del_values, depth)
        return result

    def propfind(self, resourcePath, xmlns_values, property_names, depth, isprop = TRUE, **newargs):
        if newargs:
            keys = newargs.keys()
            if keys and keys[0].lower() == "depth":
                depth = newargs.values()[0]

        result = self._client.propfind(resourcePath, xmlns_values, property_names, depth, isprop)
        return result

    def options(self, uri):
        self._srcURI = uri
        result = self._client.options(uri)
        return result

    def putbyFile(self, resourcePath, fileLoc, headers = None, chunked = FALSE):
        _log ("Client.putbyFile(resourcePath=\"%r\", file location=\"%s\", headers=\"%s\",  chunked=\"%s\")" % (resourcePath, fileLoc, self.getDisplayHeaders(headers), chunked) )
        return self._client.putbyFile(resourcePath, body, headers, chunked)

    def reportbyFile(self, resourcePath, fileLoc, headers = None, chunked = FALSE):
        _log ("Client.reportbyFile(resourcePath=\"%r\", file location=\"%s\", headers=\"%s\",  chunked=\"%s\")" % (resourcePath, fileLoc, self.getDisplayHeaders(headers), chunked) )
        return self._client.reportbyFile(resourcePath, body, headers, chunked)

    def propfindbyFile(self, resourcePath, fileLoc, headers = None, chunked = FALSE):
        _log ("Client.propfindbyFile(resourcePath=\"%r\", file location=\"%s\", headers=\"%s\",  chunked=\"%s\")" % (resourcePath, fileLoc, self.getDisplayHeaders(headers), chunked) )
        return self._client.propfindbyFile(resourcePath, body, headers, chunked)

    # Used for logging purpose only
    def getDisplayBody(self, body):
        if body is None:
            disp_body = "(Null)"
        elif len(body) > 20:
            disp_body = "[%0.20s...]" % repr(body)
        else :
            disp_body = "[%s]" % repr(body)

        return disp_body

    # Used for logging purpose only
    def getDisplayHeaders(self, headers):
        if headers is None:
            disp_headers = "(null)"
        elif len(headers) == 0:
            disp_headers = "[]"
        else:
            disp_headers = "["
            for i in range((len(headers)/2)):
                if i > 0:
                    disp_headers = disp_headers + ", "
                disp_headers = "%s%s=%s" % (disp_headers, headers[2*i], headers[1+(2*i)])
            if len(disp_headers) > 20:
                disp_headers = "[%0.20s...]" % repr(disp_headers)
            disp_headers = disp_headers + "]"

        return disp_headers

##############################################################################################
class ATOM_Client:
        def __init__(self, cfgname, user, domain, password, host_header_domain = None, host_header_port = None):
            _log ("Client.__init__(cfgname=\"%s\", user=\"%s\", domain=\"%s\", password=\"%s\")" % (cfgname, user, domain, password) )
            self._host = cfg.get(cfgname, "host")
            self._port = int_convert(cfg.get(cfgname, "port"))
            self._path = cfg.get(cfgname, "path")
            self._xml_ns = cfg.get(cfgname, "ns")
            self._xml_ns_sep = cfg.get(cfgname, "nssep")

            self._user = user
            self._domain = domain
            self._password = password

            if host_header_domain is None:
                self._host_header_domain = self._host
            else:
                self._host_header_domain = host_header_domain

            if host_header_port is None:
                self._host_header_port = self._port
            else:
                self._host_header_port = host_header_port

            _log ("Client.__init__(host=\"%s\", port=%d, user=\"%s\", domain=\"%s\", password=\"%s\")" % (self._host, self._port, self._user, self._domain, self._password) )

            self._client = UMCAtomClient(testcase, self._host, self._port, self._path, self._user, self._domain, self._password, self._host_header_domain, self._host_header_port, self._xml_ns, self._xml_ns_sep)

        def getStatusCode(self, response):
            return self._client.getStatusCode(response)

        def get(self, resourcePath, query = None, headers = None):
            # headers are an array of strings, where each string is of the form <header>: <value>
            _log ("ATOMClient.get(%s, %s, %s)" % (resourcePath, query, headers))
            result = self._client.get(resourcePath, query, headers)
            return result

        def delete(self, resourcePath, query = None, headers = None):
            # headers are an array of strings, where each string is of the form <header>: <value>
            _log ("ATOMClient.delete(%s, %s, %s)" % (resourcePath, query, headers))
            result = self._client.delete(resourcePath, query, headers)
            return result

        def post(self, resourcePath, query = None, headers = None, cmd = None):
            # headers are an array of strings, where each string is of the form <header>: <value>
            _log ("ATOMClient.post(%s, %s, %s, %s)" % (resourcePath, query, headers, cmd))
            result = self._client.post_command(resourcePath, query, headers, cmd)
            return result

        def put(self, resourcePath, query = None, headers = None, cmd = None):
            # headers are an array of strings, where each string is of the form <header>: <value>
            _log ("ATOMClient.put(%s, %s, %s, %s)" % (resourcePath, query, headers, cmd))
            result = self._client.put_command(resourcePath, query, headers, cmd)
            return result

        def send_message(self, resourcePath, query, message, headers = None, mtype = 0, msubtype = 0):
            # headers is an array of strings, where each string is of the form <header>: <value>
            _log ("ATOMClient.sendMessage(%s, %s, %s, %s, '%d', '%d')" % (resourcePath, query, headers, message, mtype, msubtype))
            result = self._client.sendMessage(resourcePath, query, headers, message, mtype, msubtype)
            return result

######################################################################################
# Canned Message Client Wrapper

class JyCannedMsgClient:
    def __init__(self, cfgname, type = 'EAIF'):
        _log ("JyCannedMsgClient.__init__(cfgname=\"%s\", type=\"%s\")" % (cfgname,type) )
        if type is None or type == "" :
            raise ValueError, "<type> value not specified for JyCannedMsgClient"
        self._type = type
        if cfgname is None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for JyCannedMsgClient"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to JyCannedMsgClient" % cfgname
        if type == 'EAIF' or type == 'MM7':
            if cfg.get(cfgname, "URL") == None:
                raise ValueError, "URL not defined for cfgname \"%s\" supplied to JyCannedMsgClient" % cfgname
            self._url = cfg.get(cfgname, "URL")
            self._client = CannedMsgClient(self._type, self._url, testcase)
        elif type == 'SMTP':
            if cfg.get(cfgname, "host") == None:
                raise ValueError, "host not defined for cfgname \"%s\" supplied to JyCannedMsgClient" % cfgname
            self._host = cfg.get(cfgname, "host")
            if cfg.get(cfgname, "port") == None:
                raise ValueError, "Port not defined for cfgname \"%s\" supplied to JyCannedMsgClient" % cfgname
            self._port = int_convert(cfg.get(cfgname, "port"))
            self._client = CannedMsgClient(self._type, self._host, self._port, testcase)
        else:
            raise ValueError, "Unknown type \"%s\" supplied to JyCannedMsgClient" % type


    def SendMessage(self, filename, sndr=None, to=None, prevSender=None, uagent=None, wapprofile=None):
        _log ("JyCannedMsgClient.SendMessage()")
        return self._client.Send(filename, sndr, to, prevSender, uagent, wapprofile)


    def close(self):
        _log ("JyCannedMsgClient.close()")
        self._client.close()

######################################################################################
# Util Wrapper

def base64Decode(data):
    return Util.base64Decode(data)

def base64Encode(data):
    return Util.base64Encode(data)

def sha1Hash(data):
    return Util.sha1Hash(data)

######################################################################################
# XMLHttpClient Wrapper

class XMLHttp_Client:
    def __init__(self, cfgname):
        _log ("XMLHttp_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._protocol = cfg.get(cfgname, "protocol")
        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._client = XMLHttpClient(testcase, self._protocol, self._host, self._port)

    def authenticate(self, command, query, userName, domain, password):
        _log ("XMLHttp_Client.authenticate(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\")" % (command, query, userName, domain))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._password = password
        return self._client.authenticate(self._command, self._query, self._userName, self._domain, self._password)

    def get(self, command, query, userName, domain, authCredentials, bAlreadyEncoded = 0, retStatusCode = 0):
        if query is not None:
            print_query = query.encode("ascii", "replace")
        else:
            print_query = query
        _log ("XMLHttp_Client.get(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\", bAlreadyEncoded=\"%d\" , retStatusCode=\"%d\")" % (command, print_query, userName, domain, bAlreadyEncoded, retStatusCode))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        self._bAlreadyEncoded = bAlreadyEncoded
        self._retStatusCode = retStatusCode
        return self._client.get(self._command, self._query, self._userName, self._domain, self._authCredentials, self._bAlreadyEncoded,  self._retStatusCode )

    def getUrl(self, url, userAgent = None):
        _log ("XMLHttp_Client.getUrl(url=\"%s\", uAgent=\"%s\")" % (url, userAgent))
        return self._client.getUrl(url, userAgent)

######################################################################################
# PSXMLHttpClient Wrapper

class PSXMLHttp_Client:
    def __init__(self, cfgname):
        _log ("PSXMLHttp_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._protocol = cfg.get(cfgname, "protocol")
        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._client = PSXMLHttpClient(testcase, self._protocol, self._host, self._port)

    def authenticate(self, command, query, userName, domain, password):
        _log ("PSXMLHttp_Client.authenticate(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\")" % (command, query, userName, domain))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._password = password
        return self._client.authenticate(self._command, self._query, self._userName, self._domain, self._password)


    def get(self, command, query, userName, domain, authCredentials, bAlreadyEncoded = 0, retStatusCode = 0):
        if query is not None:
            print_query = query.encode("ascii", "replace")
        else:
            print_query = query
        _log ("PSXMLHttp_Client.get(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\", bAlreadyEncoded=\"%d\" , retStatusCode=\"%d\")" % (command, print_query, userName, domain, bAlreadyEncoded, retStatusCode))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        self._bAlreadyEncoded = bAlreadyEncoded
        self._retStatusCode = retStatusCode
        return self._client.get(self._command, self._query, self._userName, self._domain, self._authCredentials, self._bAlreadyEncoded, self._retStatusCode )

    def getFile(self, url):
        self._url = url
        return self._client.getFile(self._url)

    def getUrl(self, url, userAgent = None):
        _log ("XMLHttp_Client.getUrl(url=\"%s\", uAgent=\"%s\")" % (url, userAgent))
        return self._client.getUrl(url, userAgent)

    def getApplinkFile(self, url, dhid, params, userName, domain, authCredentials):
        log ("PSXMLHttp_Client.getApplinkFile(url=\"%s\", dhid=\"%s\", user=\"%s\", domain=\"%s\")" % (url, dhid, userName, domain))
        self._url = url
        self._dhid = dhid
        self._params = params
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.getApplinkFile(self._url, self._dhid, self._params, self._userName, self._domain, self._authCredentials)

    def postApplinkFile(self, command, command_data, query, fileQuery, userName, domain, authCredentials, retStatusCode = 0):
        log ("PSXMLHttp_Client.postApplinkFile(command=\"%s\", command_data=\"%s\", user=\"%s\", domain=\"%s\", retStatusCode=\"%d\")" % (command, command_data, userName, domain, retStatusCode))
        self._command = command
        self._command_data = command_data
        self._query = query
        self._fileQuery = fileQuery
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        self._retStatusCode = retStatusCode
        return self._client.postApplinkFile(self._command, self._command_data, self._query, self._fileQuery, self._userName, self._domain, self._authCredentials, self._retStatusCode )

    def post(self, command, query, qparams, userName, domain, authCredentials):
        log ("PSXMLHttp_Client.post(command=\"%s\", query=\"%s\" user=\"%s\", domain=\"%s\")" %
            (command, query, userName, domain))
        self._command = command
        self._query = query
        self._qparams = qparams
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.post(self._command, self._query, self._qparams, self._userName, self._domain, self._authCredentials)

    def postApplinkFileGetString(self, command, query, qparams, userName, domain, authCredentials):
        log ("PSXMLHttp_Client.postApplinkFileGetString(command=\"%s\", query=\"%s\" user=\"%s\", domain=\"%s\")" %
            (command, query, userName, domain))
        self._command = command
        self._query = query
        self._qparams = qparams
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.postApplinkFileGetString(self._command, self._query, self._qparams, self._userName, self._domain, self._authCredentials)

    def getPSPABVersion(self):
        ver = getGlobal("ps_version", None)
        if ver is None:
            self._systemInfoPath = "/cp/ps/Main/system/Info"
            self._component = "PAB"
            self._prefix = "PAB-UI-"
            return self._client.getComponentVersion(self._systemInfoPath, self._component, self._prefix)
        else:
            return ver;

    def getPSMAILVersion(self):
            self._systemInfoPath = "/cp/ps/Main/system/Info"
            self._component = "Mail"
            self._prefix = "MS-UI-"
            version = self._client.getComponentVersion(self._systemInfoPath, self._component, self._prefix)
            if version == "8_0_999":
                version = "8.0.999"
            return version

    def getTimeTaken(self):
        timeTaken = self._client.getTimeTaken()
        return timeTaken


######################################################################################
# JSONHttpClient Wrapper

class JSONHttp_Client:
    def __init__(self, cfgname):
        _log ("JSONHttp_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._protocol = cfg.get(cfgname, "protocol")
        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._client = JSONHttpClient(testcase, self._protocol, self._host, self._port)

    def authenticate(self, command, query, userName, domain, password):
        _log ("JSONHttp_Client.authenticate(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\")" % (command, query, userName, domain))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._password = password
        return self._client.authenticate(self._command, self._query, self._userName, self._domain, self._password)

    def get(self, command, query, userName, domain, authCredentials, bAlreadyEncoded = 0, retStatusCode = 0):
        if query is not None:
            print_query = query.encode("ascii", "replace")
        else:
            print_query = query
        _log ("JSONHttp_Client.get(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\", bAlreadyEncoded=\"%d\" , retStatusCode=\"%d\")" % (command, print_query, userName, domain, bAlreadyEncoded, retStatusCode))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        self._bAlreadyEncoded = bAlreadyEncoded
        self._retStatusCode = retStatusCode
        return self._client.get(self._command, self._query, self._userName, self._domain, self._authCredentials, self._bAlreadyEncoded, self._retStatusCode)

    def getApplinkFile(self, url, dhid, params, userName, domain, authCredentials):
        _log ("JSONHttp_Client.getApplinkFile(url=\"%s\", dhid=\"%s\", user=\"%s\", domain=\"%s\")" % (url, dhid, userName, domain))
        self._url = url
        self._dhid = dhid
        self._params = params
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.getApplinkFile(self._url, self._dhid, self._params, self._userName, self._domain, self._authCredentials)

    def postApplinkFile(self, command, command_data, query, fileQuery, userName, domain, authCredentials, retStatusCode = 0):
        _log ("JSONHttp_Client.postApplinkFile(command=\"%s\", command_data=\"%s\", user=\"%s\", domain=\"%s\", retStatusCode=\"%d\")" % (command, command_data, userName, domain, retStatusCode))
        self._command = command
        self._command_data = command_data
        self._query = query
        self._fileQuery = fileQuery
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        self._retStatusCode = retStatusCode
        return self._client.postApplinkFile(self._command, self._command_data, self._query, self._fileQuery, self._userName, self._domain, self._authCredentials, self._retStatusCode)

    def postApplinkFileGetString(self, command, query, qparams, userName, domain, authCredentials):
        _log ("JSONHttp_Client.postApplinkFileGetString(command=\"%s\", query=\"%s\" user=\"%s\", domain=\"%s\")" %
            (command, query, userName, domain))
        self._command = command
        self._query = query
        self._qparams = qparams
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.postApplinkFileGetString(self._command, self._query, self._qparams, self._userName, self._domain, self._authCredentials)

    def post(self, command, query, qparams, userName, domain, authCredentials):
        _log ("JSONHttp_Client.post(command=\"%s\", query=\"%s\" user=\"%s\", domain=\"%s\")" % (command, query, userName, domain))
        self._command = command
        self._query = query
        self._qparams = qparams
        self._userName = userName
        self._domain = domain
        self._authCredentials = authCredentials
        return self._client.post(self._command, self._query, self._qparams, self._userName, self._domain, self._authCredentials)

    def jsonrpc2(self, payload):
        _log ("JSONHttp_Client.jsonrpc2(payload=\"%s\")" % (payload))
        return self._client.postJsonRpc(payload)

######################################################################################
# HTMLHttpClient Wrapper

class HTMLHttp_Client:
    def __init__(self, cfgname):
        _log ("HTMLHttp_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._protocol = cfg.get(cfgname, "protocol")
        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._client = HTMLHttpClient(testcase, self._protocol, self._host, self._port)


    def checkAuthorization(self, command, query, userName, domain):
        http403Message = "HTTP Status 403 - "

        if query is not None:
            print_query = query.encode("ascii", "replace")
        else:
            print_query = query
        _log ("HTMLHttp_Client.get(command=\"%s\", query=\"%s\", user=\"%s\", domain=\"%s\")" % (command, print_query, userName, domain))
        self._command = command
        self._query = query
        self._userName = userName
        self._domain = domain
        htmldom  = self._client.get(self._command, self._query, self._userName, self._domain, None, 0)
        h1List = htmldom.getElementsByTagName("h1")
        if h1List.getLength() > 0:
            h1 = h1List.item(0)
            testMatchString(http403Message,h1.getFirstChild().getNodeValue(), "checkAuthorization: Test the correct HTTP error message %s is returned" % http403Message)
        else:
            testSetResultFail(details = "checkAuthorization failed" )

######################################################################################
# JMXRMIClient Wrapper

class JMXRMI_Client:
    def __init__(self, cfgname):
        _log ("JMXRMI_Client.__init__(cfgname=\"%s\")" % (cfgname))
        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._path = cfg.get(cfgname, "path")
        self._userName = cfg.get(cfgname, "userName")
        self._password = cfg.get(cfgname, "password")
        self._client = JMXRMIClient(testcase, self._host, self._port, self._path, self._userName, self._password)

    def addNotificationListener(self, name):
        _log ("JMXRMI_Client.addNotificationListener(name=\"%s\")" % (name))
        self._name = name
        self._client.addNotificationListener(self._name)

    def clearNotifications(self):
        _log ("JMXRMI_Client.clearNotifications()")
        self._client.clearNotifications()

    def close(self):
        _log ("JMXRMI_Client.close()")
        self._client.close()

    def getAttribute(self, name, attrName):
        _log ("JMXRMI_Client.getAttribute(name=\"%s\", attrName=\"%s\")" % (name, attrName))
        self._name = name
        self._attrName = attrName
        return self._client.getAttribute(self._name, self._attrName)

    def getNotifications(self):
        _log ("JMXRMI_Client.getNotifications()")
        return self._client.getNotifications()

    def hasNotifications(self):
        _log ("JMXRMI_Client.hasNotifications()")
        return self._client.hasNotifications()

    def invoke(self, name, operationName, params, signature):
        _log ("JMXRMI_Client.invoke(name=\"%s\", operationName=\"%s\", params=\"%s\", signature=\"%s\")" % (name, operationName, params, signature))
        self._name = name
        self._operationName = operationName
        self._params = params
        self._signature = signature
        return self._client.invoke(self._name, self._operationName, self._params, self._signature)

    def setAttribute(self, name, attrName, attrValue):
        _log ("JMXRMI_Client.setAttribute(name=\"%s\", attrName=\"%s\", attrValue=\"%s\")" % (name, attrName, attrValue))
        self._name = name
        self._attrName = attrName
        self._attrValue = attrValue
        return self._client.setAttribute(self._name, self._attrName, self._attrValue)


#######################################################################################
#Java Couchbase wrapper

class Couchbase_Client:
    def __init__(self):
        _log ("Couchbase_Client.__init__()")
        self._client = CouchbaseClient(testcase)

    def connect(self, hosts, userName, password):
        _log("Couchbase_Client.connect(hosts=\"%s\", userName=\"%s\", password=\"%s\")" % (hosts, userName, password))
        self._hosts = hosts
        self._userName = userName
        self._password = password
        self._client.connect(self._hosts, self._userName, self._password)

    def set(self, key, expiry, value):
        _log ("Couchbase_Client.set(key=\"%s\", expiry=\"%s\", value=\"%s\")" % (key, expiry, value))
        self._key = key
        self._expiry = expiry
        self._value = value
        self._client.set(self._key, self._expiry, self._value)

    def get(self, key):
        _log ("Couchbase_Client.get(key=\"%s\")" % (key))
        self._key = key
        return self._client.get(self._key)

    def getAndWait(self, key):
        _log ("Couchbase_Client.getAndWait(key=\"%s\")" % (key))
        self._key = key
        return self._client.getAndWait(self._key)

    def shutdown(self, timeout = 0):
        _log("Couchbase_Client.shutdown(timeout=\"%s\")" % (timeout))
        self._timeout = timeout
        self._client.shutdown(self._timeout)

    def append(self, key, value):
        _log("Couchbase_Client.append(key=\"%s\", value=\"%s\")" % (key, value))
        self._key = key
        self._value = value
        self._client.append(self.key, self._value)

    def delete(self, key):
        _log("Couchbase_Client.delete(key=\"%s\")" % (key))
        self._key = key
        self._client.delete(self._key)


#######################################################################################
# create a subclass of the Java class to allow easy setting of attributes
# in other words:
# you can do "msg.to = 'email@addr.ess'" and it will automatically call the
# java method msg.setTo("email@addr.ess")
#
# Makes the script language much simpler
class JyHarnessMessage(HarnessMessage):
    pass

class Telnet_Client:
    def __init__(self, cfgname, timeout = 30 ):

        if cfgname == None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for MGR_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to MGR_Client" % cfgname

        _log ("MGR_Client.__init__(cfgname=\"%s\")" % (cfgname) )

        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._password = cfg.get(cfgname, "password")
        self._timeout = timeout*1000
        try:
            self._client = ManagementClient(testcase, self._host, self._port, self._timeout)
        except java.net.ConnectException:
            raise ValueError, "MGR_Client (cfgname=%s) cannot connect to [%s port:%u]" % (cfgname, self._host, self._port)

    def send(self, cmd):
        #print 'Telnet_Client.send() cmd=',cmd
        _log ("Telnet_Client.send(cmd=\"%s\")" % (cmd) )
        self._client.sendData(cmd)

    def receive(self):
        #print 'Telnet_Client.receive()'
        _log ("Telnet_Client.receive()")
        result = self._client.readData()
        return result

    def close(self):
        self._client.close()

class MGR_Client:
    def __init__(self, cfgname, timeout = 30, server = None):

        if cfgname == None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for MGR_Client"
        if cfg.get(cfgname) == None:
                raise ValueError, "Unknown cfgname \"%s\" supplied to MGR_Client" % cfgname

        _log ("MGR_Client.__init__(cfgname=\"%s\") (timeout=%d) (server=%s)" % (cfgname, timeout, server) )

        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._userName = cfg.get(cfgname, "userName")
        self._password = cfg.get(cfgname, "password")
        self._timeout = timeout*1000
        self._server = server
        try:
            self._client = ManagementClient(testcase, self._host, self._port, self._timeout, self._server)
        except java.net.ConnectException, e:
            log("MGR_Client ConnectException: %s" % str(e))
            raise ValueError, "MGR_Client (cfgname=%s) cannot connect to [%s port:%u] [Server:%s]\n%s" % (cfgname, self._host, self._port, self._server, str(e))
        self._client.login(self._userName, self._password)

    def send(self, cmd):
        #print 'MGR_Client.send() cmd=',cmd
        _log ("MGR_Client.send(cmd=\"%s\")" % (cmd) )
        result = self._client.request(cmd)
        return result

    def checked_send(self, cmd):
        _log ("MGR_Client.checked_send(cmd=\"%s\")" % (cmd) )
        result = self.send(cmd)
        if result is None:
            raise ValueError, "MGR_Client.checked_send() Failed to get response to command: \"%s\"" % (cmd)
        res = result.toString()
        if res.startswith("OK"):
            return result
        else:
            raise ValueError, "MGR_Client.checked_send() Error\n\t%s\n\t%s" % (cmd,result)

    def send_extended(self, cmd, extended_cmd):
        _log ("MGR_Client.send_extended(cmd=\"%s\", extended_cmd=\"%s\")" % (cmd, extended_cmd) )
        # make sure carriage returns are of form \r\n
        if extended_cmd.find("\n") != -1:
            if extended_cmd.find("\r") == -1:
                extended_cmd = extended_cmd.replace("\n","\r\n")
        result = self._client.request(cmd, extended_cmd)
        return result

    def checked_send_extended(self, cmd, extended_cmd):
        _log ("MGR_Client.checked_send_extended(cmd=\"%s\", extended_cmd=\"%s\")" % (cmd, extended_cmd) )
        result = self.send_extended(cmd,extended_cmd)
        if result is None:
            raise ValueError, "MGR_Client.checked_send_extended() Failed to get response to command: \"%s\"" % (cmd)
        res = result.toString()
        # skip any stuff like "* FORMAT 'text'" on first line if SIG command
        while res.startswith("*"):
            indx = res.find("\n")
            if indx != -1:
                res = result[indx+1:]
            else:
                break
        if res.startswith("OK"):
            return result
        else:
            raise ValueError, "MGR_Client.checked_send_extended() Error\n\t%s\n\t%s" % (cmd,result)

    def send_get_extended(self, cmd):
        _log ("MGR_Client.send_get_extended(cmd=\"%s\")" % (cmd) )
        result = self._client.request(self._client.NONE, 1, cmd)
        return result

    def close(self):
        _log ("MGR_Client.close()")
        self.send("QUIT")
        self._client.close()

    # return value from a string of format " * Debug VALUE 2"
    # or " * BillableMsgs STRING 'INEMAIL/MSG'"
    # useful for parsing telnet management protocol responses
    # Can pull a value from a list
    def getValue(self, cmd, var=None):
        _log ("getValue(cmd=\"%s\", var=\"%s\")" % (cmd, var) )
        result = self.send(cmd)
        if result is None:
            return ""
        result = result.toString()
        if result.startswith("ERROR"):
            return ""
        lines = result.splitlines()
        for ln in lines:
            # if we have been provided with a variable name
            if var is not None:
                indx = ifind(ln, var)
                if indx == -1:
                    continue
                else:
                    ln = ln[indx:]
            # convert to lowercase
            ln_uprcase = ln.upper()
            indx = ln_uprcase.find(" VALUE")
            if indx != -1:
                indx += 7  # len(" VALUE ")
                return ln[indx:]
            else:
                indx = ln_uprcase.find(" STRING")
                if indx == -1:
                    if len(ln) > 2 and ln[0] == '*' :
                        indx = 2
                    else:
                        print 'MGR_Client.getValue() cannot parse response',ln
                        return ""
                else:
                    indx += 8  # len(" STRING ")
                ln = ln[indx:]
                if ln.startswith("'"):
                    ln = ln[1:]
                    indx = ln.rfind("'")
                    ln = ln[:indx]
                return ln
        # end for
        return ""



    # return the command result in a list of string (excluding final OK or error)
    # this function doesn't expect any format, and simply removes the '* ' at
    # the begininning of each line
    # If checkError is TRUE, returns None rather than an empty list on error,
    # allowing client to make the difference between no result or error
    # Note checkError default value is FALSE, and not TRUE, for backward compatiblity reason..
    def getListString(self, cmd, checkError = FALSE):
        _log ("getListString(cmd=\"%s\")" % (cmd) )
        result = self.send(cmd)
        l = []
        if result is None:
            if checkError:
                return None
            return l

        result = result.toString()
        if result.startswith("ERROR"):
            if checkError:
                return None
            return l
        lines = result.splitlines()
        for ln in lines:
            # if we have been provided with a variable name
            indx = ln.find("* ")
            if indx != -1:
                l.append(ln[2:])
        # end for
        return l

    # return value from an extended string
    # just skips the "OK\n" at the start and strips "." from end
    # so you can easily restore this value afterwards

    def getExtendedValue(self, cmd):
        _log ("getExtendedValue(cmd=\"%s\")" % (cmd) )
        result = self.send_get_extended(cmd)
        if result is None:
            return ""
        result = result.toString()
        # skip any stuff like "* FORMAT 'text'" on first line if SIG command
        while result.startswith("*"):
            indx = result.find("\n")
            if indx != -1:
                result = result[indx+1:]
            else:
                break
        if result.startswith("ERROR"):
            return ""
        if result.startswith("OK\n"):
            result = result[3:]
        else:
            return result
        # remove . from end
        if result.endswith(".\n"):
            indx = result.rfind(".\n")
            result = result[:indx]
        return result

    # return boolean indicating if extended response was OK
    def isExtendedValueOK(self, cmd, extended_cmd=None):
        _log ("isExtendedValueOK(cmd=\"%s\", extended_cmd=\"%s\")" % (cmd, extended_cmd) )
        if extended_cmd == None or extended_cmd == "" :
            result = self.send_get_extended(cmd)
        else:
            result = self.send_extended(cmd,extended_cmd)
        if result is None:
            return FALSE
        result = result.toString()
        # skip any stuff like "* FORMAT 'text'" on first line if SIG command
        while result.startswith("*"):
            indx = result.find("\n")
            if indx != -1:
                result = result[indx+1:]
            else:
                break
        if result.startswith("OK"):
            return TRUE
        else:
            return FALSE

    def getCounterValue(self, cmd):
        _log ("getCounterValue(cmd=\"%s\")" % (cmd) )
        result = self.send(cmd)
        if result is None:
            return ""
        result = result.toString()
        if result.startswith("ERROR"):
            return ""
        lines = result.splitlines()
        for ln in lines:
            if ln.startswith("*"):
                indx = ln.find(" ")
                value = ln[2:12]
                return value
        return ""

    def getCounterNValue(self, cmd, count):
        _log ("getCounterNValue(cmd=\"%s\" count \"%d\")" % (cmd, count) )
        result = self.send(cmd)
        if result is None:
            return ""
        result = result.toString()
        if result.startswith("ERROR"):
            return ""
        lines = result.splitlines()
        cnt = 0
        for ln in lines:
            cnt += 1
            if cnt == count:
                if ln.startswith("*"):
                   value = ln[2:12]
                   indx = value.rfind(" ")
                   _log ("return value \"%s\"" % (value[indx+1:]))
                   return value[indx+1:]
        return ""

class IFSMGR_Client(MGR_Client):
    def __init__(self, cfgname, timeout = 30):
        MGR_Client.__init__(self, cfgname, timeout, "IFS")

class MOS_Client:
    def __init__(self, cfgname, timeout = 30):

        cfgname = "MOS"
        if cfgname == None or cfgname == "" :
            raise ValueError, "<cfgname> value not specified for MOS_Client"
        if cfg.get(cfgname) == None:
            raise ValueError, "Unknown cfgname \"%s\" supplied to MOS_Client" % cfgname

        _log ("MOS_Client.__init__(cfgname=\"%s\") (timeout=%d)" % (cfgname, timeout) )

        self._host = cfg.get(cfgname, "host")
        self._port = int_convert(cfg.get(cfgname, "port"))
        self._timeout = timeout*1000
        self._client = MOSClient(testcase, self._host, self._port, self._timeout)

    def send(self, cmd):
        _log ("MOS_Client.send(cmd=\"%s\")" % (cmd) )
        return self._client.send(cmd)

    def checked_send(self, cmd):
        _log ("MOS_Client.checked_send(cmd=\"%s\")" % (cmd) )
        result = self.send(cmd)
        if result is None:
            raise ValueError, "MOS_Client.checked_send() Failed to get response to command: \"%s\"" % (cmd)
        res = result.toString()
        if res.startswith("OK"):
            return result
        else:
            raise ValueError, "MOS_Client.checked_send() Error\n\t%s\n\t%s" % (cmd,result)

    # return the command result in a list of string (excluding final OK or error)
    # this function doesn't expect any format, and simply removes the '* ' at
    # the begininning of each line
    # If checkError is TRUE, returns None rather than an empty list on error,
    # allowing client to make the difference between no result or error
    # Note checkError default value is FALSE, and not TRUE, for backward compatiblity reason..
    def getListString(self, cmd, checkError = FALSE):
        _log ("getListString(cmd=\"%s\")" % (cmd) )
        result = self.send(cmd)
        l = []
        if result is None:
            if checkError:
                return None
            return l

        result = result.toString()
        if result.startswith("ERROR"):
            if checkError:
                return None
            return l
        lines = result.splitlines()
        for ln in lines:
            # if we have been provided with a variable name
            indx = ln.find("* ")
            if indx != -1:
                l.append(ln[2:])
        # end for
        return l

    def close(self):
        _log ("MOS_Client.close()")
        pass

class FSMGR_Client:
    def __init__(self, cfgname, timeout = 120):
        if inMOSMode():
            self._client = MOS_Client(cfgname, timeout)
        else:
            self._client = MGR_Client(cfgname, timeout, "FS")

    def send(self, cmd):
        return self._client.send(cmd)

    def checked_send(self, cmd):
        return self._client.checked_send(cmd)

    def getListString(self, cmd, checkError = FALSE):
        return self._client.getListString(cmd, checkError)

    def close(self):
        self._client.close()

# UPS library
class UPS_Client_MEMOVA:
    def __init__(self, cfgname = None, props = None, mappingFile = None, url = None, user = None, password = None):
        _log ("UPS_Client_MEMOVA.__init__(cfgname=\"%s\")" % (cfgname))
        if cfgname is None:
            self._locURL = url
            self._locUser = user
            self._locPass = password
        else:
            self._locURL = cfg.get(cfgname, "locURL")
            self._locUser = cfg.get(cfgname, "locUser")
            self._locPass = cfg.get(cfgname, "locPass")

        _log ("UPS_Client_MEMOVA.__init__(_locURL=\"%s\")" % (self._locURL))
        _log ("UPS_Client_MEMOVA.__init__(_locUser=\"%s\")" % (self._locUser))
        _log ("UPS_Client_MEMOVA.__init__(_locPass=\"%s\")" % (self._locPass))
        self._props = props
        self._mappingFile = mappingFile
        self._client = UPSClient(testcase, self._locURL, self._locUser, self._locPass, self._props, self._mappingFile)

    def getUPSIntf(self):
        _log ("UPS_Client_MEMOVA.getUPSIntf()")
        return self._client.getUPSIntf()

    def readUser(self, userName, domain, rollup = TRUE, rollupServices = None):
        _log ("UPS_Client_MEMOVA.readUser(user=\"%s@%s\", rollup=%d)" % (userName, domain, rollup))
        self._userName = userName
        self._domain = domain
        self._rollup = rollup
        self._rollupServices = rollupServices
        return self._client.readUser(self._userName, self._domain, self._rollup, self._rollupServices)

    def readDomain(self, domain):
        _log ("UPS_Client_MEMOVA.readDomain(domain=\"%s\")" % (domain))
        self._domain = domain
        return self._client.readDomain(self._domain)

    def getAttributeValue(self, entry, attr):
        _log ("UPS_Client_MEMOVA.getAttributeValue(attr=\"%s\")" % (attr))
        return self._client.getAttributeValue(entry, attr)

    def setAttributeValue(self, entry, attr, value):
        _log ("UPS_Client_MEMOVA.setAttributeValue(attr=\"%s\", value=\"%s\")" % (attr,value))
        return self._client.setAttributeValue(entry, attr, value)
        
    def replaceAttributeValue(self, entry, attr, value):
        _log ("UPS_Client_MEMOVA.replaceAttributeValue(attr=\"%s\", value=\"%s\")" % (attr,value))
        return self._client.replaceAttributeValue(entry, attr, value)

class UPS_Client_MOS:
    def __init__(self, cfgname = None):
        self.client = MOS_Client(cfgname, 30)

    def getUPSIntf(self):
        pass

    def readUser(self, userName, domain, rollup = TRUE, rollupServices = None):
        return self.client.send(("USER SHOW %s %s" % (userName, domain)))

    def readDomain(self, domain):
        return self.client.send(("DOMAIN SHOW %s" % domain))

    def getAttributeValue(self, entry, attr):
        # mappings
        dict = {"attr.sid" : "SID", "attr.user.Password" : "password"}
        attrName = dict[attr]
        if entry is None or attrName is None :
            return

        lines = entry.toString().splitlines()
        for ln in lines:
            index = ln.find(attrName + "=")
            if index != -1:
                return ln[(index + len(attrName) + 1):]
        return

    def setAttributeValue(self, entry, attr, value):
        pass
        
    def replaceAttributeValue(self, entry, attr, value):
         pass

class UPS_Client:
    def __init__(self, cfgname = None, props = None, mappingFile = None, url = None, user = None, password = None):
        if inMOSMode():
            self.client = UPS_Client_MOS("FSTELNET1")
        else:
            self.client = UPS_Client_MEMOVA(cfgname, props, mappingFile, url, user, password)

    def getUPSIntf(self):
        return self.client.getUPSIntf()

    def readUser(self, userName, domain, rollup = TRUE, rollupServices = None):
        return self.client.readUser(userName, domain, rollup = TRUE, rollupServices = None)

    def readDomain(self, domain):
        return self.client.readDomain(domain)

    def getAttributeValue(self, entry, attr):
        return self.client.getAttributeValue(entry, attr)

    def setAttributeValue(self, entry, attr, value):
        return self.client.setAttributeValue(entry, attr, value)
        
    def replaceAttributeValue(self, entry, attr, value):
        return self.client.replaceAttributeValue(entry, attr, value)


# Locator library
from javax.naming import Context
from java.util import Hashtable
from javax.naming.directory import InitialDirContext

class Locator_Client:
    def __init__(self, cfgname = None, props = None, mappingFile = None, url = None, user = None, password = None):
        _log ("Locator_Client.__init__(cfgname=\"%s\")" % (cfgname))
        if cfgname is None:
            self._locURL = url
            self._locUser = user
            self._locPass = password
        else:
            self._locURL = cfg.get(cfgname, "locURL")
            self._locUser = cfg.get(cfgname, "locUser")
            self._locPass = cfg.get(cfgname, "locPass")

        env=Hashtable()
        env.put(Context.INITIAL_CONTEXT_FACTORY, "com.sun.jndi.ldap.LdapCtxFactory")
        env.put(Context.PROVIDER_URL,self._locURL)
        env.put(Context.SECURITY_AUTHENTICATION, "simple")
        env.put(Context.SECURITY_PRINCIPAL,self._locUser)
        env.put(Context.SECURITY_CREDENTIALS,self._locPass)
        ctx =InitialDirContext(env)
        self.ctx = ctx

        _log ("Locator_Client.__init__(_locURL=\"%s\")" % (self._locURL))
        _log ("Locator_Client.__init__(_locUser=\"%s\")" % (self._locUser))
        _log ("Locator_Client.__init__(_locPass=\"%s\")" % (self._locPass))
        self._props = props
        self._mappingFile = mappingFile
        self._client = LocatorClient(testcase, self._locURL, self._locUser, self._locPass, self._props, self._mappingFile)

    def getLocatorIntf(self):
        _log ("Locator_Client.getLocatorIntf()")
        return self._client.getLocatorIntf()

    def getUserBundle(self, user, domain):
        _log ("Locator_Client.getUserBundle(user=\"%s@%s\")" % (user, domain))
        self._user = user
        self._domain = domain
        return self._client.getUserBundle(self._user,self._domain)

    def setDomainPreferredBundles(self, domain, prefBundles):
        _log ("Locator_Client.setDomainPreferredBundles(domain=\"%s\", prefBundles=\"%s\")" % (domain,prefBundles))
        self._domain = domain
        self._prefBundles = prefBundles
        return self._client.setDomainPreferredBundles(self._domain,self._prefBundles)

    def getDomainPreferredBundles(self, domain):
        _log ("Locator_Client.getDomainPreferredBundles(domain=\"%s\")" % (domain))
        self._domain = domain
        return self._client.getDomainPreferredBundles(self._domain)

    def addDomainServiceBundle(self, domain, bundle):
        _log ("Locator_Client.addDomainBundle(domain=\"%s\", bundle=\"%s\")" % (domain,bundle))
        self._domain = domain
        self._bundle = bundle
        return self._client.addDomainServiceBundle(self._domain,self._bundle)

    def getDomainServiceBundle(self, domain, locString, bundleName):
         _log ("Locator_Client.getDomainServiceBundle(domain=\"%s\", locString=\"%s\", bundleName=\"%s\")" % (domain,locString,bundleName))
         self._domain = domain
         self._locString = locString
         self._bundleName = bundleName
         return self._client.getDomainServiceBundle(self._domain,self._locString,self._bundleName)

    def getUserServiceLocation(self, user, domain, locString):
         _log ("Locator_Client.getUserServiceLocation( user=\"%s\",domain=\"%s\", locString=\"%s\")" % (domain,user,locString))
         self._user = user
         self._domain = domain
         self._locString = locString

         return self._client.getUserServiceLocation( self._user,self._domain, self._locString)

    def getDefaultPedId(self, cn):
        _log ("Locator_Client.getDefaultPedId(cn=\"%s\")" % cn)
        entrydn = "cn="+cn+", cn=default, cn=defaults, cn=ped, cn=platform, cn=cproot"
        resAtts = ["cpPEDPrimary"]
        atts = self.ctx.getAttributes(entrydn,resAtts)
        pedId = str(atts.get("cpPEDPrimary").get())
        return pedId

#
# CS API Client
#
# NOTE: The CSAPI is no longer available after CAL 9.2.002, where only CalDAV access is supported (so use CalDAV_Client,
#       CpCalDAV_Client or WEBDAV_Client instead).
#
class CSAPI_Client:
    def __init__(self, calHostName, calUser, calPass, calHostPort = 0):
        _log ("CSAPI_Client.__init__(calHostName=\"%s\")" % (calHostName))
        _log ("CSAPI_Client.__init__(calHostPort=\"%s\")" % (calHostPort))
        _log ("CSAPI_Client.__init__(calUser=\"%s\")" % (calUser))
        _log ("CSAPI_Client.__init__(calPass=\"%s\")" % (calPass))
        self._client = CSAPIClient(testcase, calHostName, calHostPort, calUser, calPass)

    def createCalendar(self, calendarName, userAtDomainSid, description, timeZoneOffset):
        _log ("CSAPI_Client.createCalendar(calendarName=\"%s\" userAtDomainSid=\"%s\" description=\"%s\" timeZoneOffset=\"%s\"" % (calendarName, userAtDomainSid, description, timeZoneOffset))
        return self._client.createCalendar(calendarName, userAtDomainSid, description, timeZoneOffset)

    def createCalendarType(self, calendarName, userAtDomainSid, description, timeZoneOffset, calendarType):
        _log ("CSAPI_Client.createCalendar(calendarName=\"%s\" userAtDomainSid=\"%s\" description=\"%s\" timeZoneOffset=\"%s\" calendarType=\"%s\"" % (calendarName, userAtDomainSid, description, timeZoneOffset,calendarType))
        return self._client.createCalendar(calendarName, userAtDomainSid, description, timeZoneOffset, calendarType)

    def getEmptyEvent(self):
        _log ("CSAPI_Client.getEmptyEvent")
        return self._client.getEmptyEvent()

    def addRecurrenceRuleToEvent(self, object, frequency, interval, untilDate, selectedDayOfWeek, dayOfMonth, isEvent, count = -1):
        _log ("CSAPI_Client.addRecurrenceRuleToEvent(frequency=\"%s\" interval=\"%s\" untilDate=\"%s\" selectedDayOfWeek=\"%s\" dayOfMonth=\"%s\" isEvent=\"%s\" count=\"%s\"" % (frequency, interval, untilDate, selectedDayOfWeek, dayOfMonth, isEvent, count))
        return self._client.addRecurrenceRuleToEvent(object, frequency, interval, untilDate, count, selectedDayOfWeek, dayOfMonth, isEvent)

    def addDetailsToEvent(self, event, startTime, endTime, timeZoneOffset, summary, description, location, attendees, organizerUserAtDomain, alarm, isAllDay, avilability, privacy, relcalID = None):
        _log ("CSAPI_Client.addDetailsToEvent(startTime=\"%s\" endTime=\"%s\" timeZoneOffset=\"%s\" summary=\"%s\" description=\"%s\" location=\"%s\" organizerUserAtDomain=\"%s\" isAllDay=\"%s\" avilability=\"%s\" privacy=\"%s\" relcalID=\"%s\"" % (startTime, endTime, timeZoneOffset, summary, description, location, organizerUserAtDomain, isAllDay, avilability, privacy, relcalID))
        return self._client.addDetailsToEvent(event, startTime, endTime, timeZoneOffset, summary, description, location, attendees, organizerUserAtDomain, alarm, isAllDay, avilability, privacy, relcalID)

    def addToDoDetailsToCalendar(self, task, dueDate, timeZoneOffset, summary, description, status, priority, attachment, alarm):
        _log ("CSAPI_Client.addToDoDetailsToCalendar(dueDate=\"%s\" timeZoneOffset=\"%s\" summary=\"%s\" description=\"%s\" status=\"%s\" priority=\"%s\" attachment=\"%s\"" % (dueDate, timeZoneOffset, summary, description, status, priority, attachment))
        return self._client.addToDoDetailsToCalendar(task, dueDate, timeZoneOffset, summary, description, status, priority, attachment, alarm)

    def addAttachment(self, object, uri, data, isEvent):
        _log ("CSAPI_Client.addAttachment(uri=\"%s\" isEvent=\"%s\")" % (uri, isEvent))
        return self._client.addAttachment(object, uri, data, isEvent)

    def addRecurrenceRuleToTask(self, task, dtstart, frequency, interval, untilDate, count, selectedDayOfWeek, dayOfMonth):
        _log ("CSAPI_Client.addRecurrenceRuleToTask(dtstart=\"%s\" frequency=\"%s\" interval=\"%s\" untilDate=\"%s\" count=\"%s\" selectedDayOfWeek=\"%s\" dayOfMonth=\"%s\"" % (dtstart, frequency, interval, untilDate, count, selectedDayOfWeek, dayOfMonth))
        return self._client.addRecurrenceRuleToTask(task, dtstart, frequency, interval, untilDate, count, selectedDayOfWeek, dayOfMonth)

    def addRecurrenceReference(self, instance, master, isEvent):
        _log ("CSAPI_Client.addRecurrenceReference()")
        return self._client.addRecurrenceReference(instance, master, isEvent)

    def addExceptionDate(self, object, dat, isEvent):
        _log ("CSAPI_Client.addExceptionDate(dat=\"%s\" isEvent=\"%s\"" % (dat, isEvent))
        return self._client.addExceptionDate(object, dat, isEvent)

    def addExceptionDateTime(self, object, dattim, isEvent):
        _log ("CSAPI_Client.addExceptionDateTime(dattim=\"%s\" isEvent=\"%s\"" % (dattim, isEvent))
        return self._client.addExceptionDateTime(object, dattim, isEvent)

    # Get an email alarm
    def getAlarm(self, weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, reminderType):
        _log ("CSAPI_Client.getAlarm(weeks=\"%s\" days=\"%s\" hours=\"%s\" minutes=\"%s\" seconds=\"%s\" description=\"%s\" summary=\"%s\" organizerUserAtDomain=\"%s\" reminderType=\"%s\"" % (weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, reminderType))
        return self._client.getAlarm(weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, reminderType)

    # Get an email alarm with attendees
    def getAlarmWithAttendees(self, weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, attendees, reminderType):
        _log ("CSAPI_Client.getAlarm(weeks=\"%s\" days=\"%s\" hours=\"%s\" minutes=\"%s\" seconds=\"%s\" description=\"%s\" summary=\"%s\" organizerUserAtDomain=\"%s\" reminderType=\"%s\"" % (weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, reminderType))
        return self._client.getAlarm(weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain, attendees, reminderType)

    # Get a display alarm
    def getDisplayAlarm(self, weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain):
        _log ("CSAPI_Client.getDisplayAlarm(weeks=\"%s\" days=\"%s\" hours=\"%s\" minutes=\"%s\" seconds=\"%s\" description=\"%s\" summary=\"%s\" organizerUserAtDomain=\"%s\"" % (weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain))
        return self._client.getDisplayAlarm(weeks, days, hours, minutes, seconds, description, summary, organizerUserAtDomain)

    def createEvent(self, event, calendarId, fanOut = "itip"):
        _log ("CSAPI_Client.createEvent(event=\"%s\" calendarId=\"%s\" fanOut=\"%s\"" % (event, calendarId, fanOut))
        return self._client.createEvent(event, calendarId, fanOut)

    def createTask(self, task, calendarId):
        _log ("CSAPI_Client.createTask(task=\"%s\" calendarId=\"%s\"" % (task, calendarId))
        return self._client.createTask(task, calendarId)

    def retrieveTask(self, taskId, recurrenceId, calendarId):
        return self._client.retrieveTask(taskId, recurrenceId, calendarId)

    def createImipEvent(self, event, calendarId):
        _log ("CSAPI_Client.createImipEvent(event=\"%s\" calendarId=\"%s\"" % (event, calendarId))
        return self._client.createImipEvent(event, calendarId)

    def getXChar(self):
        _log ("CSAPI_Client.getXChar")
        return self._client.getXChar()

    def deleteEvent(self, eventId, recurrenceId, calendarId):
        _log ("CSAPI_Client.deleteEvent(eventId=\"%s\" recurrenceId=\"%s\" calendarId=\"%s\"" % (eventId, recurrenceId, calendarId))
        return self._client.deleteEvent(eventId, recurrenceId, calendarId)

    def updateEvent(self, eventId, calendarId, addContent, updateContent, removeContent, removeMissing, fanOut = "itip"):
        _log ("CSAPI_Client.updateEvent(eventId=\"%s\" calendarId=\"%s\" addContent=\"%s\" updateContent=\"%s\" removeContent=\"%s\" removeMissing=\"%s\" fanOut=\"%s\"" % (eventId, calendarId, addContent, updateContent, removeContent, removeMissing, fanOut))
        return self._client.updateEvent(eventId, calendarId, addContent, updateContent, removeContent, removeMissing, fanOut)

    def deleteCalendar(self, calendarId):
        _log ("CSAPI_Client.deleteCalendar(calendarId=\"%s\"" % (calendarId))
        return self._client.deleteCalendar(calendarId)

    def deleteCalendarTimeOut(self, calendarId, timeout):
        _log ("CSAPI_Client.deleteCalendar(calendarId=\"%s,%d\"" % (calendarId,timeout))
        return self._client.deleteCalendar(calendarId,timeout)

    def retrieveEvent(self, eventId, recurrenceId, calendarId):
        _log ("CSAPI_Client.retrieveEvent(eventId=\"%s\" recurrenceId=\"%s\" calendarId=\"%s\"" % (eventId, recurrenceId, calendarId))
        return self._client.retrieveEvent(eventId, recurrenceId, calendarId)

    def retrieveEvents(self, startTime, endTime, calendarId, timeZoneOffset):
        _log ("CSAPI_Client.retrieveEvents(startTime=\"%s\" endTime=\"%s\" calendarId=\"%s\" timeZoneOffset=\"%s\"" % (startTime, endTime, calendarId, timeZoneOffset))
        return self._client.retrieveEvents(startTime, endTime, calendarId, timeZoneOffset)

    def retrieveTasks(self, startTime, endTime, calendarId, timeZoneOffset):
        return self._client.retrieveTasks(startTime, endTime, calendarId, timeZoneOffset)
#

# Eureka client

class Eureka_Client:
    def __init__(self, eurekaHost, eurekaPort, eurekaPath, appId, appHost, appPort, appIp):
        _log ("Eureka_Client.__init__(eurekaHost=\"%s\", eurekaPort=\"%s\", eurekaPath=\"%s\, appId=\"%s\", appHost=\"%s\", appPort=\"%s\", appIp\"%s\""
            % (eurekaHost, eurekaPort, eurekaPath, appId, appHost, appPort, appIp))
        self._client = EurekaApplication(testcase, eurekaHost, eurekaPort, eurekaPath, appId, appHost, appPort, appIp)
        
    def register(self):
        return self._client.register()
        
    def unregister(self):
        return self._client.unregister()
    
# CalDAV client

class CalDAV_Client:
    def __init__(self, calHostName, calId, calUser, calDomain, calPass, calHostPort = 5211):
        _log ("CALDav_Client.__init__(calHostName=\"%s\")" % (calHostName))
        _log ("CALDav_Client.__init__(calHostPort=\"%s\")" % (calHostPort))
        _log ("CALDav_Client.__init__(calId=\"%s\")" % (calId))
        _log ("CALDav_Client.__init__(calUser=\"%s\")" % (calUser))
        _log ("CALDav_Client.__init__(calDomain=\"%s\")" % (calDomain))
        _log ("CALDav_Client.__init__(calPass=\"%s\")" % (calPass))
        self._client = CalDAVClient(testcase, calHostName, calHostPort, calId, calUser, calDomain, calPass)

    def addBasicEvent(self):
        _log ("CalDAV_Client.addBasicEvent")
        return self._client.addBasicEvent()

    def listEventIds(self):
        _log ("CalDAV_Client.listEventIds")
        return self._client.listEventIds()

    def deleteEvent(self, eventId):
        _log ("CalDAV_Client.deleteEvent(id=\"%s\")" % (eventId))
        return self._client.deleteEvent(eventId)

    def clearCalendar(self):
        _log("CalDAV_Client.clearCalendar()")
        self._client.clearCalendar()

    def propFind(self, path, propTag, depth):
        _log("CalDAV_Client.propFind")
        self._client.propFind(path, propTag, depth)


#

def getXmlHelper(data, defaultNS, nsSep):
    return XMLParserHelper(testcase, data, defaultNS, nsSep)

def isAvailable(cfgname):
    # may be set in cfg
    available = cfg.get(cfgname, "available")
    if available != None:
        _log ("isAvailable(cfgname=\"%s\") returns %s" % (cfgname, available) )
        return available
    # not in cfg so look at host
    # null host name normally indicates disabled
    # this might need to be improved
    cfghost = cfg.get(cfgname, "host")
    if (cfghost is None) or (cfghost == '') or (cfghost == 'nohost.invalid'):
        _log ("isAvailable(cfgname=\"%s\") returns 0" % (cfgname))
        return FALSE
    _log ("isAvailable(cfgname=\"%s\") returns 1" % (cfgname) )
    return TRUE

def isLocalhost(cfgname):
    cfghost = cfg.get(cfgname, "host")
    if (cfghost is None) or (cfghost == ''):
        _log ("isLocalhost(cfgname=\"%s\") returns FALSE because \"host\" is not defined" % (cfgname))
        return FALSE
    if (cfghost == '127.0.0.1') or (cfghost == 'localhost'):
        _log ("isLocalhost(cfgname=\"%s\") returns TRUE because \"host\" is %s" % (cfgname,cfghost))
        return TRUE
    localhost = java.net.InetAddress.getLocalHost();
    localhostname = localhost.getCanonicalHostName();

    if localhostname == cfghost :
        _log ("isLocalhost(cfgname=\"%s\") returns TRUE because CanonicalHostName matches %s" % (cfgname,cfghost))
        return TRUE
    if localhost.getHostAddress() == cfghost:
        _log ("isLocalhost(cfgname=\"%s\") returns TRUE because HostAddress matches %s" % (cfgname,cfghost))
        return TRUE
    _log ("isLocalhost(cfgname=\"%s\") returns FALSE. %s does match hostname or IP address of localhost" % (cfgname,cfghost))
    return FALSE

# global functions
def getListSize(lst):
    _log('getListSize() lst=\"%s\"' % (repr(lst.toString())))
    if lst is None:
        _log('getListSize: - invalid lst parameter')
        return 0
    else:
        lst = lst.toString()
        lines = lst.splitlines()
        count = 0
        for ln in lines:
            count = count + 1
        _log('getListSize: - returns %d' % (count))
        return count

# case insensitive string find
def ifind(str, substr):
    if str is None or substr is None :
        return -1
    else:
        str1 = str.lower()
        substr1 = substr.lower()
        return str1.find(substr1)

# return data between opening and closing tags
def xmlFind(xmldata, name):
    if xmldata is None or len(xmldata) == 0:
        return None
    if name is None or len(name) == 0:
        return None
    tag = '<%s>' % name
    start = xmldata.find(tag)
    if start > 0:
        start += len(tag)
        tag = '</%s>' % name
        end = xmldata[start:].find(tag)
        if end > 0:
            return xmldata[start:start+end]
    else:
        return None

def getStatusCounterName(str):
    if str is None:
        return None

    indx = str.strip().find(' ')
    if indx > 0:
        return str[indx:].strip()
    return None

def getPerfCounterName(str):
    if str is None:
        return None

    start = str.strip().find('NAME=')
    if start > 0:
        end = str[start+5:].find(' ')
        if end > 0:
            return str[start+5:end]
        else:
            return str[start+5:]
    else:
        return None

def getLocalHostAddress():
    return java.net.InetAddress.getLocalHost().getHostAddress()

def getCanonicalHostName():
    return java.net.InetAddress.getLocalHost().getCanonicalHostName()

def int_convert(arg):
    try: return int(arg)
    except: pass
    return long(arg)

def sleep(millis, description=None):
    text = "Sleeping for %s ms" % (millis)
    if description:
        text = "Sleeping for %s ms. %s" % (millis, description)
    _log (text)
    print text
    try:
        java.lang.Thread.sleep(millis);
        _log("sleep done")
    except java.lang.InterruptedException:
        pass

def getRandomInt(max = java.lang.Integer.MAX_VALUE):
    r = getGlobal("_getRandomInt_")
    if r is None:
        r = java.util.Random(java.lang.System.currentTimeMillis())
        setGlobal("_getRandomInt_", r)
    rn =  r.nextInt(max)
    _log("getRandomInt() returns %u" % rn )
    return rn

# time format used by many MRS commands like USER ADD
# use negative offset to get time in past
def getZuluTimeStr(offsetInSeconds=0):
    localtime = java.util.GregorianCalendar();
    zuluCal = java.util.GregorianCalendar(java.util.TimeZone.getTimeZone("Zulu"));
    tmmilli = localtime.getTimeInMillis()

    tmmilli = tmmilli + (1000 * offsetInSeconds)
    zuluCal.setTimeInMillis(tmmilli)
    year = zuluCal.get(java.util.Calendar.YEAR);
    month = 1 + zuluCal.get(java.util.Calendar.MONTH);
    day = zuluCal.get(java.util.Calendar.DAY_OF_MONTH);
    hour = zuluCal.get(java.util.Calendar.HOUR_OF_DAY);
    mins = zuluCal.get(java.util.Calendar.MINUTE);
    sec = zuluCal.get(java.util.Calendar.SECOND);
    timestr = "%04d%02d%02d%02d%02d%02d" % (year,month, day, hour, mins, sec)
    _log("getZuluTimeStr(%d) returns %s" % (offsetInSeconds, timestr))
    return timestr

# Time format used by IFS management command EXPIRATION= settings
# use negative offset to get time in past.
#
# Same as getZuluTimeStr except precision is only to Minutes instead of
# Seconds
#
def getZuluTimeStrMins(offsetInSeconds=0):
    localtime = java.util.GregorianCalendar();
    zuluCal = java.util.GregorianCalendar(java.util.TimeZone.getTimeZone("Zulu"));
    tmmilli = localtime.getTimeInMillis()

    tmmilli = tmmilli + (1000 * offsetInSeconds)
    zuluCal.setTimeInMillis(tmmilli)
    year = zuluCal.get(java.util.Calendar.YEAR);
    month = 1 + zuluCal.get(java.util.Calendar.MONTH);
    day = zuluCal.get(java.util.Calendar.DAY_OF_MONTH);
    hour = zuluCal.get(java.util.Calendar.HOUR_OF_DAY);
    mins = zuluCal.get(java.util.Calendar.MINUTE);

    timestr = "%04d%02d%02d%02d%02d" % (year,month, day, hour, mins)
    _log("getZuluTimeStr(%d) returns %s" % (offsetInSeconds, timestr))
    return timestr

# Timestamp format used by Calendar Server (iCal)
# Gets Current Time as iCal Stamp
#

def getIcalTimeStamp():
    localtime = java.util.GregorianCalendar();
    year = localtime.get(java.util.Calendar.YEAR);
    month = 1 + localtime.get(java.util.Calendar.MONTH);
    day = localtime.get(java.util.Calendar.DAY_OF_MONTH);
    hour = localtime.get(java.util.Calendar.HOUR_OF_DAY);
    mins = localtime.get(java.util.Calendar.MINUTE);
    sec = localtime.get(java.util.Calendar.SECOND);

    stamp = "%04d%02d%02dT%02d%02d%02dZ" %(year, month, day, hour, mins, sec)
    _log("getIcaltimeStamp() returns %s" %(stamp))
    return stamp

# Convert any iCal format TimeStamp into a Java Calender Object
#

def icalToJavaCal(iCalStr):

    ret = java.util.Calendar.getInstance();

    year = int(iCalStr[0:4])
    month = int(iCalStr[4:6]) - 1
    day = int(iCalStr[6:8])
    hour = int(iCalStr[9:11])
    mins = int(iCalStr[11:13])
    secs = int(iCalStr[13:15])

    ret.set(java.util.Calendar.YEAR, year)
    ret.set(java.util.Calendar.MONTH, month)
    ret.set(java.util.Calendar.DAY_OF_MONTH, day)
    ret.set(java.util.Calendar.HOUR_OF_DAY, hour)
    ret.set(java.util.Calendar.MINUTE, mins)
    ret.set(java.util.Calendar.SECOND, secs)

    _log("icalToJavaCal(%s) returns %s" % (iCalStr, ret))

    return ret

# Change a Java calender into an iCal Stamp
#

def javaCalToIcal(c = java.util.Calendar):

    year = c.get(java.util.Calendar.YEAR);
    month = 1 + c.get(java.util.Calendar.MONTH);
    day = c.get(java.util.Calendar.DAY_OF_MONTH);
    hour = c.get(java.util.Calendar.HOUR_OF_DAY);
    mins = c.get(java.util.Calendar.MINUTE);
    sec = c.get(java.util.Calendar.SECOND);

    stamp = "%04d%02d%02dT%02d%02d%02dZ" %(year, month, day, hour, mins, sec)
    _log("javaCalToIcal(%s) returns %s" % (c, stamp))
    return stamp

# takes in an iCal formatted timestamp,
# adds any number of years, months, days, hours, minutes and seconds to it
# and returns the result as an iCal timestamp

def addTimeToIcalStamp(iCalStr, years = 0, months = 0, days = 0, hours = 0, minutes = 0, seconds = 0):

    cal = icalToJavaCal(iCalStr)

    cal.add(java.util.Calendar.YEAR, years)
    cal.add(java.util.Calendar.MONTH, months)
    cal.add(java.util.Calendar.DAY_OF_MONTH, days)
    cal.add(java.util.Calendar.HOUR_OF_DAY, hours)
    cal.add(java.util.Calendar.MINUTE, minutes)
    cal.add(java.util.Calendar.SECOND, seconds)

    stamp = javaCalToIcal(cal)
    _log("addTimeToIcalStamp(%s,%s,%s,%s,%s,%s,%s) returns %s" % (iCalStr, years, months, days, hours, minutes, seconds, stamp))
    return stamp

def setIcalStamp(year = 2010, month = 0, dayOfMonth = 1, hourOfDay = 0, minute = 0, seconds = 0, dayOfYear = None, weekOfYear = None ):

    cal = java.util.Calendar.getInstance()

    cal.set(java.util.Calendar.YEAR, year)
    cal.set(java.util.Calendar.MONTH, month)
    cal.set(java.util.Calendar.DAY_OF_MONTH, dayOfMonth)
    cal.set(java.util.Calendar.HOUR_OF_DAY, hourOfDay)
    cal.set(java.util.Calendar.MINUTE, minute)
    cal.set(java.util.Calendar.SECOND, seconds)

    if dayOfYear != None:
        cal.set(java.util.Calendar.DAY_OF_YEAR, dayOfYear)

    if weekOfYear != None:
        cal.set(java.util.Calendar.WEEK_OF_YEAR, weekOfYear)

    stamp = javaCalToIcal(cal)

    _log("setIcalStamp(%s,%s,%s,%s,%s,%s,%s,%s) returns %s" % (year, month, dayOfMonth, hourOfDay, minute, seconds, dayOfYear, weekOfYear, stamp))

    return stamp

# Returns a random date and time,
# from somewhere in the near future


def getRandomIcalTimeStamp(shiftDays = 0, shiftHours = 0):

    # get the current timestamp, create a random number of hours and seconds and add it to the stamp
    stamp = getIcalTimeStamp()
    hours = getRandomInt(max = 30000) + shiftHours
    secs = getRandomInt(max = 3600)

    randStamp =  addTimeToIcalStamp(stamp, days = shiftDays, hours = hours, seconds = secs)
    _log("getRandomIcalTimeStamp() returns %s" % (randStamp))
    return randStamp


# Check the version of server
def checkInfoVersion(_mgmt, comparison, ver_str, serverLogId):
    _mgr = MGR_Client(_mgmt, 30)
    info = _mgr.getValue("INFO")
    _mgr.close()
    arr = info.split()
    ver = arr[1]

    return checkVersion(ver_str, comparison, ver, serverLogId)

def compare_num_version(num1, num2):

    try:
        v1 = int(num1)
    except:
        v1 = -1
    
    try:
        v2 = int(num2)
    except:
        v2 = -1

    # For non numeric version part (for ex git hash number)
    # compare as is, otherwise compare numerical values
    if v2 == -1 or v1 == -1:
        if num1 > num2:
            return 1
        elif num1 < num2:
            return -1
        else:
            return 0
    return v1 - v2

def checkVersion(ver_str, comparison, serverVersion, server):
    _log("checkVersion() %s %s %s %s" % (repr(serverVersion), comparison, ver_str, server) )
    if ver_str is None:
        raise ValueError, "checkVersion(): invalid ver_str"
    if serverVersion is None:
        raise ValueError, "checkVersion(): No Server Version value"
    ver_arr = ver_str.split('.')
    server_arr = serverVersion.split('.')
    index = len (ver_arr)
    # pad out to len of version
    while index < len (server_arr):
        ver_arr.append('0')
        index += 1
    index = 0
    lt = FALSE; gt = FALSE
    while index < len(server_arr):
        ret = compare_num_version(server_arr[index], ver_arr[index])
        if ret > 0:
            gt = TRUE
            break
        if ret < 0:
            lt = TRUE;
            break
        index +=1
        
    if comparison == '>':
        return gt
    elif comparison == '==':
        return lt == FALSE and gt == FALSE
    elif comparison == '<':
        return lt
    elif comparison == '<=':
        return lt == TRUE or gt == FALSE
    elif comparison == '>=':
        return lt == FALSE or gt == TRUE
    else:
        raise ValueError, "checkVersion(): invalid comparison operator %s" % comparison

def getMRSVersion():
    _log("getMRSVersion() returns %s" % mrsversion)
    return mrsversion

def getMRSBuildNo():
    _log("getMRSBuildNo() returns %s" % mrsbuildno)
    return mrsbuildno

def isMRSVerGT(ver_str):
    res = checkVersion(ver_str, ">", mrsversion, "MRS")
    _log("isMRSVerGT(%s) returns %u" % (ver_str, res) )
    return res
def isMRSVerLT(ver_str):
    res = checkVersion(ver_str, "<", mrsversion, "MRS")
    _log("isMRSVerLT(%s) returns %u" % (ver_str, res) )
    return res
def isMRSVerEQ(ver_str):
    res = checkVersion(ver_str, "==", mrsversion, "MRS")
    _log("isMRSVerEQ(%s) returns %u" % (ver_str, res) )
    return res
def isMRSVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", mrsversion, "MRS")
    _log("isMRSVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res
def isMRSVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", mrsversion, "MRS")
    _log("isMRSVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def checkMRSVer(ver_str, comparison):
    _log("checkMRSVer() %s %s %s" % (repr(mrsversion), comparison, ver_str) )
    if ver_str is None:
        raise ValueError, "checkMRSVer(): invalid ver_str"
    if mrsversion is None:
        raise ValueError, "checkMRSVer(): No MRS Version value"
    
    return checkVersion(ver_str, comparison, mrsversion, "MRS")

def setMRSVersion(ver_str = None):
    """setMRSVersion  function"""
    _log("setMRSVersion()\"%s\"" % ver_str)
    global mrsversion
    global mrsbuildno
    mrsversion = ""
    mrsbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            mrsversion = arr[2]
        if len(arr) >= 5:
            mrsbuildno = arr[4]


def getPABVersion():
    _log("getPABVersion() returns %s" % pabversion)
    return pabversion

def getPABBuildNo():
    _log("getPABBuildNo() returns %s" % pabbuildno)
    return pabbuildno

def isPABVerGT(ver_str):
    res = checkVersion(ver_str, ">", pabversion, "PAB")
    _log("isPABVerGT(%s) returns %u" % (ver_str, res) )
    return res
def isPABVerLT(ver_str):
    res = checkVersion(ver_str, "<", pabversion, "PAB")
    _log("isPABVerLT(%s) returns %u" % (ver_str, res) )
    return res
def isPABVerEQ(ver_str):
    res = checkVersion(ver_str, "==", pabversion, "PAB")
    _log("isPABVerEQ(%s) returns %u" % (ver_str, res) )
    return res
def isPABVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", pabversion, "PAB")
    _log("isPABVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res
def isPABVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", pabversion, "PAB")
    _log("isPABVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def checkPABVer(ver_str, comparison):
    _log("checkPABVer() %s %s %s" % (repr(pabversion), comparison, ver_str) )
    if ver_str is None:
        raise ValueError, "checkPABVer(): invalid ver_str"
    if pabversion is None:
        raise ValueError, "checkPABVer(): No PAB Version value"
    return checkVersion(ver_str, comparison, pabversion, "PAB")

def setPABVersion(ver_str = None):
    """setPABVersion  function"""
    _log("setPABVersion()\"%s\"" % ver_str)
    global pabversion
    global pabbuildno
    pabversion = ""
    pabbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            pabversion = arr[2]
        if len(arr) >= 5:
            pabbuildno = arr[4]

def setPABVersion2(ver_str = None):
    """setPABVersion2  function"""
    _log("setPABVersion2()\"%s\"" % ver_str)
    global pabversion2
    global pabbuildno2
    pabversion2 = ""
    pabbuildno2 = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            pabversion2 = arr[2]
        if len(arr) >= 5:
            pabbuildno2 = arr[4]

def getPABVersion2():
    _log("getPABVersion2() returns %s" % pabversion2)
    return pabversion2

def getPABBuildNo2():
    _log("getPABBuildNo2() returns %s" % pabbuildno2)
    return pabbuildno2

def isPAB2VerGT(ver_str):
    res = checkVersion(ver_str, ">", pabversion2, "PAB")
    _log("isPAB2VerGT(%s) returns %u" % (ver_str, res) )
    return res
def isPAB2VerLT(ver_str):
    res = checkVersion(ver_str, "<", pabversion2, "PAB")
    _log("isPAB2VerLT(%s) returns %u" % (ver_str, res) )
    return res
def isPAB2VerEQ(ver_str):
    res = checkVersion(ver_str, "==", pabversion2, "PAB")
    _log("isPAB2VerEQ(%s) returns %u" % (ver_str, res) )
    return res
def isPAB2VerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", pabversion2, "PAB")
    _log("isPAB2VerGTEQ(%s) returns %u" % (ver_str, res) )
def isPAB2VerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", pabversion2, "PAB")
    _log("isPAB2VerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def checkPAB2Ver(ver_str, comparison):
    _log("checkPAB2Ver() %s %s %s" % (repr(pabversion2), comparison, ver_str) )
    if ver_str is None:
        raise ValueError, "checkPAB2Ver(): invalid ver_str"
    if pabversion is None:
        raise ValueError, "checkPAB2Ver(): No PAB Version value"
    return checkVersion(ver_str, comparison, pabversion2, "PAB")


def getCALVersion():
    _log("getCALVersion() returns %s" % calversion)
    return calversion

def getCALBuildNo():
    _log("getCALBuildNo() returns %s" % calbuildno)
    return calbuildno

def isCALVerGT(ver_str):
    res = checkVersion(ver_str, ">", calversion, "CAL")
    _log("isCALVerGT(%s) returns %u" % (ver_str, res) )
    return res
def isCALVerLT(ver_str):
    res = checkVersion(ver_str, "<", calversion, "CAL")
    _log("isCALVerLT(%s) returns %u" % (ver_str, res) )
    return res
def isCALVerEQ(ver_str):
    res = checkVersion(ver_str, "==", calversion, "CAL")
    _log("isCALVerEQ(%s) returns %u" % (ver_str, res) )
    return res
def isCALVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", calversion, "CAL")
    _log("isCALVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res
def isCALVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", calversion, "CAL")
    _log("isCALVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res


def checkCALVer(ver_str, comparison):
    _log("checkCALVer() %s %s %s" % (repr(calversion), comparison, ver_str) )
    if ver_str is None:
        raise ValueError, "checkCALVer(): invalid ver_str"
    if calversion is None:
        raise ValueError, "checkCALVer(): No CAL Version value"
    return checkVersion(ver_str, comparison, calversion, "CAL")


def setCALVersion(ver_str = None):
    """setCALVersion  function"""
    _log("setCALVersion()\"%s\"" % ver_str)
    global calversion
    global calbuildno
    calversion = ""
    calbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            calversion = arr[2]
        if len(arr) >= 5:
            calbuildno = arr[4]


def setPSVersion(ver_str = None):
    _log("setPSVersion()\"%s\"" % ver_str)
    setGlobal("ps_version", ver_str)

def getSMLVersion():
    _log("getSMLVersion() returns %s" % smlversion)
    return smlversion

def getSMLBuildNo():
    _log("getSMLBuildNo() returns %s" % smlbuildno)
    return smlbuildno

def isSMLVerGT(ver_str):
    res = checkVersion(ver_str, ">", smlversion, "SML")
    _log("isSMLVerGT(%s) returns %u" % (ver_str, res) )
    return res
def isSMLVerLT(ver_str):
    res = checkVersion(ver_str, "<", smlversion, "SML")
    _log("isSMLVerLT(%s) returns %u" % (ver_str, res) )
    return res
def isSMLVerEQ(ver_str):
    res = checkVersion(ver_str, "==", smlversion, "SML")
    _log("isSMLVerEQ(%s) returns %u" % (ver_str, res) )
    return res
def isSMLVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", smlversion, "SML")
    _log("isSMLVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res
def isSMLVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", smlversion, "SML")
    _log("isSMLVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def setSMLVersion(ver_str = None):
    """setSMLVersion  function"""
    _log("setSMLVersion()\"%s\"" % ver_str)
    global smlversion
    global smlbuildno
    smlversion = ""
    smlbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            smlversion = arr[2]
        if len(arr) >= 5:
            smlbuildno = arr[4]

def getUMCVersion():
    _log("getUMCVersion() returns %s" % umcversion)
    return umcversion

def getUMCBuildNo():
    _log("getUMCBuildNo() returns %s" % umcbuildno)
    return umcbuildno

def isUMCVerGT(ver_str):
    res = checkVersion(ver_str, ">", umcversion, "UMC")
    _log("isUMCVerGT(%s) returns %u" % (ver_str, res) )
    return res

def isUMCVerLT(ver_str):
    res = checkVersion(ver_str, "<", umcversion, "UMC")
    _log("isUMCVerLT(%s) returns %u" % (ver_str, res) )
    return res

def isUMCVerEQ(ver_str):
    res = checkVersion(ver_str, "==", umcversion, "UMC")
    _log("isUMCVerEQ(%s) returns %u" % (ver_str, res) )
    return res

def isUMCVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", umcversion, "UMC")
    _log("isUMCVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res

def isUMCVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", umcversion, "UMC")
    _log("isUMCVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def setUMCVersion(ver_str = None):
    """setUMCVersion  function"""
    _log("setUMCVersion()\"%s\"" % ver_str)
    global umcversion
    global umcbuildno
    umcversion = ""
    umcbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            umcversion = arr[2]
        if len(arr) >= 5:
            umcbuildno = arr[4]

def getGSSVersion():
    _log("getGSSVersion() returns %s" % gssversion)
    return gssversion

def getGSSBuildNo():
    _log("getGSSBuildNo() returns %s" % gssbuildno)
    return gssbuildno

def isGSSVerGT(ver_str):
    res = checkVersion(ver_str, ">", gssversion, "GSS")
    _log("isGSSVerGT(%s) returns %u" % (ver_str, res) )
    return res

def isGSSVerLT(ver_str):
    res = checkVersion(ver_str, "<", gssversion, "GSS")
    _log("isGSSVerLT(%s) returns %u" % (ver_str, res) )
    return res

def isGSSVerEQ(ver_str):
    res = checkVersion(ver_str, "==", gssversion, "GSS")
    _log("isGSSVerEQ(%s) returns %u" % (ver_str, res) )
    return res

def isGSSVerGTEQ(ver_str):
    res = checkVersion(ver_str, ">=", gssversion, "GSS")
    _log("isGSSVerGTEQ(%s) returns %u" % (ver_str, res) )
    return res

def isGSSVerLTEQ(ver_str):
    res = checkVersion(ver_str, "<=", gssversion, "GSS")
    _log("isGSSVerLTEQ(%s) returns %u" % (ver_str, res) )
    return res

def setGSSVersion(ver_str = None):
    """setGSSVersion  function"""
    _log("setGSSVersion()\"%s\"" % ver_str)
    global gssversion
    global gssbuildno
    gssversion = ""
    gssbuildno = ""
    if ver_str is not None:
        ver_str = str(ver_str) # convert to python string
        arr = ver_str.split()
        # E.g. ['*', 'mms3.cpth.ie', '1.5.5.0', 'Build', '1', 'WIN32/UNIX']
        if len(arr) >= 3:
            gssversion = arr[2]
        if len(arr) >= 5:
            gssbuildno = arr[4]

def index_of(ids, id):
    try:
        _log("Index of '%s' in '%s'" % (id, ids))
        idx = 0
        for i in ids:
            if i == id:
                return idx
            idx = idx +1
        idx = -1
    except:
        idx = -1
    return idx

def xml_escape(str):
    _log("xml_escape(%s)" % (str) )

    count = 0
    res = ""
    while count < len(str):
        esc = FALSE
        s = str[count]
        c = ord(s)

        if c < 0x20:
            res = "%s&#%d;" % (res, c)
        elif c > 0x7E:
            res = "%s&#%d;" % (res, c)
        elif c in [ 0x22, 0x23, 0x25, 0x26, 0x27, 0x3B, 0x3C, 0x3E, 0x5B, 0x5C, 0x5D, 0x5E]:
            res = "%s&#%d;" % (res, c)
        else:
            res = "%s%s" % (res, s)

        count = count + 1
    return res


def qpdecode(filename):
    """ Decode specified quoted printable file and return contents as string
    """
    _log("qpdecode(%s)" % filename )
    fl_txt = open(filename, 'r')
    filetxtqpdec = filename+'.tmp'
    fl_qpdec = open(filetxtqpdec,'w')
    try : quopri.decode(fl_txt, fl_qpdec )
    finally:
        fl_txt.close()
        fl_qpdec.close()

    fl_qpdec = open(filetxtqpdec ,'r')
    try: str = fl_qpdec.read()
    finally: fl_qpdec.close()
    return str

def fileread(filename):
    """ Read file and return contents as string
    """
    _log("fileread(%s)" % filename )
    fl_txt = open(filename, 'r')
    try: str = fl_txt.read()
    finally: fl_txt.close()
    return str

def fileBinread(filename):
    """ Read file and return contents as string
    """
    _log("fileBinread(%s)" % filename )
    fl_txt = open(filename, 'rb')
    try: str = fl_txt.read()
    finally: fl_txt.close()
    return str

def filewrite(filename, str):
    """ Write the specified string to the specified file
    """
    _log("filewrite(%s, %s)" % (filename, str) )
    fl_txt = open(filename, 'w')
    try: fl_txt.write(str)
    finally: fl_txt.close()
    return

def fileexists(filename):
    """Check the file exists
    """
    _log("fileexists(%s)" % (filename) )
    fp1 = java.io.File(filename)
    if not fp1.exists():
        _log("file (%s) does not exist" % (filename) )
        return FALSE
    else:
        if fp1.isDirectory():
            _log("file (%s) is a directory" % (filename) )
            return FALSE
        else:
            return TRUE

def folderexists(filename):
    """Check the folder exists
    """
    _log("folderexists (%s)" % (filename) )
    fp1 = java.io.File(filename)
    if not fp1.exists():
        _log("folder (%s) does not exist" % (filename) )
        return FALSE
    else:
        if not fp1.isDirectory():
            _log("folder (%s) is not a directory" % (filename) )
            return FALSE
        else:
            return TRUE

def makeFile(fileName, size):
    _log("makeFile() - name=[%s], size=%d" % (fileName, size))

    # remove file if it exists
    file = java.io.File(fileName)
    if file.exists():
        os.remove(fileName)

    # just create and empty file if necessary
    if (size <= 0):
        file.createNewFile()
        return

    # create a buffer of random data
    i = 0
    bufferSize = random.randint(1024, 4096)
    if (bufferSize > size):
        bufferSize = size
    buffer = zeros(bufferSize, "b")
    while (i < bufferSize):
        buffer[i] = random.randint(-127, 127)
        i = i + 1;

    # use the pre-created buffer to fill the file
    i = 0
    bufferCount = size / bufferSize
    outputStream = java.io.FileOutputStream(file)
    while (i < bufferCount):
        outputStream.write(buffer)
        i = i + 1;
    bufferRemainder = size - (bufferSize * bufferCount)
    if (bufferRemainder > 0):
        outputStream.write(buffer, 0, bufferRemainder)

    outputStream.close()

def filegenerate(filename, size):
    makeFile(filename,size)

def filecompare(f1, f2):
    _log("filecmp(%s,%s)" % (f1,f2) )
    if f1 == f2:
        raise ValueError, "filecmp() Comparing file with itself"
    fp1 = java.io.File(f1)
    if not fp1.exists():
        _log("filecmp returns FALSE - %s does not exist" % (f1) )
        return FALSE
    fp2 = java.io.File(f2)
    if not fp2.exists():
        _log("filecmp returns FALSE - %s does not exist" % (f2) )
        return FALSE
    if fp1.length() != fp2.length():
        _log("filecmp returns FALSE - file sizes differ")
        return FALSE

    in1 = java.io.FileInputStream(fp1)
    in2 = java.io.FileInputStream(fp2)

    offset = 0
    buffer1 = zeros(10240, "b")
    buffer2 = zeros(10240, "b")
    same = 1
    while same:
        bytes_read1 = in1.read(buffer1)
        bytes_read2 = in2.read(buffer2)

        if bytes_read1 != bytes_read2:
            _log("filecmp bytes_read value is different")
            same = 0
        elif (bytes_read1 > 0):
            _log("filecmp read %d bytes from both files" % bytes_read1)
            for i in range(0, bytes_read1):
                offset +=1
                if buffer1[i] != buffer2[i]:
                    _log("filecmp detected difference at byte %d" % offset)
                    same = 0
                    break
        else:
            break
    in1.close()
    in2.close()
    if same:
        _log("filecmp returns TRUE")
        return TRUE
    else:
        _log("filecmp returns FALSE")
        return FALSE

def filesize(f1):
    _log("filesize(%s)" % f1 )
    fp1 = java.io.File(f1)
    if not fp1.exists():
        _log("filesize returns 0 - %s does not exist" % (f1) )
        return 0

    _log("filesize returns %d" % fp1.length())
    return fp1.length()

def _log(str):
    """harness log function for internal functions. Obeys debug setting"""
    global testcase
    trace(str)
    try:
        if testcase is not None:
            testcase.log("(Harness) "+str)
    except NameError:
        pass
    except AttributeError:
        pass

def log(str):
    """print to screen and log"""
    global testcase
    print(str)
    try:
        if testcase is not None:
            testcase.log("(log) "+str)
    except NameError:
        pass
    except AttributeError:
        pass

def trace(str):
    """trace  function"""
    global debug
    try:
        if debug is not None:
            if debug:
                print("(trace) "+str)
    except NameError:
        print("(trace) "+str)
    except AttributeError:
        print("(trace) "+str)

def initTestcaseContext():
    """Harness is required to define an instance of testcase class
    before running each test scripts.
    Stored as global so it's available in all scopes and testcase writer
    does not need to know anything about it."""
    global testcase
    # check for testcase instance (in case left over from previous test)
    try:
        if testcase is not None:
            testcase.close()
            del testcase
    except NameError:
        pass
    except AttributeError:
        pass

def setTestcaseTitle(title):
    global testcase
    try:
        testcase.title(title)
    except NameError:
        raise ValueError, "Harness error: testcase must be defined before running test case"
    except AttributeError:
        raise ValueError, "Harness error: testcase must be defined before running test case"

def checkPSVer(version, dev_versions, min_version):
    if version is None:
        version = getGlobal("ps_version")

    if getGlobal("ps_version") is None:
        setGlobal("ps_version", version)

    # Check development versions first
    for ver in dev_versions:
        if version == ver:
            return TRUE

    # Check minimum version
    if version >= min_version:
        return TRUE

    return FALSE

##
## Returns 1 if server version falls within range
##  Defaults are provided to allow checking "newer than":
##          check_version_range("CPMS1_SMTP_MGMT", "8.0") ---- return 1 if 8.0 or higher.
##  or "older than":
##          check_version_range("CPMS1_SMTP_MGMT", max_version = "8.0") ---- return 1 if 8.0 or lower
##  Currently, only the first two digits are checked
##
def check_version_range(server, min_version="0.0", max_version="99.9"):
        msmgr = MGR_Client(server, 30)
        result = msmgr.send("INFO")
        str = result.toString()
        values = str.split(' ')
        version = values[2]
        server_versions = version.split('.')

        min_versions = min_version.split('.')

        max_versions = max_version.split('.')

        if server_versions[0] < min_version[0]:
                return FALSE    ## Major version too low
        if server_versions[0] == min_version[0] and server_versions[1] < min_versions[1]:
                return FALSE    ## Minor version too low

        if server_versions[0] > max_versions[0]:
                return FALSE    ## Major version too high
        if server_versions[0] == max_version[0] and server_versions[1] > max_versions[1]:
                return FALSE    ## Minor version too high

        print "version is ok"
        return TRUE

# IMAP/POP mailbox comparison, dumping

##
## compareMailboxes()
##
## compare each folder (and subfolders) on 'imap_src' with those on 'imap_dst'
##
def compareMailboxes(src_server, src_user, src_pass, dst_server, dst_user, dst_pass, match_uids = TRUE):

    try:
        imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
    except:
        log("IMAP Login failed - retrying")
        try:
            imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
        except:
            testSetResultFail(details="IMAP Login failed")
            return FALSE

    try:
        imap_dst = IMAP_Client(dst_server, dst_user, dst_pass, FALSE)
    except:
        testSetResultFail(details="IMAP Login failed")
        imap_src.close()
        return FALSE

    folder_names = imap_src.listFolders()

    if folder_names == None:
        log("listFolders returned nothing!")
        imap_src.close()
        imap_dst.close()
        return FALSE

    for i in range (0, len(folder_names)):
        if folder_names[i] != None:
            if compareFolders(imap_src, imap_dst, folder_names[i], match_uids) == FALSE:
                imap_src.close()
                imap_dst.close()
                return FALSE

    imap_src.close()
    imap_dst.close()
    return TRUE


##
## compareFolders()
##
## compare messages and subfolders in 'folder_name'
##
def compareFolders(imap_src, imap_dst, folder_name, match_uids):
    try:
        f_src = imap_src.getFolder(folder_name)
        uidvalidity_src = f_src.getUIDValidity()
        uidnext_src = f_src.getUIDNext()
        msg_count_src = f_src.getMessageCount()
    except:
        log("error selecting folder '%s', skipping" % (folder_name))
        return TRUE

    try:
        f_dst = imap_dst.getFolder(folder_name)
        uidvalidity_dst = f_dst.getUIDValidity()
        uidnext_dst = f_dst.getUIDNext()
        msg_count_dst = f_dst.getMessageCount()
    except:
        log("error selecting folder '%s'" % (folder_name))
        return FALSE

    log("[%d] '%s' contains %d messages (uidnext=%d)" % (uidvalidity_src, folder_name, msg_count_src, uidnext_src))

    # compare UIDValidity
    if match_uids and uidvalidity_src != uidvalidity_dst:
        log("UIDVALIDITY mismatch for '%s': %d != %d" % (folder_name, uidvalidity_src, uidvalidity_dst))
        return FALSE

    # compare UIDNext
    if match_uids and uidnext_src != uidnext_dst:
        log("UIDNEXT mismatch for '%s': %d != %d" % (folder_name, uidnext_src, uidnext_dst))
        return FALSE

    # compare message counts
    if msg_count_src != msg_count_dst:
        log("message count mismatch for '%s': %d != %d" % (folder_name, msg_count_src, msg_count_dst))
        return FALSE

    # compare messages
    if msg_count_src > 0:
        imap_src.selectFolder(folder_name)
        msgs_src = imap_src.getUIDs()

        imap_dst.selectFolder(folder_name)
        msgs_dst = imap_dst.getUIDs()

        if match_uids and msgs_src != msgs_dst:
            log("message mismatch for '%s': %s != %s" % (folder_name, msgs_src, msgs_dst))
            return FALSE

        # compare message sizes, subjects
        for i in range (len(msgs_src)):
            if imap_src.getMessage(i + 1).getSize() != imap_dst.getMessage(i + 1).getSize():
                log("message %d: size of %d != %d" % (i + 1, imap_src.getMessage(i + 1).getSize(), imap_dst.getMessage(i + 1).getSize()))
                return FALSE
            if imap_src.getMessage(i + 1).getSubject() != imap_dst.getMessage(i + 1).getSubject():
                log("message %d: subject of '%s' != '%s'" % (i + 1, imap_src.getMessage(i + 1).getSubject(), imap_dst.getMessage(i + 1).getSubject()))
                return FALSE

    # compare subfolders
    subfolder_names = imap_src.listFolders(folder_name)

    if subfolder_names != None:
        for i in range (0, len(subfolder_names)):
            if compareFolders(imap_src, imap_dst, folder_name + "/" + subfolder_names[i], match_uids) == FALSE:
                return FALSE

    return TRUE

##
## compareMOSInboxes
##
## compare two POP inboxes.  don't assume the order will be the same.
## we'll build a hashtable from the UID,size of one inbox, then iterate
## through the other inbox, making sure we find all the messages.
##

def compareMOSInboxes(src_server, src_user, src_pass, dst_server, dst_user, dst_pass):

     log("compareMOSInboxes:IMAP server=%s,IMAP USER=%s, IMAP PASS =%s" %(src_server,src_user,src_pass))
     log("compareMOSInboxes:POP server=%s,POP USER=%s,POP PASS =%s" %(dst_server,dst_user,dst_pass))
     try:
        imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
     except:
        log("IMAP Login failed - retrying")
        try:
            imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
        except:
            testSetResultFail(details="IMAP Login failed")
            return FALSE

     try:
        f_src = imap_src.getFolder("INBOX")
        imap_uidvalidity_src = f_src.getUIDValidity()
        imap_uidnext_src = f_src.getUIDNext()
        imap_msg_count_src = f_src.getMessageCount()
        imap_uids_src = imap_src.getUIDs()
     except:
        log("error selecting Inbox")
        return FALSE

     try:
        pop_dst = POP_Client(dst_server, dst_user, dst_pass)
     except:
        testSetResultFail(details="POP Login failed")
        return FALSE


     pop_uids_dst = pop_dst.getUIDs()
     pop_sizes_dst = pop_dst.getSizes()
     pop_msgs_dst = pop_dst.getMessages()

     # must be the same number of messages in Inbox of IMAP and POP mailbox

     if imap_msg_count_src != len(pop_uids_dst):
        log("message count mismatch: %d != %d" % (len(mos_uids), len(dst_uids)))
        return FALSE

     # add each src UID/size pair, add to a hash map

     srcmap = HashMap()

     for i in range (0, len(imap_uids_src)):
        mos_uid = "%s.%s" % (imap_uidvalidity_src, imap_uids_src[i])
        srcmap.put(mos_uid, imap_src.getMessage(i+1).getSize())

     # for each dst message, find its UID/size in the hash map - should have a match for all

     for i in range (0, len(pop_uids_dst)):
        sz = srcmap.get(pop_uids_dst[i])
        if sz is None:
            log("message %d: no message found with UIDL value of '%s'" % (i + 1, pop_uids_dst[i]))
            return FALSE
        if int(sz) != pop_sizes_dst[i]:
            log("message %d: size of %d != %d" % (i + 1, pop_sizes_dst[i], int(sz)))
            return FALSE

     pop_dst.close()
     imap_src.close()

     return TRUE


# IMAP/POP mailbox comparison with FOLDERMAP option, dumping

##
## compareSpecificMailboxes()
##
## This is called for MIGRATE with FOLDERMAP option
##
## compare each folder  on 'imap_src' with those on 'imap_dst'
##
def compareSpecificMailboxes(src_server, src_user, src_pass, dst_server, dst_user, dst_pass, fold_src = [], fold_dest =[], exist_fold = [],inbox_existing_msg_cnt=0,match_uids = TRUE):

    print "inbox_existing_msg_cnt= %d" % inbox_existing_msg_cnt
    try:
        imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
    except:
        log("IMAP Login failed - retrying")
        try:
            imap_src = IMAP_Client(src_server, src_user, src_pass, FALSE)
        except:
            testSetResultFail(details="IMAP Login failed")
            return FALSE

    try:
        imap_dst = IMAP_Client(dst_server, dst_user, dst_pass, FALSE)
    except:
        testSetResultFail(details="IMAP Login failed")
        imap_src.close()
        return FALSE

    folder_names = imap_src.listFolders()

    if folder_names == None:
        log("listFolders returned nothing!")
        imap_src.close()
        imap_dst.close()
        return FALSE

    for i in range (0, len(folder_names)):
        compare_fold_with = None
        exist = FALSE
        print "exist for folder_name=%s is  %d" % (folder_names[i],exist)
        if (folder_names[i] == "INBOX"):
           existing_msg_cnt = inbox_existing_msg_cnt
        else:
           existing_msg_cnt = 0
        print "folder_name = %s, inbox_existing_msg_cnt= %d" % (folder_names[i], existing_msg_cnt)
        if folder_names[i] != None:
            for j in range (0,len(fold_src)):
                print "folder_names =%s, fold_src=%s" % (folder_names[i],fold_src[j])
                if folder_names[i] == fold_src[j] :
                   compare_fold_with = fold_dest[j]
                   if folder_names[i] in exist_fold:
                      exist = TRUE
                   break
        if compareSpecificFolders(imap_src, imap_dst, folder_names[i], compare_fold_with, existing_msg_cnt, exist, match_uids) == FALSE:
            imap_src.close()
            imap_dst.close()
            return FALSE

    imap_src.close()
    imap_dst.close()
    return TRUE


##
## compareSpecificFolders()
##
## This is called for MIGRATE with FOLDERMAP option
##
## compare message count and UIDNEXT in 'folder_name'
##
def compareSpecificFolders(imap_src, imap_dst, folder_name, compare_fold_with, existing_msg_cnt, exist, match_uids):
    try:
        f_src = imap_src.getFolder(folder_name)
        uidvalidity_src = f_src.getUIDValidity()
        uidnext_src = f_src.getUIDNext()
        msg_count_src = f_src.getMessageCount()
    except:
        log("error selecting folder '%s', skipping" % (folder_name))
        return TRUE

    try:
        if compare_fold_with != None:
           folder_name = compare_fold_with
        f_dst = imap_dst.getFolder(folder_name)
        uidvalidity_dst = f_dst.getUIDValidity()
        uidnext_dst = f_dst.getUIDNext()
        msg_count_dst = f_dst.getMessageCount()
    except:
        log("error selecting folder '%s'" % (folder_name))
        return FALSE

    log("[%d] '%s' contains %d messages (uidnext=%d)" % (uidvalidity_src, folder_name, msg_count_src, uidnext_src))

    # compare UIDValidity
    print "exist for folder_name=%s is  %d" % (folder_name,exist)
    if exist == TRUE:
        if match_uids and uidvalidity_src != uidvalidity_dst:
            log("UIDVALIDITY mismatch for '%s': %d != %d" % (folder_name, uidvalidity_src, uidvalidity_dst))
            return FALSE

    # compare UIDNext
    if match_uids and (uidnext_src+existing_msg_cnt) != uidnext_dst:
        log("UIDNEXT mismatch for '%s': %d != %d" % (folder_name, uidnext_src, uidnext_dst))
        return FALSE

    # compare message counts
    if (msg_count_src+existing_msg_cnt) != msg_count_dst:
        log("message count mismatch for '%s': %d != %d" % (folder_name, msg_count_src, msg_count_dst))
        return FALSE

    return TRUE


##
## dumpMailbox()
##
## show contents of IMAP mailbox
##
def dumpMailbox(_server, _user, _pass):

    log("Dumping mailbox: '%s' on '%s'" % (_user, cfg.get(_server, "host")))

    try:
        imap = IMAP_Client(_server, _user, _pass, FALSE)
    except:
        log("IMAP Login failed")
        return

    folder_names = imap.listFolders()

    if folder_names == None:
        log("listFolders returned nothing!")
    else:
        for i in range (0, len(folder_names)):
            if folder_names[i] != None:
                dumpFolder(imap, folder_names[i])

    imap.close()

##
## dumpFolder()
##
## show contents of IMAP folder
##
def dumpFolder(imap, folder_name):
    try:
        f = imap.getFolder(folder_name)
        uidvalidity = f.getUIDValidity()
        uidnext = f.getUIDNext()
        msg_count = f.getMessageCount()
    except:
        log("error selecting folder '%s', skipping" % (folder_name))
        return

    log("[%d] '%s' contains %d messages (uidnext=%d)" % (uidvalidity, folder_name, msg_count, uidnext))

    # for each mssage, dump message summary
    if msg_count > 0:
        imap.selectFolder(folder_name)
        msgs = imap.getUIDs()

        # dump message sizes, subjects
        for i in range (len(msgs)):
            log(" %d: [UID=%d] [%d] '%s'" % (i + 1, msgs[i], imap.getMessage(i + 1).getSize(), imap.getMessage(i + 1).getSubject()))

    # dump subfolders
    subfolder_names = imap.listFolders(folder_name)

    if subfolder_names != None:
        for i in range (0, len(subfolder_names)):
            dumpFolder(imap, folder_name + "/" + subfolder_names[i])

##
## dumpPopInbox()
##
## show contents of POP Inbox
##
def dumpPopInbox(_server, _user, _pass):

    log("Dumping POP inbox: '%s' on '%s'" % (_user, cfg.get(_server, "host")))

    try:
        pop = POP_Client(_server, _user, _pass)
    except:
        log(details="POP Login failed")
        return

    uids = pop.getUIDs()
    msgs = pop.getMessages()
    sizes = pop.getSizes()

    # dump message sizes, subjects

    for i in range (0, len(uids)):
        log(" %d: [%d] '%s' '%s'" % (i + 1, sizes[i], uids[i], msgs[i].getSubject()))

    pop.close()

##
## comparePopInboxes()
##
## compare two POP inboxes.  don't assume the order will be the same.
## we'll build a hashtable from the UID,size of one inbox, then iterate
## through the other inbox, making sure we find all the messages.
##
def comparePopInboxes(src_server, src_user, src_pass, dst_server, dst_user, dst_pass):

    try:
        pop_src = POP_Client(src_server, src_user, src_pass)
    except:
        log("POP Login failed - retrying")
        try:
            pop_src = POP_Client(src_server, src_user, src_pass)
        except:
            testSetResultFail(details="POP Login failed")
            return FALSE

    try:
        pop_dst = POP_Client(dst_server, dst_user, dst_pass)
    except:
        testSetResultFail(details="POP Login failed")
        return FALSE

    src_uids = pop_src.getUIDs()
    src_sizes = pop_src.getSizes()
    src_msgs = pop_src.getMessages()

    dst_uids = pop_dst.getUIDs()
    dst_sizes = pop_dst.getSizes()
    dst_msgs = pop_dst.getMessages()

    # must be the same number of messages

    if len(src_uids) != len(dst_uids):
        log("message count mismatch: %d != %d" % (len(src_uids), len(dst_uids)))
        return FALSE

    # add each src UID/size pair, add to a hash map

    srcmap = HashMap()

    for i in range (0, len(src_uids)):
        srcmap.put(src_uids[i], src_sizes[i])

    # for each dst message, find its UID/size in the hash map - should have a match for all

    for i in range (0, len(dst_uids)):
        sz = srcmap.get(dst_uids[i])
        if sz is None:
            log("message %d: no message found with UIDL value of '%s'" % (i + 1, dst_uids[i]))
            return FALSE
        if int(sz) != dst_sizes[i]:
            log("message %d: size of %d != %d" % (i + 1, dst_sizes[i], int(sz)))
            return FALSE

    pop_src.close()
    pop_dst.close()

    return TRUE

# return the next message sequence number, wrapping at '_max'.
# e.g. nextMsgSequence(0, 3) returns 1
#      nextMsgSequence(1, 3) returns 2
#      nextMsgSequence(2, 3) returns 3
#      nextMsgSequence(3, 3) returns 1
def nextMsgSequence(_last, _max):
    _last += 1
    if _last > _max:
        _last = 1
    return _last

##
## populateMailbox()
##
## create some folders and messages.
## Creates the folders specified in '_create_folders'.
## Creates '_n_msgs' messages in the INBOX, then copies those messages to
## the folders specified in '_copy_to_folders'.
## Finally, deletes a message from each folder, so that the UID lists and
## UIDNEXT values are slightly different.
##
def populateMailbox(_imap_server, _user, _pass, _n_msgs = 3, _create_folders = [], _copy_to_folders = []):
    log("populate mailbox: %s" % (_user))
    try:
        imap = IMAP_Client(_imap_server, _user, _pass, FALSE)
    except:
        testSetResultFail(details="IMAP Login failed")
        return FALSE

    for f in _create_folders:
        if imap.createFolder(f) == FALSE:
            testSetResultFail(details="create folder failed")
            return FALSE

    # Save some messages

    imap.selectFolder("INBOX")

    from_address = _user
    to_address = _user
    msg_subject = "test%d--%.*s"
    msg_body = "body%d"

    # create the requested number of messages, in the INBOX

    for i in range (_n_msgs):
        msg = imap.createMessage()

        msg.setFrom(from_address)
        msg.setTo(to_address)
        msg.setSubject(msg_subject % (i, random.randint(1, 26), "abcdefghijklmnopqrstuvwxyz"))
        msg.setText(msg_body % i)

        imap.appendMessage(msg)

    if imap.getMessageCount() != _n_msgs:
        testSetResultFail(details="wrong message count: %d" % (imap.getMessageCount()))
        return FALSE

    _del = 0

    # copy messages from INBOX to requested folders

    for f in _copy_to_folders:
        imap.copyMessages("INBOX", f)

        # delete a message, to leave UID gap

        imap.selectFolder(f)
        _del = nextMsgSequence(_del, _n_msgs)
        imap.deleteMessage(_del)
        imap.expungeMessages()

    # delete a message from the INBOX, to leave UID gap

    imap.selectFolder("INBOX")
    _del = nextMsgSequence(_del, _n_msgs)
    imap.deleteMessage(_del)
    imap.expungeMessages()

    imap.close()

    # ensure UIDVALIDITY uniqueness
    sleep(1000)

##
## alterPopUids()
##
## 1. scp mailbox.dat to local system (after converting to text, for v4)
## 2. adjust so that messages have different POP UIDs
## 3. scp mailbox.dat back (and then convert to binary, for v4)
##
def alterPopUids(_ims, _remote, _mbox, _mailbox_path):

    # skip this for windows

    if FileSeparator == '\\':
        log("Cannot alter POP UIDs on Windows - skipping")
        return TRUE

    if checkInfoVersion("CPMS1_IMS_MGMT", "<", "8.6", "CPMS"):
        mbox_ver = 3
    else:
        mbox_ver = 4

    # ensure it is safe to copy mailbox.dat

    _mgr = MGR_Client(_ims, 30)
    _mgr.checked_send("CONNECTION KILL %s" % _mbox)
    _mgr.close()

    mbox_local = "%s%s%s" % (getCurrentDir(), FileSeparator, "mailbox.dat")
    mbox_remote_path = "%s@%s:%s%s" % (cfg.get(_remote, "user"), cfg.get(_remote, "host"), _mailbox_path, '/')

    # if new mailbox format, run mailbox conversion utility
    if mbox_ver > 3:
        mbox_conv = "%s/global/bin/mailbox" % (cfg.get(_remote, "install"))
        mbox_file = "v4_mailbox.dat"
        cmd = "%s --write-text --input %s/%s --output %s/%s" % (mbox_conv, _mailbox_path, "mailbox.bin", _mailbox_path, mbox_file)

        ssh = SSH_Client(_remote)
        resp = ssh.executeCommand(cmd)
        print "Response: " + resp
        if ssh.getExitCode() != 0:
            testSetResultFail(details='failed to convert mailbox.bin to text')
            ssh.close()
            return FALSE
        ssh.close()
    else:
        mbox_file = "mailbox.dat"

    # get a copy of mailbox.dat to work with locally

    scp = "scp"
    mbox_remote = mbox_remote_path + mbox_file
    cmd = "%s %s %s" % (scp, mbox_remote, mbox_local)
    log("About to issue: " + cmd)
    ret = os.system(cmd)
    if ret != 0:
        testSetResultFail(details='failed to retrieve mailbox.dat')
        return FALSE

    # make changes to local mailbox.dat

    if adjustMailboxDat(mbox_local, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-", mbox_ver) == FALSE:
        testSetResultFail(details='failed to adjust mailbox.dat')
        return FALSE

    # copy the new mailbox.dat back

    cmd = "%s %s %s%s" % (scp, mbox_local, mbox_remote_path, "mailbox.bin.text")
    log("About to issue: " + cmd)
    ret = os.system(cmd)
    if ret != 0:
        testSetResultFail(details='failed to copy mailbox.bin.text back')
        return FALSE

    # if new mailbox format, run mailbox conversion utility
    if mbox_ver > 3:
        mbox_conv = "%s/global/bin/mailbox" % (cfg.get(_remote, "install"))
        cmd = "%s --write-binary --input %s/%s --output %s/%s" % (mbox_conv, _mailbox_path, "mailbox.bin.text", _mailbox_path, "mailbox.bin")

        ssh = SSH_Client(_remote)
        resp = ssh.executeCommand(cmd)
        print "Response: " + resp
        if ssh.getExitCode() != 0:
            testSetResultFail(details='failed to convert text to mailbox.bin')
            ssh.close()
            return FALSE
        ssh.close()

    return TRUE

##
## adjustMailboxDat()
##
## for each UID (3rd token of a MSG line), change "<n>" to "<n>+<tag><n>"
##
def adjustMailboxDat(_mbox, _tag, _ver):

    in_file = open(_mbox, 'r')
    m = in_file.readlines()
    in_file.close()

    print m

    out_file = open(_mbox, 'w')

    for l in m:
        t = l.split()
        if t[0] == "MSG":
            if _ver > 3:
                l = "%s %s %s+%s%s %s %s %s %s %s\n" % (t[0], t[1], t[2], _tag, t[2], t[3], t[4], t[5], t[6], t[7])
            else:
                l = "%s %s %s+%s%s %s %s %s %s\n" % (t[0], t[1], t[2], _tag, t[2], t[3], t[4], t[5], t[6])

        log("Writing: " + l)
        out_file.write(l)

    out_file.close()

    return TRUE

#--------------------------------------------

def inMOSMode():
    mosEnv = getGlobal("MOS_ENV")
    return mosEnv is not None and mosEnv == "YES"    

#--------------------------------------------

def removeCalDisplayPreferences(ups, user, dom):

    upsmgr = UPS_Client(ups)
    try:
        entry = upsmgr.readUser(user, dom, FALSE)
        if (entry is not None):
            entry.addModification(AttributeModificationType.DELETE, Attributes.CAL_USER_CLIENT_DISPLAY_PREFERENCES, None)
            entry.modify()
    except UPSLocatorException:
        _log("ignoring non-existent user")
    except UPSNoSuchEntryException:
        _log("ignoring error, as nothing to do")
    except:
        _log("ignoring general error")

#--------------------------------------------
# funcs to store global data

# use setGlobal, getGlobal
def setGlobal(name,value):
    global globalarray
    if globalarray is None:
            raise ValueError, "Harness error: globalarray not defined"
    globalarray[name] = value
    _log("setGlobal() %s=\"%s\")" % (name,value) )


def getGlobal(name, defaultval=None):
    global globalarray
    if globalarray is None:
            raise ValueError, "Harness error: globalarray not defined"
    try : val = globalarray[name]
    except KeyError: return defaultval
    if val is None:
        _log("getGlobal(%s) Null value found. Returning default \"%s\")" % (name,defaultval) )
        return defaultval
    else:
        _log("getGlobal(%s) returns \"%s\"" % (name,val) )
        return val


def delGlobal(name):
    global globalarray
    if globalarray is None:
            raise ValueError, "Harness error: globalarray not defined"
    try : del globalarray[name]
    except NameError: pass
    except KeyError: pass


def resetGlobal():
    global globalarray
    _log("resetGlobal() - deleting all global values" )
    if globalarray is None:
        raise ValueError, "Harness error: globalarray not defined"
    globalarray = {}


def getCurrentDir():
    global pwd
    try:
        ret =  pwd
        #path may be relative on windows
        #if pwd[0] != FileSeparator:
         #   ret = "%s%s%s" % (java.lang.System.getProperty("user.dir"), FileSeparator, ret)
        _log("getCurrentDir() returns \"%s\"" % ret )
        return ret
    except NameError:
        _log("getCurrentDir() No pwd value so return \".\"")
        return '.'
    except AttributeError:
        _log("getCurrentDir() No pwd value so return \".\"")
        return '.'

def getFullCurrentDir():
    global pwd
    try:
        ret = pwd
        _log("getFullCurrentDir() pwd = %s" % ret);
        ret = os.path.abspath(ret)
        _log("getFullCurrentDir() full = %s" % ret);

        #ret = pwd
        #_log("getFullCurrentDir() pwd = %s" % ret);
        # path may be relative on windows
        #if ret[0] != FileSeparator and ret[1] == ':':
        #    if (ret[0] >= 'a' and ret[0] <= 'z') or (ret[0] >= 'A' and ret[0] <= 'Z'):
        #        ret = "%s%s%s" % (java.lang.System.getProperty("user.dir"), FileSeparator, ret)
        #_log("getFullCurrentDir() returns \"%s\"" % ret )
        return ret
    except NameError:
        _log("getFullCurrentDir() No pwd value so return \".\"")
        return '.'
    except AttributeError:
        _log("getFullCurrentDir() No pwd value so return \".\"")
        return '.'

# Returns the full path to the directory containing the external tools
def getToolsDir():
    return java.lang.System.getProperty("cp.tools.path");


def removeDir(dir, force = FALSE):
    _log("removeDir() [%s] force(%d)" % (dir, force))

    if os.path.exists(dir):
        if force:
            if os.path.isdir(dir):
                list = os.listdir(dir)
                for i in list:
                    f = "%s%s%s" % (dir, FileSeparator, i)
                    if os.path.isdir(f):
                        removeDir(f, force)
                    else:
                        os.remove(f)
                os.rmdir(dir)
            else:
                os.remove(dir)
        else:
            os.rmdir(dir)

def removeFile(file):
    _log("removeFile() [%s]" % (file))

    if os.path.exists(file):
        os.remove(file)

def testExecuteRsh(sshserver, sshcmd, description = "Execute rsh", fail_on_success = FALSE):
    _log("Execute command on '" + sshserver + "': " + sshcmd)
    ssh = None
    try:
        ssh = SSH_Client(sshserver)
        ssh._client.setTestCase(testcase)
        resp = ssh.executeCommand(sshcmd)
        ssh.close()
        if fail_on_success:
            testcase.addResult(TestCase.FAILED,'%s - Got unexpected success for rsh cmd \"%s\"' % (description, sshcmd) )
            return FALSE
        else:
            testcase.addResult(TestCase.PASSED,'%s - Got expected success for rsh cmd \"%s\"' % (description, sshcmd) )
            return TRUE

    except:
        errstr = "Can't execute rsh command " + sshcmd + " error=" + str(sys.exc_info()[0]) + " on '" + sshserver + "'"
        _log(errstr)
        if ssh != None:
            ssh.close()

        if fail_on_success:
            testcase.addResult(TestCase.PASSED,'%s - Got expected failure for rsh cmd \"%s\"' % (description, sshcmd) )
            return TRUE
        else:
            testcase.addResult(TestCase.FAILED,'%s - Got unexpected failure for rsh cmd \"%s\"' % (description, sshcmd) )
            return FALSE

def testExecutePutFile(sshserver, localSrc, remoteDest, recursive = FALSE, description = "Execute remote put", fail_on_success = FALSE):
    _log("Execute put file '%s' to '%s' on '%s' - recursive(%s)" % (localSrc, remoteDest, sshserver, recursive))

    ssh = None
    result = FALSE
    try:
        ssh = SSH_Client(sshserver)
        result = ssh.executePutFile(localSrc, remoteDest, recursive)
        ssh.close()

    except:
        errstr = "Failed to put file - error=" + str(sys.exc_info()[0]) + " on '" + sshserver + "'"
        _log(errstr)
        if ssh != None:
            ssh.close()
        pass

    if result:
        if fail_on_success:
            testcase.addResult(TestCase.FAILED,'%s - Got unexpected success for remote put file' % (description) )
            return FALSE
        testcase.addResult(TestCase.PASSED,'%s - Got expected success for remote put file' % (description) )
        return TRUE
    else:
        if fail_on_success:
            testcase.addResult(TestCase.PASSED,'%s - Got expected failure for remote put file' % (description) )
            return TRUE
        testcase.addResult(TestCase.FAILED,'%s - Got unexpected failure for remote put file' % (description) )
        return FALSE


# next three definitions are used when wrapping users' scripts
# Put here so can be easily modified - no java compilation required
__SCRIPTWRAPPER_PREPEND = """
# -*- coding: UTF-8 -*-
import gc
class TestScriptWrapper(ScriptWrapper):
\tdef run(self):
"""

__SCRIPTWRAPPER_INDENT = """\t\t"""

__SCRIPTWRAPPER_APPEND = """
\t\t# automatically inserted tests to ensure all queues are empty
\t\ttestIsNull(MessageServer.checkqueues() ,"verify harness queues are empty")
\t\ttestMrsQueusAreEmpty()

MessageServer.setTestcase4all()
SMPP_Client.setTestcase4all()
thistest = TestScriptWrapper()
thistest.run()
del thistest      # remove from namespace
del TestScriptWrapper  # remove Class from namespace
gc.collect()
"""

class ScriptWrapper:
    """Purpose of script wrapper is to make life easy for test script writer.
    E.g. Clean up all variables so no leakage between scripts
    This class must be subclassed for each test script (run() is abstract).
    """

    def __init__(self):
        """Constructor
        Check the required globals are in place
        An instance of TestCase class called "testcase" must exist as a global.
        And an instance of Config called "cfg" must also be a global.
        Harness must take care of defining and cleaning up these values for
        each script
        """
        global cfg
        global globalarray
        global testcase
        if cfg is None:
            raise ValueError, "cfg must be defined before running test case"
        if globalarray is None:
            raise ValueError, "globalarray must be defined before running test case"
        if testcase is None:
            raise ValueError, "testcase must be defined before running test case"


    def run(self):
        raise ValueError, "Harness error: run is an abstract method. Must be overriden"


