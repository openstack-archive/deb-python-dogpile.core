Introduction
============

At its core, Dogpile provides a locking interface around a "value creation" function.

The interface supports several levels of usage, starting from
one that is very rudimentary, then providing more intricate 
usage patterns to deal with certain scenarios.  The documentation here will attempt to 
provide examples that use successively more and more of these features, as 
we approach how a fully featured caching system might be constructed around
Dogpile.

Note that when using the `dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_
package, the constructs here provide the internal implementation for that system,
and users of that system don't need to access these APIs directly (though understanding
the general patterns is a terrific idea in any case).
Using the core Dogpile APIs described here directly implies you're building your own 
resource-usage system outside, or in addition to, the one 
`dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_ provides.

Usage
=====

A simple example::

    from dogpile import Dogpile

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
remainder of the ``with`` block then proceeds.   Concurrent threads which 
call :meth:`.Dogpile.acquire` during this initial period
will be blocked until ``some_creation_function()`` completes.

Once the creation function has completed successfully the first time,
new calls to :meth:`.Dogpile.acquire` will call ``some_creation_function()`` 
each time the "expiretime" has been reached, allowing only a single
thread to call the function.  Concurrent threads
which call :meth:`.Dogpile.acquire` during this period will
fall through, and not be blocked.  It is expected that
the "stale" version of the resource remain available at this
time while the new one is generated.

By default, :class:`.Dogpile` uses Python's ``threading.Lock()`` 
to synchronize among threads within a process.  This can 
be altered to support any kind of locking as we'll see in a 
later section.

Locking the "write" phase against the "readers"
------------------------------------------------

The dogpile lock can provide a mutex to the creation 
function itself, so that the creation function can perform
certain tasks only after all "stale reader" threads have finished.
The example of this is when the creation function has prepared a new
datafile to replace the old one, and would like to switch in the
"new" file only when other threads have finished using it.

To enable this feature, use :class:`.SyncReaderDogpile`.
:meth:`.SyncReaderDogpile.acquire_write_lock` then provides a safe-write lock
for the critical section where readers should be blocked::


    from dogpile import SyncReaderDogpile

    dogpile = SyncReaderDogpile(3600)

    def some_creation_function(dogpile):
        create_expensive_datafile()
        with dogpile.acquire_write_lock():
            replace_old_datafile_with_new()

    # usage:
    with dogpile.acquire(some_creation_function):
        read_datafile()

With the above pattern, :class:`.SyncReaderDogpile` will
allow concurrent readers to read from the current version 
of the datafile as 
the ``create_expensive_datafile()`` function proceeds with its
job of generating the information for a new version.  
When the data is ready to be written,  the 
:meth:`.SyncReaderDogpile.acquire_write_lock` call will 
block until all current readers of the datafile have completed
(that is, they've finished their own :meth:`.Dogpile.acquire` 
blocks).   The ``some_creation_function()`` function
then proceeds, as new readers are blocked until
this function finishes its work of 
rewriting the datafile.

Using a Value Function with a Cache Backend
-------------------------------------------

The dogpile lock includes a more intricate mode of usage to optimize the
usage of a cache like Memcached.   The difficulties Dogpile addresses
in this mode are:

* Values can disappear from the cache at any time, before our expiration
  time is reached. Dogpile needs to be made aware of this and possibly 
  call the creation function ahead of schedule.
* There's no function in a Memcached-like system to "check" for a key without 
  actually retrieving it.  If we need to "check" for a key each time, 
  we'd like to use that value instead of calling it twice.
* If we did end up generating the value on this get, we should return 
  that value instead of doing a cache round-trip.

To use this mode, the steps are as follows:

* Create the Dogpile lock with ``init=True``, to skip the initial
  "force" of the creation function.   This is assuming you'd like to
  rely upon the "check the value" function for the initial generation.
  Leave it at False if you'd like the application to regenerate the
  value unconditionally when the dogpile lock is first created
  (i.e. typically application startup).
* The "creation" function should return the value it creates.
* An additional "getter" function is passed to ``acquire()`` which
  should return the value to be passed to the context block.  If
  the value isn't available, raise ``NeedRegenerationException``.

Example::

    from dogpile import Dogpile, NeedRegenerationException

    def get_value_from_cache():
        value = my_cache.get("some key")
        if value is None:
            raise NeedRegenerationException()
        return value

    def create_and_cache_value():
        value = my_expensive_resource.create_value()
        my_cache.put("some key", value)
        return value

    dogpile = Dogpile(3600, init=True)

    with dogpile.acquire(create_and_cache_value, get_value_from_cache) as value:
        return value

Note that ``get_value_from_cache()`` should not raise :class:`.NeedRegenerationException`
a second time directly after ``create_and_cache_value()`` has been called.

Using Dogpile for Caching
--------------------------

