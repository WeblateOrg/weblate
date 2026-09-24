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

Weblate 2026.8 introduced NumPy as a required dependency. On x86-64 systems,
the optimized NumPy build bundled in the Docker image requires an x86-64-v2
compatible CPU. Without the required CPU features, NumPy fails to load and
Weblate cannot start.

Before upgrading, check for the required SSE4.2 CPU feature on the Linux system
running Docker:

.. code-block:: sh

   grep sse4_2 /proc/cpuinfo

Empty output indicates that a required CPU feature is unavailable. This is a
preliminary check; finding SSE4.2 does not verify all x86-64-v2 CPU features.

If Docker runs in a virtual machine, run the check inside the guest. Virtual
machines can hide CPU features supported by the host. Configure the virtual
machine to expose the required host CPU features, then reboot the guest. If
the physical CPU lacks the required features, upgrade the hardware.

Storage usage
+++++++++++++

The typical database storage usage is around 300 MB per 1 million hosted words.

Storage space needed for cloned repositories varies, but Weblate tries to keep
their size minimal by doing shallow clones.

Storage performance
+++++++++++++++++++

Version control operations perform many filesystem metadata lookups. The
:file:`vcs` subdirectory in :setting:`DATA_DIR` therefore needs low read
latency; storage with slow metadata access can make operations such as
:command:`git status` take a long time even when its bulk throughput is good.
Keep :setting:`CACHE_DIR` on low-latency local or temporary storage when
possible.

The deployment checks measure metadata lookup latency for both locations and
warn when the median latency exceeds 10 milliseconds. This is an approximate
point-in-time measurement affected by filesystem and system load. Rerun
:command:`weblate check --deploy` before changing the storage configuration.

Nodes
+++++

For small and medium-sized sites (millions of hosted words), all Weblate components (see
:ref:`architecture`) can be run on a single node.

When you grow to hundreds of millions of hosted words, it is recommended to
have a dedicated node for database (see :ref:`database-setup`).
