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

#. Install Weblate including all dependencies:

   .. code-block:: sh

        pip install Weblate

#. Install database driver:

   .. code-block:: sh

        pip install psycopg2-binary

#. Install wanted optional dependencies depending on features you intend to use
   (some might require additional system libraries, check :ref:`optional-deps`):

   .. code-block:: sh

        pip install ruamel.yaml aeidon boto3 zeep chardet tesserocr
