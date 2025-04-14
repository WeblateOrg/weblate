Python modules
++++++++++++++

.. hint::

   We're using virtualenv to install Weblate in a separate environment from your
   system. If you are not familiar with it, check virtualenv :doc:`venv:user_guide`.


#. Create the virtualenv for Weblate:

   .. code-block:: sh

        uv venv ~/weblate-env

#. Activate the virtualenv for Weblate:

   .. code-block:: sh

        . ~/weblate-env/bin/activate

#. Install Weblate including all optional dependencies:

   .. code-block:: sh

        # Install Weblate with all optional dependencies
        uv pip install "weblate[all]"

   Please check :ref:`python-deps` for fine-tuning of optional dependencies.

   .. seealso::

      :ref:`troubleshoot-pip-install` describes frequent issues while installing Python
      dependencies.