Dogpile is part of an effort to "break up" the Beaker
package into smaller, simpler components (which also work better). Here, we
illustrate how to approximate Beaker's "cache decoration"
function, to decorate any function and store the value in
Memcached.  We create a Python decorator function called ``cached()`` which
will provide caching for the output of a single function.  It's given 
the "key" which we'd like to use in Memcached, and internally it makes
usage of its own :class:`.Dogpile` object that is dedicated to managing
this one function/key::

    import pylibmc
    mc_pool = pylibmc.ThreadMappedPool(pylibmc.Client("localhost"))

    from dogpile import Dogpile, NeedRegenerationException

    def cached(key, expiration_time):
        """A decorator that will cache the return value of a function
        in memcached given a key."""

        def get_value():
             with mc_pool.reserve() as mc:
                value = mc.get(key)
                if value is None:
                    raise NeedRegenerationException()
                return value

        dogpile = Dogpile(expiration_time, init=True)

        def decorate(fn):
            def gen_cached():
                value = fn()
                with mc_pool.reserve() as mc:
                    mc.put(key, value)
                return value

            def invoke():
                with dogpile.acquire(gen_cached, get_value) as value:
                    return value
            return invoke

        return decorate

Above we can decorate any function as::

    @cached("some key", 3600)
    def generate_my_expensive_value():
        return slow_database.lookup("stuff")

The Dogpile lock will ensure that only one thread at a time performs ``slow_database.lookup()``,
and only every 3600 seconds, unless Memcached has removed the value in which case it will
be called again as needed.

In particular, Dogpile's system allows us to call the memcached get() function at most
once per access, instead of Beaker's system which calls it twice, and doesn't make us call
get() when we just created the value.

Scaling Dogpile against Many Keys
----------------------------------

The patterns so far have illustrated how to use a single, persistently held
:class:`.Dogpile` object which maintains a thread-based lock for the lifespan
of some particular value.  The :class:`.Dogpile` also is responsible for
maintaining the last known "creation time" of the value; this is available
from a given :class:`.Dogpile` object from the :attr:`.Dogpile.createdtime`
attribute.

For an application that may deal with an arbitrary
number of cache keys retrieved from a remote service, this approach must be 
revised so that we don't need to store a :class:`.Dogpile` object for every
possible key in our application's memory.

The two challenges here are:

* We need to create new :class:`.Dogpile` objects as needed, ideally
  sharing the object for a given key with all concurrent threads,
  but then not hold onto it afterwards.
* Since we aren't holding the :class:`.Dogpile` persistently, we 
  need to store the last known "creation time" of the value somewhere
  else, i.e. in the cache itself, and ensure :class:`.Dogpile` uses 
  it.

The approach is another one derived from Beaker, where we will use a *registry*
that can provide a unique :class:`.Dogpile` object given a particular key,
ensuring that all concurrent threads use the same object, but then releasing
the object to the Python garbage collector when this usage is complete.
The :class:`.NameRegistry` object provides this functionality, again
constructed around the notion of a creation function that is only invoked
as needed.   We also will instruct the :meth:`.Dogpile.acquire` method
to use a "creation time" value that we retrieve from the cache, via
the ``value_and_created_fn`` parameter, which supercedes the
``value_fn`` we used earlier to expect a function that will return a tuple
of ``(value, created_at)``::

    import pylibmc
    import pickle
    import os
    import time
    import sha1
    from dogpile import Dogpile, NeedRegenerationException, NameRegistry

    mc_pool = pylibmc.ThreadMappedPool(pylibmc.Client("localhost"))

    def create_dogpile(key, expiration_time):
        return Dogpile(expiration_time)

    dogpile_registry = NameRegistry(create_dogpile)

    def cache(expiration_time):

        def get_or_create(key):
            def get_value():
                 with mc_pool.reserve() as mc:
                    value = mc.get(key)
                    if value is None:
                        raise NeedRegenerationException()
                    # deserialize a tuple
                    # (value, createdtime)
                    return pickle.loads(value)

            dogpile = dogpile_registry.get(key, expiration_time)

            def gen_cached():
                value = fn()
                with mc_pool.reserve() as mc:
                    # serialize a tuple
                    # (value, createdtime)
                    value = (value, time.time())
                    mc.put(mangled_key, pickle.dumps(value))
                return value

            with dogpile.acquire(gen_cached, value_and_created_fn=get_value) as value:
                return value

        return get_or_create

Above, we use ``Dogpile.registry()`` to create a name-based "registry" of ``Dogpile``
objects.  This object will provide to us a ``Dogpile`` object that's 
unique on a certain name (or any hashable object) when we call the ``get()`` method.  
When all usages of that name are complete, the ``Dogpile``
object falls out of scope.   This way, an application can handle millions of keys
without needing to have millions of ``Dogpile`` objects persistently resident in memory.

The next part of the approach here is that we'll tell Dogpile that we'll give it 
the "creation time" that we'll store in our
cache - we do this using the ``value_and_created_fn`` argument, which assumes we'll
be storing and loading the value as a tuple of (value, createdtime).  The creation time
should always be calculated via ``time.time()``.   The ``acquire()`` function
returns the "value" portion of the tuple to us and uses the 
"createdtime" portion to determine if the value is expired.


Using a File or Distributed Lock with Dogpile
----------------------------------------------

The example below will use a file-based mutex using `lockfile <http://pypi.python.org/pypi/lockfile>`_.
