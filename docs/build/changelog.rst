==========
Changelog
==========

.. changelog::
    :version: 0.4.1
    :released: Sat Jan 19 2013

    .. change::
        :pullreq: 2

      An "async creator" function can be specified to
      :class:`.Lock` which allows the "creation" function
      to be called asynchronously or be subsituted for
      another asynchronous creation scheme.  Courtesy
      Ralph Bean.

.. changelog::
    :version: 0.4.0
    :released: Tue Oct 30 2012

    .. change::

      reworked Dogpile's API into a new object called Lock.
      Lock presents just one set of arguments for locking within
      one constructor call, and provides the "comprehensive" caching
      pattern that is what's desired in the vast majority of cases.
      The Dogpile class is now legacy, and
      builds its various usage patterns on top of Lock.

    .. change::
        :tags:
        :tickets: 1

      Fixed the dependency on storing "creationtime" locally in memory;
      this caused dogpile pileups for a missing cache value when used in multiple-process
      environments.  The new Lock object now checks the value_and_created_fn()
      an extra time within the "lock acquired" phase so that multiple writers
      who entered the block don't rely upon a memory-only version of creation
      time.


.. changelog::
    :version: 0.3.3
    :released: Tue Sep 25 2012

    .. change::
        :tags:
        :tickets:

      repair setup.py so that tests don't install,
      courtesy Ben Hayden.

.. changelog::
    :version: 0.3.2
    :released: Wed Jun 13 2012

    .. change::
        :tags:
        :tickets:

      upgrade to beta.

.. changelog::
    :version: 0.3.1
    :released: Sun Apr 15 2012

    .. change::
        :tags:
        :tickets:

      py3k compatibility is in-place now, no
      2to3 needed.

.. changelog::
    :version: 0.3.0
    :released: Sat Apr 14 2012

    .. change::
        :tags:
        :tickets:

      Renamed the project again - to dogpile.core.
      Package has been reorganized so that "dogpile"
      is a pure namespace package.  The base dogpile
      features are now in "dogpile.core".


.. changelog::
    :version: 0.2.2
    :released: Fri Mar 30 2012

    .. change::
        :tags:
        :tickets:

      expire time of None means "never expire".

.. changelog::
    :version: 0.2.1
    :released: Fri Dec 23 2011

    .. change::
        :tags:
        :tickets:

      Add new "nameregistry" helper.  Another fixture
      derived from Beaker, this allows the ad-hoc creation of
      a new Dogpile lock based on a name, where all other
      threads calling that name at the same time will get
      the same Dogpile lock.  Allows any number of
      logical "dogpile" actions to carry on concurrently
      without any memory taken up outside of those operations.

    .. change::
        :tags:
        :tickets:

      To support the use case supported by nameregistry, added
      value_and_created_fn to dogpile.acquire().  The idea
      is that the value_and_created_fn can return
      (value, createdtime), so that the creation time of the
      value can come from the cache, thus eliminating the
      need for the dogpile lock to hang around persistently.

.. changelog::
    :version: 0.2.0
    :released: Sun Oct 23 2011

    .. change::
        :tags:
        :tickets:

      change name to lowercase "dogpile".

.. changelog::
    :version: 0.1.0

	.. change::

	  initial revision.
