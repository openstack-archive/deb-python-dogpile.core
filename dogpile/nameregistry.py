from util import threading
import weakref

class NameRegistry(object):
    """Generates and return an object, keeping it as a
    singleton for a certain identifier for as long as its 
    strongly referenced.
    
    e.g.::
    
        class MyFoo(object):
            "some important object."

        registry = NameRegistry(MyFoo)

        # thread 1:
        my_foo = registry.get("foo1")
        
        # thread 2
        my_foo = registry.get("foo1")
    
    Above, "my_foo" in both thread #1 and #2 will
    be *the same object*.
    
    When thread 1 and thread 2 both complete or 
    otherwise delete references to "my_foo", the
    object is *removed* from the NameRegistry as 
    a result of Python garbage collection.
    
    """
    _locks = weakref.WeakValueDictionary()
    _mutex = threading.RLock()

    def __init__(self, creator):
        self._values = weakref.WeakValueDictionary()
        self._mutex = threading.RLock()
        self.creator = creator

    def get(self, identifier, *args, **kw):
        try:
            if identifier in self._values:
                return self._values[identifier]
            else:
                return self._sync_get(identifier, *args, **kw)
        except KeyError:
            return self._sync_get(identifier, *args, **kw)

    def _sync_get(self, identifier, *args, **kw):
        self._mutex.acquire()
        try:
            try:
                if identifier in self._values:
                    return self._values[identifier]
                else:
                    self._values[identifier] = value = self.creator(identifier, *args, **kw)
                    return value
            except KeyError:
                self._values[identifier] = value = self.creator(identifier, *args, **kw)
                return value
        finally:
            self._mutex.release()
