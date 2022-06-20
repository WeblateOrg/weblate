Python modules
++++++++++++++

.. hint::

   We're using virtualenv to install Weblate in a separate environment from your
   system. If you are not familiar with it, check virtualenv :doc:`venv:user_guide`.

.. warning::

   Run the following commands in an empty directory

#. Create the virtualenv for Weblate:

   .. code-block:: sh

        python3 -m venv .

#. Activate the virtualenv for Weblate:

   .. code-block:: sh

        source bin/activate

#. Install Weblate including all optional dependencies:

   .. code-block:: sh

        # pkgconfig is needed to install borgbackup 1.2
        pip3 install pkgconfig
        # Install Weblate with all optional dependencies, if you want to use PostgreSQL
        pip3 install "Weblate[all]"
        # If you want to use MySQL/MariaDB instead PostgreSQL
        pip3 install "Weblate[all,MySQL]"

   Please check :ref:`optional-deps` for fine-tuning of optional dependencies.

   .. note::

      On some Linux distributions running Weblate fails with libffi error:

      .. code-block:: text

         ffi_prep_closure(): bad user_data (it seems that the version of the libffi library seen at runtime is different from the 'ffi.h' file seen at compile-time)

      This is caused by incompatibility of binary packages distributed via PyPI
      with the distribution. To address this, you need to rebuild the package
      on your system:

      .. code-block:: sh

         pip3 install --force-reinstall --no-binary :all: cffi
