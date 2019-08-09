Hardware requirements
---------------------

Weblate should run on all contemporary hardware without problems, the following is
the minimal configuration required to run Weblate on a single host (Weblate, database
and webserver):

* 2 GB of RAM
* 2 CPU cores
* 1 GB of storage space

The more memory the better - it is used for caching on all
levels (filesystem, database and Weblate).

Many concurrent users increases the amount of needed CPU cores.
For hundreds of translation components at least 4 GB of RAM is
recommended.

.. note::

    Actual requirements for your installation of Weblate vary heavily based on the size of
    the translations managed in it.
