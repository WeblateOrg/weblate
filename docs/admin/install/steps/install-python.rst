Python modules
++++++++++++++

.. hint::

   We're using virtualenv to install Weblate in a separate environment from your
   system. If you are not familiar with it, check virtualenv :doc:`venv:user_guide`.


#. Create the virtualenv for Weblate:

   .. code-block:: sh

        virtualenv ~/weblate-env

#. Activate the virtualenv for Weblate:

   .. code-block:: sh

        . ~/weblate-env/bin/activate

#. Install Weblate including all optional dependencies:

   .. code-block:: sh

        # Install Weblate with all optional dependencies
        pip install "Weblate[all]"

   Please check :ref:`python-deps` for fine-tuning of optional dependencies.

   .. note::

      On some Linux distributions running Weblate fails with libffi error:

      .. code-block:: text

         ffi_prep_closure(): bad user_data (it seems that the version of the libffi library seen at runtime is different from the 'ffi.h' file seen at compile-time)

      This is caused by incompatibility of binary packages distributed via PyPI
      with the distribution. To address this, you need to rebuild the package
      on your system:

      .. code-block:: sh

         pip install --force-reinstall --no-binary :all: cffi
