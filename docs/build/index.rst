===================================
Welcome to Dogpile's documentation!
===================================

`Dogpile <http://bitbucket.org/zzzeek/dogpile>`_ provides the *dogpile* lock, 
one which allows a single thread or process to generate
an expensive resource while other threads/processes use the "old" value, until the
"new" value is ready.

Dogpile is at the core of the `dogpile.cache <http://bitbucket.org/zzzeek/dogpile.cache>`_ package
which provides for a basic cache API and sample backends based on the dogpile concept.


.. toctree::
   :maxdepth: 2

   usage
   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

