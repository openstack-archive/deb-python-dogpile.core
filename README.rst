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

Dogpile is at the core of the `dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_ package
which provides for a basic cache API and sample backends based on the dogpile concept.

Development Status
-------------------

Please note Dogpile is new and has only had minimal production usage !   Comments
and improvements are welcome.  Since this is concurrency-oriented code, please review
the source and let me know about potential issues.   As always, **use at your own risk!**




