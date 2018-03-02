# support classes for concurrent tasks

import threading
import time
import os
import hashlib
import random

from threading import Thread
from java.util.concurrent import TimeUnit
from java.util.concurrent import Executors, ExecutorCompletionService
from java.util.concurrent import Callable

class AbstractLogger(object):
    def __init__(_self):
        _self.logger = None

    def setLogger(_self, logger):
        _self.logger = logger

    def log(_self, msg):
        print msg

        if _self.logger == None:
            return

        _self.logger(msg)


# subclass this and override doWork for each worker class
class AbstractWorker(AbstractLogger):
    def __init__(_self):
        _self.exit = False
        return

    def shutdown(_self):
        _self.exit = True

    def isExit(_self):
        return _self.exit

    def doWork(_self):
        raise NotImplementedError("Please Implement this method")

# this worker repeatedly invokes another worker for a maximum number of iterations
class SequencedWorker(AbstractWorker):
    def __init__(_self, worker, iterations):
        AbstractWorker.__init__(_self)
        _self.pause = pauseSeconds
        _self.iterations = iterations
        _self.worker = worker

    def shutdown(_self):
        _self.worker.shutdown()
        AbstractWorker.shutdown(_self)

    def doWork(_self):
        while _self.iterations > 0:
            start = time.time()
            _self.worker.doWork()
            stop = time.time()
            p = (_self.pause * 1000) - (stop - start)
            if p > 0:
               d = p / 1000
               time.sleep(d)
            else:
               print "*** worker took too long to complete - no sleep ***"
            _self.iterations -= 1
            if _self.exit:
                _self.iterations = 0

# this worker repeatedly invokes another worker for a specified time period (in seconds)
class TimeSequencedWorker(AbstractWorker):
    def __init__(_self, worker, duration, pauseSeconds, startFactor = 0):
        AbstractWorker.__init__(_self)
        _self.pause = pauseSeconds
        _self.duration = duration
        _self.worker = worker
        _self.startFactor = startFactor

    def shutdown(_self):
        _self.worker.shutdown()
        AbstractWorker.shutdown(_self)

    def doWork(_self):
        if _self.startFactor > 0:
            # randomise startup between 0 and startFactor
            time.sleep(random.randint(0, _self.startFactor))
        workerStart = time.time()
        while AbstractWorker.isExit(_self) == False:
            start = time.time()
            _self.worker.doWork()
            stop = time.time()
            diff = stop - start
            p = (_self.pause * 1000) - (stop - start)
            if p > 0:
               d = p / 1000
               time.sleep(d)
            else:
               print "*** worker took too long to complete - no sleep ***"
            now = time.time()
            beenRunningFor = now - workerStart
            if beenRunningFor > _self.duration:
                print "*** SHUTDOWN WORKER AFTER %f SECONDS ***" % (beenRunningFor)
                AbstractWorker.shutdown(_self)

# subclass this and override doReport for each reporter class
class AbstractReporter(AbstractLogger):
    def __init__(_self, frequency):
        print "AbstractReporter constructor"
        _self.exit = False
        _self.frequency = frequency
        _self.output = "output"
        _self.thr = Thread(target=lambda: _self.runLoop())

    # subclass this method to run each report step
    def doReport(_self):
        print "AbstractReporter::doReport - WRONG"
        _self.exit = True
        raise NotImplementedError("Please Implement this method")

    def startReporting(_self):
        _self.log("start reporting")
        _self.thr.start()

    def stopReporting(_self):
        _self.log("stop reporting")
        _self.exit = True

    def isExit(_self):
        return _self.exit

    def runLoop(_self):
        _self.log("start runLoop %s" % (_self.frequency))
        _self.doReport()
        while _self.exit == False:
            time.sleep(_self.frequency)
            _self.doReport()
        _self.log("end runLoop")

    def setOutput(_self, output):
        _self.output = output

    # the default output method writes to a file
    def outputReport(_self, id, data):
        try:
            os.makedirs(_self.output)
        except OSError:
            pass
        fullname = "%s/%s.txt" % (_self.output, id)
        f = open(fullname, 'a')
        f.write(data)
        f.close()

