from .util import threading
import time
import logging
from .readwrite_lock import ReadWriteMutex

log = logging.getLogger(__name__)


class NeedRegenerationException(Exception):
    """An exception that when raised in the 'with' block, 
    forces the 'has_value' flag to False and incurs a 
    regeneration of the value.
    
    """

NOT_REGENERATED = object()

class Dogpile(object):
    """Dogpile lock class.
    
    Provides an interface around an arbitrary mutex 
    that allows one thread/process to be elected as 
    the creator of a new value, while other threads/processes 
    continue to return the previous version 
    of that value.

    :param expiretime: Expiration time in seconds.  Set to
     ``None`` for never expires.
    :param init: if True, set the 'createdtime' to the
     current time.
    :param lock: a mutex object that provides
     ``acquire()`` and ``release()`` methods.
        
    """
    def __init__(self, expiretime, init=False, lock=None):
        """Construct a new :class:`.Dogpile`.

        """
        if lock:
            self.dogpilelock = lock
        else:
            self.dogpilelock = threading.Lock()

        self.expiretime = expiretime
        if init:
            self.createdtime = time.time()

    createdtime = -1
    """The last known 'creation time' of the value,
    stored as an epoch (i.e. from ``time.time()``).

    If the value here is -1, it is assumed the value
    should recreate immediately.
    
    """

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
         previous one left off.   
         
        """
        dogpile = self

        class Lock(object):
            def __enter__(self):
                return dogpile._enter(creator, value_fn, 
                                    value_and_created_fn)

            def __exit__(self, type, value, traceback):
                dogpile._exit()
        return Lock()

    @property
    def is_expired(self):
        """Return true if the expiration time is reached, or no 
        value is available."""

        return not self.has_value or \
            (
                self.expiretime is not None and 
                time.time() - self.createdtime > self.expiretime
            )

    @property
    def has_value(self):
        """Return true if the creation function has proceeded 
        at least once."""
        return self.createdtime > 0

    def _enter(self, creator, value_fn=None, value_and_created_fn=None):
        if value_and_created_fn:
            value_fn = value_and_created_fn

        if not value_fn:
            return self._enter_create(creator)

        try:
            value = value_fn()
            if value_and_created_fn:
                value, self.createdtime = value
        except NeedRegenerationException:
            log.debug("NeedRegenerationException")
            self.createdtime = -1
            value = NOT_REGENERATED

        generated = self._enter_create(creator)

        if generated is not NOT_REGENERATED:
            if value_and_created_fn:
                generated, self.createdtime = generated
            return generated
        elif value is NOT_REGENERATED:
            try:
                if value_and_created_fn:
                    value, self.createdtime = value_fn()
                else:
                    value = value_fn()
                return value
            except NeedRegenerationException:
                raise Exception("Generation function should "
                            "have just been called by a concurrent "
                            "thread.")
        else:
            return value

    def _enter_create(self, creator):

        if not self.is_expired:
            return NOT_REGENERATED

        if self.has_value:
            if not self.dogpilelock.acquire(False):
                log.debug("creation function in progress "
                            "elsewhere, returning")
                return NOT_REGENERATED
        else:
            log.debug("no value, waiting for create lock")
            self.dogpilelock.acquire()
        try:
            log.debug("value creation lock %r acquired" % self.dogpilelock)

            # see if someone created the value already
            if not self.is_expired:
                log.debug("value already present")
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
    """Provide a read-write lock function on top of the :class:`.Dogpile`
    class.
    
    """
    def __init__(self, *args, **kw):
        super(SyncReaderDogpile, self).__init__(*args, **kw)
        self.readwritelock = ReadWriteMutex()

    def acquire_write_lock(self):
        """Return the "write" lock context manager.
        
        This will provide a section that is mutexed against
        all readers/writers for the dogpile-maintained value.
        
        """

        dogpile = self
        class Lock(object):
            def __enter__(self):
                dogpile.readwritelock.acquire_write_lock()
            def __exit__(self, type, value, traceback):
                dogpile.readwritelock.release_write_lock()
        return Lock()


    def _enter(self, *arg, **kw):
        value = super(SyncReaderDogpile, self)._enter(*arg, **kw)
        self.readwritelock.acquire_read_lock()
        return value

    def _exit(self):
        self.readwritelock.release_read_lock()
