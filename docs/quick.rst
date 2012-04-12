Quick installation guide
========================

.. note::

    This is just a quick guide for installing Weblate, please
    check :ref:`install` for more detailed instructions.

From sources/git
----------------

#. Install all required dependencies, see :ref:`requirements`.

#. Grab Weblate sources (either using Git or download a tarball) and unpack 
   them.

#. Edit :file:`settings.py` to match your setup. You will at least need to
   configure database connection (possibly adding user and creating the 
   database). Check :ref:`config` for Weblate specific configuration options.

#. Build Django tables and initial data:

   .. code-block:: sh

        ./manage.py syncdb
        ./manage.py setuplang
        ./manage.py setupgroups
        ./manage.py compilemessages # If you are using Git checkout

#. Configure webserver to serve Weblate, see :ref:`server`.
