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

We're about to write custom Python code and we need place to store it - it's
called a module in Python.  Late we need to place somewhere where the Python
interpreter can import it - either in system path (usually something like
:file:`/usr/lib/python3.7/site-packages/`) or in Weblate directory, which is
also added to the interpreter search path.

The best approach is to create a proper Python package out of your customization:

1. Place your Python module with check into folder which will match your 
   package name. We're using `weblate_customization` in following examples.
2. Add empty :file:`__init__.py` file to the same directory. This ensures Python
   can import this whole package.
3. Write :file:`setup.py` in parent directory to describe your package:

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

4. Now you can install it using :command:`pip install -e .` 
5. Once installed into Python path, you can use it in Weblate configuration, in
   most cases as fully qualified path (for example
   ``weblate_customization.checks.FooCheck``).

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
      # Weblate apps are here...

      # Add your customization as last
      'weblate_customization',
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
