"""A "dogpile" lock, one which allows a single thread to generate
an expensive resource while other threads use the "old" value, until the
"new" value is ready.

Usage::
    
    # store a reference to a "resource", some 
    # object that is expensive to create.
    the_resource = [None]

    def some_creation_function():
        # create the resource here
        the_resource[0] = create_some_resource()
        
    def use_the_resource():
        # some function that uses
        # the resource.  Won't reach
        # here until some_creation_function()
        # has completed at least once.
        the_resource[0].do_something()
        
    # create Dogpile with 3600 second
    # expiry time
    dogpile = Dogpile(3600)

    with dogpile.acquire(some_creation_function):
        use_the_resource()

Above, ``some_creation_function()`` will be called
when :meth:`.Dogpile.acquire` is first called.  The 
block then proceeds.   Concurrent threads which 
call :meth:`.Dogpile.acquire` during this initial period
will block until ``some_creation_function()`` completes.

Once the creation function has completed successfully,
new calls to :meth:`.Dogpile.acquire` will route a single
thread into new calls of ``some_creation_function()`` 
each time the expiration time is reached.  Concurrent threads
which call :meth:`.Dogpile.acquire` during this period will
fall through, and not be blocked.  It is expected that
the "stale" version of the resource remain available at this
time while the new one is generated.

The dogpile lock can also provide a mutex to the creation 
function itself, so that the creation function can perform
certain tasks only after all "stale reader" threads have finished.
The example of this is when the creation function has prepared a new
datafile to replace the old one, and would like to switch in the
"new" file only when other threads have finished using it.   

To enable this feature, use :class:`.SyncReaderDogpile`.
Then use :meth:`.SyncReaderDogpile.acquire_write_lock` for the critical section
where readers should be blocked::
    
    from dogpile import SyncReaderDogpile
    
    dogpile = SyncReaderDogpile(3600)

    def some_creation_function():
        create_expensive_datafile()
        with dogpile.acquire_write_lock():
            replace_old_datafile_with_new()

"""
try:
    import threading
    import thread
except ImportError:
    import dummy_threading as threading
    import dummy_thread as thread

import time
import logging
from readwrite_lock import ReadWriteMutex

log = logging.getLogger(__name__)

class Dogpile(object):
    """Dogpile class.   
    
    :param expiretime: Expiration time in seconds.
    
    """
    def __init__(self, expiretime):
        self.dogpilelock = threading.Lock()
        self.expiretime = expiretime
        self.createdtime = -1

    def acquire(self, creator):
        """Acquire the lock, returning a context manager.
        
        :param creator: Creation function, used if this thread
         is chosen to create a new value.
         
        """
        dogpile = self
        class Lock(object):
            def __enter__(self):
                dogpile._enter(creator)
            def __exit__(self, type, value, traceback):
                dogpile._exit()
        return Lock()

    @property
    def is_expired(self):
        """Return true if the expiration time is reached, or no value is available."""

        return not self.has_value or \
            time.time() - self.createdtime > self.expiretime

    @property
    def has_value(self):
        """Return true if the creation function has proceeded at least once."""
        return self.createdtime > 0

    def _enter(self, creator):
        if not self.is_expired:
            return

        has_createlock = False
        if self.has_value:
            if not self.dogpilelock.acquire(False):
                log.debug("dogpile entering block while another thread does the create")
                return
            log.debug("dogpile create lock acquired")
            has_createlock = True

        if not has_createlock:
            log.debug("no value, waiting for create lock")
            self.dogpilelock.acquire()
            log.debug("waited for create lock")

        try:
            # see if someone created the value already
            if not self.is_expired:
                return

            log.debug("Calling creation function")
            creator()
            self.createdtime = time.time()
        finally:
            self.dogpilelock.release()
            log.debug("Released creation lock")

    def _exit(self):
        pass

class SyncReaderDogpile(Dogpile):
    def __init__(self, expiretime):
        super(SyncReaderDogpile, self).__init__(expiretime)
        self.readwritelock = ReadWriteMutex()

    def acquire_write_lock(self):
        dogpile = self
        class Lock(object):
            def __enter__(self):
                dogpile.readwritelock.acquire_write_lock()
            def __exit__(self, type, value, traceback):
                dogpile.readwritelock.release_write_lock()
        return Lock()


    def _enter(self, creator):
        super(SyncReaderDogpile, self)._enter(creator)
        self.readwritelock.acquire_read_lock()

    def _exit(self):
        self.readwritelock.release_read_lock()
