===========
Usage Guide
===========

At its core, dogpile.core provides a locking interface around a "value creation" function.

The interface supports several levels of usage, starting from
one that is very rudimentary, then providing more intricate 
usage patterns to deal with certain scenarios.  The documentation here will attempt to 
provide examples that use successively more and more of these features, as 
we approach how a fully featured caching system might be constructed around
dogpile.core.

Do I Need to Learn the dogpile.core API Directly?
=================================================

It's anticipated that most users of dogpile.core will be using it indirectly via the
`dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_ caching
front-end.  If you fall into this category, then the short answer is no.

dogpile.core provides core internals to the 
`dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_
package, which provides a simple-to-use caching API, rudimental
backends for Memcached and others, and easy hooks to add new backends.  
Users of dogpile.cache
don't need to know or access dogpile.core's APIs directly, though a rough understanding
the general idea is always helpful.

Using the core dogpile.core APIs described here directly implies you're building your own 
resource-usage system outside, or in addition to, the one 
`dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_ provides.

Rudimentary Usage
==================

A simple example::

    from dogpile.core import Dogpile

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

Using a Value Function with a Cache Backend
=============================================

The dogpile lock includes a more intricate mode of usage to optimize the
usage of a cache like Memcached.   The difficulties :class:`.Dogpile` addresses
in this mode are:

* Values can disappear from the cache at any time, before our expiration
  time is reached. :class:`.Dogpile` needs to be made aware of this and possibly 
  call the creation function ahead of schedule.
* There's no function in a Memcached-like system to "check" for a key without 
  actually retrieving it.  If we need to "check" for a key each time, 
  we'd like to use that value instead of calling it twice.
* If we did end up generating the value on this get, we should return 
  that value instead of doing a cache round-trip.

To use this mode, the steps are as follows:

* Create the :class:`.Dogpile` lock with ``init=True``, to skip the initial
  "force" of the creation function.   This is assuming you'd like to
  rely upon the "check the value" function for the initial generation.
  Leave it at False if you'd like the application to regenerate the
  value unconditionally when the :class:`.Dogpile` lock is first created
  (i.e. typically application startup).
* The "creation" function should return the value it creates.
* An additional "getter" function is passed to ``acquire()`` which
  should return the value to be passed to the context block.  If
  the value isn't available, raise ``NeedRegenerationException``.

Example::

    from dogpile.core import Dogpile, NeedRegenerationException

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

.. _caching_decorator:

Using dogpile.core for Caching
===============================

dogpile.core is part of an effort to "break up" the Beaker
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

    from dogpile.core import Dogpile, NeedRegenerationException

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

The :class:`.Dogpile` lock will ensure that only one thread at a time performs ``slow_database.lookup()``,
and only every 3600 seconds, unless Memcached has removed the value in which case it will
be called again as needed.

In particular, dogpile.core's system allows us to call the memcached get() function at most
once per access, instead of Beaker's system which calls it twice, and doesn't make us call
get() when we just created the value.

.. _scaling_on_keys:

Scaling dogpile.core against Many Keys
=======================================

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
``value_fn`` we used earlier.  ``value_and_created_fn`` expects a function that will return a tuple
of ``(value, created_at)``, where it's assumed both have been retrieved from
the cache backend::

    import pylibmc
    import time
    from dogpile.core import Dogpile, NeedRegenerationException, NameRegistry

    mc_pool = pylibmc.ThreadMappedPool(pylibmc.Client("localhost"))

    def create_dogpile(key, expiration_time):
        return Dogpile(expiration_time)

    dogpile_registry = NameRegistry(create_dogpile)

    def get_or_create(key, expiration_time, creation_function):
        def get_value():
             with mc_pool.reserve() as mc:
                value_plus_time = mc.get(key)
                if value_plus_time is None:
                    raise NeedRegenerationException()
                # return a tuple
                # (value, createdtime)
                return value_plus_time

        def gen_cached():
            value = creation_function()
            with mc_pool.reserve() as mc:
                # create a tuple
                # (value, createdtime)
                value_plus_time = (value, time.time())
                mc.put(key, value_plus_time)
            return value_plus_time

        dogpile = dogpile_registry.get(key, expiration_time)

        with dogpile.acquire(gen_cached, value_and_created_fn=get_value) as value:
            return value


Stepping through the above code:

* After the imports, we set up the memcached backend using the ``pylibmc`` library's
  recommended pattern for thread-safe access.
* We create a Python function that will, given a cache key and an expiration time,
  produce a :class:`.Dogpile` object which will produce the dogpile mutex on an
  as-needed basis.   The function here doesn't actually need the key, even though
  the :class:`.NameRegistry` will be passing it in.  Later, we'll see the scenario
  for which we'll need this value.
* We construct a :class:`.NameRegistry`, using our dogpile creator function, that
  will generate for us new :class:`.Dogpile` locks for individual keys as needed.
* We define the ``get_or_create()`` function.  This function will accept the cache
  key, an expiration time value, and a function that is used to create a new value 
  if one does not exist or the current value is expired.
* The ``get_or_create()`` function defines two callables, ``get_value()`` and 
  ``gen_cached()``.   These two functions are exactly analogous to the the
  functions of the same name in :ref:`caching_decorator` - ``get_value()``
  retrieves the value from the cache, raising :class:`.NeedRegenerationException`
  if not present; ``gen_cached()`` calls the creation function to generate a new 
  value, stores it in the cache, and returns it.  The only difference here is that
  instead of storing and retrieving the value alone from the cache, the value is 
  stored along with its creation time; when we make a new value, we set this
  to ``time.time()``.  While the value and creation time pair are stored here 
  as a tuple, it doesn't actually matter how the two are persisted; 
  only that the tuple value is returned from both functions.
* We acquire a new or existing :class:`.Dogpile` object from the registry using
  :meth:`.NameRegistry.get`.   We pass the identifying key as well as the expiration
  time.   A new :class:`.Dogpile` is created for the given key if one does not 
  exist.  If a :class:`.Dogpile` lock already exists in memory for the given key,
  we get that one back.
* We then call :meth:`.Dogpile.acquire` as we did in the previous cache examples,
  except we use the ``value_and_created_fn`` keyword for our ``get_value()`` 
  function.  :class:`.Dogpile` uses the "created time" value we pull from our 
  cache to determine when the value was last created.

An example usage of the completed function::

    import urllib2

    def get_some_value(key):
        """retrieve a datafile from a slow site based on the given key."""
        def get_data():
            return urllib2.urlopen(
                        "http://someslowsite.com/some_important_datafile_%s.json" % key
                    ).read()
        return get_or_create(key, 3600, get_data)

    my_data = get_some_value("somekey")

Using a File or Distributed Lock with Dogpile
==============================================


The final twist on the caching pattern is to fix the issue of the Dogpile mutex
itself being local to the current process.   When a handful of threads all go 
to access some key in our cache, they will access the same :class:`.Dogpile` object
which internally can synchronize their activity using a Python ``threading.Lock``.
But in this example we're talking to a Memcached cache.  What if we have many 
servers which all access this cache?  We'd like all of these servers to coordinate
together so that we don't just prevent the dogpile problem within a single process,
we prevent it across all servers.

To accomplish this, we need an object that can coordinate processes.   In this example
we'll use a file-based lock as provided by the `lockfile <http://pypi.python.org/pypi/lockfile>`_
package, which uses a unix-symlink concept to provide a filesystem-level lock (which also
has been made threadsafe).  Another strategy may base itself directly off the Unix ``os.flock()``
call, and still another approach is to lock within Memcached itself, using a recipe 
such as that described at `Using Memcached as a Distributed Locking Service <http://www.regexprn.com/2010/05/using-memcached-as-distributed-locking.html>`_.
The type of lock chosen here is based on a tradeoff between global availability
and reliable performance.  The file-based lock will perform more reliably than the
memcached lock, but may be difficult to make accessible to multiple servers (with NFS 
being the most likely option, which would eliminate the possibility of the ``os.flock()``
call).  The memcached lock on the other hand will provide the perfect scope, being available
from the same memcached server that the cached value itself comes from; however the lock may
vanish in some cases, which means we still could get a cache-regeneration pileup in that case.

