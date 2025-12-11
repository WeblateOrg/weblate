Hardware requirements
---------------------

Weblate should run on any contemporary hardware without problems, the following is
the minimal configuration required to run Weblate on a single host (Weblate, database
and web server):

* 3 GB of RAM
* 2 CPU cores
* 1 GB of storage space

.. note::

    Actual requirements for your installation of Weblate vary heavily based on the size of
    the translations managed in it.

Memory usage
++++++++++++

The more memory the better - it is used for caching on all
levels (file system, database and Weblate).
For hundreds of translation components, at least 4 GB of RAM is
recommended.

.. hint::

   For systems with less memory than recommended, :ref:`minimal-celery` is recommended.

CPU usage
+++++++++

Many concurrent users increase the amount of needed CPU cores.

Storage usage
+++++++++++++

The typical database storage usage is around 300 MB per 1 million hosted words.

Storage space needed for cloned repositories varies, but Weblate tries to keep
their size minimal by doing shallow clones.

Nodes
+++++

For small and medium-sized sites (millions of hosted words), all Weblate components (see
:ref:`architecture`) can be run on a single node.

When you grow to hundreds of millions of hosted words, it is recommended to
have a dedicated node for database (see :ref:`database-setup`).
