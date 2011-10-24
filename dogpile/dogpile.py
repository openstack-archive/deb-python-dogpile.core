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
from util import thread, threading
import time
import logging
from readwrite_lock import ReadWriteMutex
from nameregistry import NameRegistry

log = logging.getLogger(__name__)


class NeedRegenerationException(Exception):
    """An exception that when raised in the 'with' block, forces
    the 'has_value' flag to False and incurs a regeneration of the value.
    
    """

NOT_REGENERATED = object()

class Dogpile(object):
    """Dogpile class.   
    
    :param expiretime: Expiration time in seconds.
    
    """
    def __init__(self, expiretime, init=False):
        self.dogpilelock = threading.Lock()

        self.expiretime = expiretime
        if init:
            self.createdtime = time.time()
        else:
            self.createdtime = -1

    @clasmethod
    def registry(cls, *arg, **kw):
        """Return a name-based registry of :class:`.Dogpile` objects.
        
        The registry is an instance of :class:`.NameRegistry`,
        and calling its ``get()`` method with an identifying 
        key (anything hashable) will construct a new :class:`.Dogpile`
        object, keyed to that key.  Subsequent usages will return
        the same :class:`.Dogpile` object for as long as the 
        object remains in scope.

        The given arguments are passed along to the underlying
        constructor of the :class:`.Dogpile` class.

        """
        return NameRegistry(lambda identifier: cls(*arg, **kw))

    def acquire(self, creator, 
                        value_fn=None, 
                        value_and_created_fn=None):
        """Acquire the lock, returning a context manager.
        
        :param creator: Creation function, used if this thread
         is chosen to create a new value.
         
        :param value_fn: Optional function that returns
         the value from some datasource.  Will be returned
         if regeneration is not needed.

        :param value_and_created_fn: Like value_fn, but returns a tuple
         of (value, createdtime).  The returned createdtime 
         will replace the "createdtime" value on this dogpile
         lock.   This option removes the need for the dogpile lock
         itself to remain persistent across usages; another 
         dogpile can come along later and pick up where the
         previous one left off.   Should be used in conjunction
         with a :class:`.NameRegistry`.
         
        """
        dogpile = self

        if value_and_created_fn:
            value_fn = value_and_created_fn

        class Lock(object):
            if value_fn:
                def __enter__(self):
                    try:
                        value = value_fn()
                        if value_and_created_fn:
                            value, dogpile.createdtime = value
                    except NeedRegenerationException:
                        dogpile.createdtime = -1
                        value = NOT_REGENERATED

                    generated = dogpile._enter(creator)

                    if generated is not NOT_REGENERATED:
                        return generated
                    elif value is NOT_REGENERATED:
                        try:
                            return value_fn()
                        except NeedRegenerationException:
                            raise Exception("Generation function should "
                                        "have just been called by a concurrent "
                                        "thread.")
                    else:
                        return value
            else:
                def __enter__(self):
                    return dogpile._enter(creator)

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
            return NOT_REGENERATED

        if self.has_value:
            if not self.dogpilelock.acquire(False):
                log.debug("dogpile entering block while another "
                                "thread does the create")
                return NOT_REGENERATED
        else:
            log.debug("no value, waiting for create lock")
            self.dogpilelock.acquire()
        try:
            log.debug("value creation lock acquired")

            # see if someone created the value already
            if not self.is_expired:
                return NOT_REGENERATED

            log.debug("Calling creation function")
            created = creator()
            self.createdtime = time.time()
            return created
        finally:
            self.dogpilelock.release()
            log.debug("Released creation lock")

    def _exit(self):
        pass

class SyncReaderDogpile(Dogpile):
    def __init__(self, *args, **kw):
        super(SyncReaderDogpile, self).__init__(*args, **kw)
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
        value = super(SyncReaderDogpile, self)._enter(creator)
        self.readwritelock.acquire_read_lock()
        return value

    def _exit(self):
        self.readwritelock.release_read_lock()
