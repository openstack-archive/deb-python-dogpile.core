dogpile
========
A "dogpile" lock, one which allows a single thread to generate
an expensive resource while other threads use the "old" value, until the
"new" value is ready.

Dogpile is basically the locking code extracted from the
Beaker package, for simple and generic usage.

Usage
-----

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
when ``Dogpile.acquire()`` is first called.  The 
remainder of the ``with`` block then proceeds.   Concurrent threads which 
call ``Dogpile.acquire()`` during this initial period
will be blocked until ``some_creation_function()`` completes.

Once the creation function has completed successfully the first time,
new calls to ``Dogpile.acquire()`` will call ``some_creation_function()`` 
each time the "expiretime" has been reached, allowing only a single
thread to call the function.  Concurrent threads
which call ``Dogpile.acquire()`` during this period will
fall through, and not be blocked.  It is expected that
the "stale" version of the resource remain available at this
time while the new one is generated.

Using a Value Function with a Memcached-like Cache
---------------------------------------------------

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

Note that get_value_from_cache() should not raise NeedRegenerationException
a second time directly after create_and_cache_value() has been called.

Locking the "write" phase against the "readers"
------------------------------------------------

The dogpile lock can provide a mutex to the creation 
function itself, so that the creation function can perform
certain tasks only after all "stale reader" threads have finished.
The example of this is when the creation function has prepared a new
datafile to replace the old one, and would like to switch in the
"new" file only when other threads have finished using it.

To enable this feature, use ``SyncReaderDogpile()``.
``SyncReaderDogpile.acquire_write_lock()`` then provides a safe-write lock
for the critical section where readers should be blocked::

    from dogpile import SyncReaderDogpile

    dogpile = SyncReaderDogpile(3600)

    def some_creation_function():
        create_expensive_datafile()
        with dogpile.acquire_write_lock():
            replace_old_datafile_with_new()

Using Dogpile for Caching
--------------------------

Dogpile is part of an effort to "break up" the Beaker
package into smaller, simpler components (which also work better). Here, we
illustrate how to replicate Beaker's "cache decoration"
function, to decorate any function and store the value in
Memcached::

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

Development Status
-------------------

Please note Dogpile is new and has only had minimal production usage !   Comments
and improvements are welcome.  Since this is concurrency-oriented code, please review
the source and let me know about potential issues.   As always, **use at your own risk!**




