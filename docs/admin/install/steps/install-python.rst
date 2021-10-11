Python modules
++++++++++++++

.. hint::

   We're using virtualenv to install Weblate in a separate environment from your
   system. If you are not familiar with it, check virtualenv :doc:`venv:user_guide`.


#. Create the virtualenv for Weblate:

   .. code-block:: sh

        virtualenv --python=python3 ~/weblate-env

#. Activate the virtualenv for Weblate:

   .. code-block:: sh

        . ~/weblate-env/bin/activate

#. Install Weblate including all optional dependencies:

   .. code-block:: sh

        pip install "Weblate[all]"

   Please check :ref:`optional-deps` for fine-tuning of optional dependencies.
