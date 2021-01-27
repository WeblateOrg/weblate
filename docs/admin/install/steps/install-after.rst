After installation
------------------

Congratulations, your Weblate server is now running and you can start using it.

* You can now access Weblate on ``http://localhost:8000/``.
* Login with admin credentials obtained during installation or register with new users.
* You can now run Weblate commands using :command:`weblate` command when
  Weblate virtualenv is active, see :ref:`manage`.
* You can stop the test server with Ctrl+C.
* Review potential issues with your installation either on ``/manage/performance/`` URL or using :command:`weblate check --deploy`, see :ref:`production`.

Adding translation
++++++++++++++++++

#. Open the admin interface (``http://localhost:8000/create/project/``) and create the project you
   want to translate. See :ref:`project` for more details.

   All you need to specify here is the project name and its website.

#. Create a component which is the real object for translation - it points to the
   VCS repository, and selects which files to translate. See :ref:`component`
   for more details.

   The important fields here are: Component name, VCS repository address and
   mask for finding translatable files. Weblate supports a wide range of formats
   including gettext PO files, Android resource strings, iOS string properties,
   Java properties or Qt Linguist files, see :ref:`formats` for more details.

#. Once the above is completed (it can be lengthy process depending on the size of
   your VCS repository, and number of messages to translate), you can start
   translating.
