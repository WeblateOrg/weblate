Customizing Weblate
===================

Weblate can be extended or customized using standard Django and Python ways.
Always please consider contributing changes upstream so that everybody can
benefit from your additions. Including your changes in Weblate itself will also
reduce your maintenance costs - code in Weblate is taken care of when changing
internal interfaces or refactoring the code.

.. warning::

   Neither internal interfaces or templates are considered as stable API.
   Please review your customizations on every upgrade, the interface or their
   semantics might change without notice.

.. seealso::

   :ref:`contributing`

.. _custom-module:

Creating Python module
----------------------

If you are not familiar with Python, you might want to look into `Python For
Beginners <https://www.python.org/about/gettingstarted/>`_ which explains the
basics and will point you to further tutorials.

We're about to write some custom Python code (called a module) and we need a
place to store it - either in the system path (usually something like
:file:`/usr/lib/python3.7/site-packages/`) or in the Weblate directory, which
is also added to the interpreter search path.

The best approach is to create a proper Python package out of your customization:

1. Create a folder for your package (we will use `weblate_customization`).
2. Inside, create a :file:`setup.py` file to describe the package:

    .. code-block:: python

        from setuptools import setup

        setup(
            name = "weblate_customization",
            version = "0.0.1",
            author = "Michal Cihar",
            author_email = "michal@cihar.com",
            description = "Sample Custom check for Weblate.",
            license = "BSD",
            keywords = "weblate check example",
            packages=['weblate_customization'],
        )

3. Create a folder for the Python module (also called `weblate_customization`).
4. To make sure Python can import the module, add an :file:`__init__.py` file
   inside the module folder. Put the rest of the customization code in this
   folder.
5. Now it's possible to install this package using :command:`pip install -e .`
6. Once installed, the module can be used in the Weblate configuration
   (for example ``weblate_customization.checks.FooCheck``).

Overall your module structure should look like:

.. code-block:: text

    weblate_customization
    ├── setup.py
    └── weblate_customization
        ├── __init__.py
        ├── addons.py
        └── checks.py

You can find example application for custimizing Weblate at
<https://github.com/WeblateOrg/customize-example>, it covers all topics
described below.

Changing logo
-------------

To change logo you need to create simple Django app which will contain static
files which you want to overwrite (see :ref:`custom-module`). Then you add it
into :setting:`django:INSTALLED_APPS`:

.. code-block:: python

   INSTALLED_APPS = (
      # Add your customization as first
      'weblate_customization',

      # Weblate apps are here...
   )

And then execute :samp:`./manage.py collectstatic --noinput`, this will collect
static files served to clients.

.. seealso::

   :doc:`django:howto/static-files/index`,
   :ref:`static-files`

.. _custom-check-modules:

Custom quality checks and auto fixes
------------------------------------

You have implemented code for :ref:`custom-autofix` or :ref:`custom-checks` and
now it's time to install it into Weblate. First place them into your Python
module with Weblate customization (see :ref:`custom-module`). Then enabled it
is just matter of adding its fully-qualified path to Python class to
appropriate settings (:setting:`CHECK_LIST` or :setting:`AUTOFIX_LIST`):

.. code-block:: python

  CHECK_LIST = (
      'weblate_customization.checks.FooCheck',
  )

.. seealso::

   :ref:`own-checks`

.. _custom-addon-modules:

Custom addons
-------------

First place them into your Python module with Weblate customization (see
:ref:`custom-module`). Then enabled it is just matter of adding its
fully-qualified path to Python class to appropriate settings
(:setting:`WEBLATE_ADDONS`):


.. code-block:: python

   WEBLATE_ADDONS = (
      'weblate_customization.addons.ExamplePreAddon',
   )

.. seealso::

   :ref:`own-addon`, :ref:`addon-script`