What all of these locking schemes have in common is that unlike the Python ``threading.Lock``
object, they all need access to an actual key which acts as the symbol that all processes
will coordinate upon.   This is where the ``key`` argument to our ``create_dogpile()``
function introduced in :ref:`scaling_on_keys` comes in.   The example can remain
the same, except for the changes below to just that function::

    import lockfile
    import os
    from hashlib import sha1

    # ... other imports and setup from the previous example

    def create_dogpile(key, expiration_time):
        lock_path = os.path.join("/tmp", "%s.lock" % sha1(key).hexdigest())
        return Dogpile(
                    expiration_time,
                    lock=lockfile.FileLock(path)
                    )

    # ... everything else from the previous example

Where above,the only change is the ``lock`` argument passed to the constructor of
:class:`.Dogpile`.   For a given key "some_key", we generate a hex digest of it
first as a quick way to remove any filesystem-unfriendly characters, we then use
``lockfile.FileLock()`` to create a lock against the file 
``/tmp/53def077a4264bd3183d4eb21b1f56f883e1b572.lock``.   Any number of :class:`.Dogpile`
objects in various processes will now coordinate with each other, using this common 
filename as the "baton" against which creation of a new value proceeds.

Locking the "write" phase against the "readers"
================================================

A less prominent feature of Dogpile ported from Beaker is the
ability to provide a mutex against the actual resource being read
and created, so that the creation function can perform
certain tasks only after all reader threads have finished.
The example of this is when the creation function has prepared a new
datafile to replace the old one, and would like to switch in the
new file only when other threads have finished using it.

To enable this feature, use :class:`.SyncReaderDogpile`.
:meth:`.SyncReaderDogpile.acquire_write_lock` then provides a safe-write lock
for the critical section where readers should be blocked::


    from dogpile.core import SyncReaderDogpile

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

Note that the :class:`.SyncReaderDogpile` approach is useful
for when working with a resource that itself does not support concurent
access while being written, namely flat files, possibly some forms of DBM file.
It is **not** needed when dealing with a datasource that already
provides a high level of concurrency, such as a relational database,
Memcached, or NoSQL store.   Currently, the :class:`.SyncReaderDogpile` object
only synchronizes within the current process among multiple threads;
it won't at this time protect from concurrent access by multiple 
processes.   Beaker did support this behavior however using lock files,
and this functionality may be re-added in a future release.