# internal class - requires full path name for Callable
class Task(Callable):
    def __init__(_self, worker):
        _self.worker = worker
        _self.started = None
        _self.completed = None
        _self.result = None
        _self.thread_used = None
        _self.exception = None

    def toString(_self):
        return _self.__str__()

    def __str__(_self):
        if _self.exception:
             return "[%s] worker error %s in %.2fs" % \
                (_self.thread_used, _self.exception,
                 _self.completed - _self.started, ) #, _self.result)
        elif _self.completed:
            return "[%s] completed in %.2fs" % \
                (_self.thread_used,
                 _self.completed - _self.started, ) #, _self.result)
        elif _self.started:
            return "[%s] started at %s" % \
                (_self.thread_used, _self.started)
        else:
            return "[%s] not yet scheduled" % \
                (_self.thread_used)

    # needed to implement the Callable interface;
    # any exceptions will be wrapped as either ExecutionException
    # or InterruptedException
    def call(_self):
        _self.thread_used = threading.currentThread().getName()
        _self.started = time.time()
        try:
            _self.result = _self.worker.doWork()
        except Exception, ex:
            _self.exception = ex
        _self.completed = time.time()
        return _self

# this wraps the Task class - create one of these, add workers and an optional reporter, then call 'process'
class Concurrent(AbstractLogger):
    def __init__(_self, reporter = None, max_concurrency = 1000):
        _self.max_concurrency = max_concurrency
        _self.reporter = reporter
        _self.workers = []
        _self.pool = Executors.newFixedThreadPool(_self.max_concurrency)
        _self.ecs = ExecutorCompletionService(_self.pool)

    def shutdown_and_await_termination(_self, timeout):
        _self.log("...shutdown pool")
        _self.pool.shutdown()
        try:
            if not _self.pool.awaitTermination(timeout, TimeUnit.SECONDS):
            	_self.log("...shutdown timed out - SHUTDOWN NOW")
                _self.pool.shutdownNow()
            if (not _self.pool.awaitTermination(timeout, TimeUnit.SECONDS)):
            	_self.log("...shutdown_now timed out - ERROR")
                print >> sys.stderr, "Pool did not terminate"
        except InterruptedException, ex:
            # (Re-)Cancel if current thread also interrupted
            _self.pool.shutdownNow()
            # Preserve interrupt status
            _self.log("shutdown is interrupting the current thread")
            Thread.currentThread().interrupt()

    def scheduler(_self):
        for item in _self.workers:
            yield item

    # add an AbstractWorker subclass
    def addWorker(_self, w):
        _self.workers.append(w)

    def process(_self):
        if (_self.reporter != None):
            # start a reporter thread
            _self.reporter.startReporting()

        try:
            _self.log("submitting tasks")

            for w in _self.scheduler():
                _self.ecs.submit(Task(w))

            _self.log("tasks submitted OK")

            # work with results as soon as they become available
            submitted = len(_self.workers)
            while submitted > 0:
                try:
                    result = _self.ecs.take().get()
                    _self.log(result.toString())
                except Exception, ex:
                    _self.log("hit exception processing results %s" % (ex))

                submitted -= 1

        except Exception, ex:
        	_self.log("hit exception running tasks %s" % (ex))

        _self.log("shutting down...")

        for w in _self.workers:
            w.shutdown()

        time.sleep(5)

        _self.shutdown_and_await_termination(10)

        if (_self.reporter != None):
            # stop the reporter thread
            _self.reporter.stopReporting()

        time.sleep(5)

        _self.log("done")

# a basic performance stats reporter for CAL
class CALPerformanceReporter(AbstractReporter):
    def __init__(_self, frequency, id, client):
        # this next line works UNLESS this class is in HarnessLanguage
        # super(AbstractReporter, _self).__init__(frequency)

        # so do it this way, which works here...
        AbstractReporter.__init__(_self, frequency)

        t = time.time()
        _self.id = "%s-%s" % (id, t)
       # Full path is now passed in in id so results will be written to test case directory
        _self.setOutput("")
        _self.client = client

    def doReport(_self):
        print "CAL doReport"
        try:
            counters = _self.client()
            str = "output counters: %s" % (counters)
            _self.outputReport(_self.id, "---\n")
            for ent in counters:
                _self.outputReport(_self.id, "%s\n" % (ent))
        except Exception, ex:
            print ex


# a basic performance stats reporter for PAB
class CardDAVPerformanceReporter(AbstractReporter):
    def __init__(_self, frequency, id, client):
        # this next line works UNLESS this class is in HarnessLanguage
        # super(AbstractReporter, _self).__init__(frequency)

        # so do it this way, which works here...
        AbstractReporter.__init__(_self, frequency)

        t = time.time()
        _self.id = "%s-%s" % (id, t)
        # Full path is now passed in in id so results will be written to test case directory
        _self.setOutput("")
        _self.client = client

    def doReport(_self):
        print "PAB-CardDAV doReport"
        try:
            counters = _self.client()
            str = "output counters: %s" % (counters)
            _self.outputReport(_self.id, "---\n")
            for ent in counters:
                _self.outputReport(_self.id, "%s\n" % (ent))
        except Exception, ex:
            print ex

