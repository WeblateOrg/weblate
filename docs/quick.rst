Quick starting guide
====================

.. note::

    This is just a quick guide for installing and starting to use Weblate,
    please check :ref:`install` for more detailed instructions.

Installing from sources
-----------------------

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


Adding translation
------------------

#. Open admin interface (http://example.org/admin/) and create project you
   want to translate. See :ref:`project` for more details.

#. Create subproject which is the real resource for translating - it points to
   Git repository and selects which files to translate. See :ref:`subproject`
   for more details.

#. Once above is completed (it can be lengthy process depending on size of
   your Git repository and number of messages to translate), you can start
   translating.
