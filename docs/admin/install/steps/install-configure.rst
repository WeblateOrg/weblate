Configuring Weblate
+++++++++++++++++++

.. note::

   The following assumes the virtualenv used by Weblate is activated
   (by executing ``. ~/weblate-env/bin/activate``). If not, specify the full path
   to the :command:`weblate` command as ``~/weblate-env/bin/weblate``.

#. Copy the file :file:`~/weblate-env/lib/python3.9/site-packages/weblate/settings_example.py`
   to :file:`~/weblate-env/lib/python3.9/site-packages/weblate/settings.py`.

#.
   .. include:: steps/adjust-config.rst

#. Create the database and its structure for Weblate (the example settings use
   PostgreSQL, check :ref:`database-setup` for a production-ready setup):

   .. code-block:: sh

        weblate migrate

   .. seealso::

      :wladmin:`migrate`

#. Create an administrator user account ``admin``, generate its password, and copy it
   to the clipboard; remember to save it for later use:

   .. code-block:: sh

        weblate createadmin

   .. hint::

      If you previously missed/lost the admin password, you can generate a new one with the following command:

      .. code-block:: sh

         weblate createadmin --update

   .. seealso::

      :wladmin:`createadmin`

#. Collect the static files for your web server (see :ref:`server` and :ref:`static-files`):

   .. code-block:: sh

        weblate collectstatic

#. Compress the JavaScript and CSS files (optional, see :ref:`production-compress`):

   .. code-block:: sh

        weblate compress

#. Start the Celery workers. This is not necessary for development purposes, but
   strongly recommended otherwise. :ref:`celery` has more info:

   .. code-block:: sh

         ~/weblate-env/lib/python3.9/site-packages/weblate/examples/celery start

#. Start the development server (:ref:`server` details a production setup):

   .. code-block:: sh

        weblate runserver
