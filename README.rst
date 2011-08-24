A "dogpile" lock, one which allows a single thread to generate
an expensive resource while other threads use the "old" value, until the
"new" value is ready.

Dogpile is basically the locking code extracted from the
Beaker package, for simple and generic usage.

Usage::

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
block then proceeds.   Concurrent threads which 
call ``Dogpile.acquire()`` during this initial period
will block until ``some_creation_function()`` completes.

Once the creation function has completed successfully,
new calls to ``Dogpile.acquire()`` will route a single
thread into new calls of ``some_creation_function()`` 
each time the expiration time is reached.  Concurrent threads
which call ``Dogpile.acquire()`` during this period will
fall through, and not be blocked.  It is expected that
the "stale" version of the resource remain available at this
time while the new one is generated.

The dogpile lock can also provide a mutex to the creation 
function itself, so that the creation function can perform
certain tasks only after all "stale reader" threads have finished.
The example of this is when the creation function has prepared a new
datafile to replace the old one, and would like to switch in the
"new" file only when other threads have finished using it.   

To enable this feature, use `SyncReaderDogpile``.
Then use ``SyncReaderDogpile.acquire_write_lock()`` for the critical section
where readers should be blocked::

    from dogpile import SyncReaderDogpile

    dogpile = SyncReaderDogpile(3600)

    def some_creation_function():
        create_expensive_datafile()
        with dogpile.acquire_write_lock():
            replace_old_datafile_with_new()
