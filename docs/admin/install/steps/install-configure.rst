Configuring Weblate
+++++++++++++++++++

.. note::

   Following steps assume virtualenv used by Weblate is active (what can be
   done by ``. ~/weblate-env/bin/activate``). In case this is not true, you will
   have to specify full path to :command:`weblate` command as
   ``~/weblate-env/bin/weblate``.

#. Copy the file :file:`~/weblate-env/lib/python3.7/site-packages/weblate/settings_example.py`
   to :file:`~/weblate-env/lib/python3.7/site-packages/weblate/settings.py`.

#.
   .. include:: steps/adjust-config.rst

#. Create the database and its structure for Weblate (the example settings use
   PostgreSQL, check :ref:`database-setup` for production ready setup):

   .. code-block:: sh

        weblate migrate

#. Create the administrator user account and copy the password it outputs
   to the clipboard, and also save it for later use:

   .. code-block:: sh

        weblate createadmin

#. Collect static files for web server (see :ref:`server` and :ref:`static-files`):

   .. code-block:: sh

        weblate collectstatic

#. Compress JavaScript and CSS files (optional, see :ref:`production-compress`):

   .. code-block:: sh

        weblate compress

#. Start Celery workers. This is not necessary for development purposes, but
   strongly recommended otherwise. See :ref:`celery` for more info:

   .. code-block:: sh

         ~/weblate-env/lib/python3.7/site-packages/weblate/examples/celery start

#. Start the development server (see :ref:`server` for production setup):

   .. code-block:: sh

        weblate runserver
