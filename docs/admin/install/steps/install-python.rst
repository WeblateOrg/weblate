Python modules
++++++++++++++

.. hint::

   We're installing Weblate in a separate Python environment.


#. Create the Python environment for Weblate:

   .. code-block:: sh

        uv venv ~/weblate-env

#. Activate the Python environment for Weblate:

   .. code-block:: sh

        . ~/weblate-env/bin/activate

#. Install Weblate including all optional dependencies:

   .. code-block:: sh

        # Install Weblate with all optional dependencies
        uv pip install "weblate[all]"

   Please check :ref:`python-deps` for fine-tuning of optional dependencies.

.. seealso::

   * `Using Python environments`_
   * :ref:`troubleshoot-pip-install`

.. _Using Python environments: https://docs.astral.sh/uv/pip/environments/
