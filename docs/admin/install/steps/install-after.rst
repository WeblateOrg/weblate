After installation
------------------

Congratulations, your Weblate server is now running and you can start using it.

* You can now access Weblate on ``http://localhost:8000/``.
* Sign in with admin credentials obtained during installation or register with new users.
* You can now run Weblate commands using :command:`weblate` command when
  Weblate virtualenv is active, see :ref:`manage`.
* You can stop the test server with Ctrl+C.
* Review potential issues with your installation either on ``/manage/performance/`` URL (see :ref:`manage-performance`) or using :command:`weblate check --deploy`, see :ref:`production`.

Adding translation
++++++++++++++++++

#. Open the admin interface (``http://localhost:8000/create/project/``) and create the project you
   want to translate. See :ref:`project` for more details.

   All you need to specify here is the project name and its website.

#. Create a component which is the real object for translation - it points to the
   VCS repository, and selects which files to translate. See :ref:`component`
   for more details.

   The important fields here are: :ref:`component-name`, :ref:`component-repo`,
   and :ref:`component-filemask` for finding translatable files. Weblate
   supports a wide range of formats including :ref:`gettext`, :ref:`aresource`,
   :ref:`apple`, :ref:`javaprop`, :ref:`stringsdict` or :ref:`fluent`, see
   :ref:`formats` for more details.

#. Once the above is completed (it can be lengthy process depending on the size of
   your VCS repository, and number of messages to translate), you can start
   translating.
