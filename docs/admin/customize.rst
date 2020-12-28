Customizing Weblate
===================

Extend and customize using Django and Python.
Contribute your changes upstream so that everybody can benefit. This reduces
your maintenance costs; code in Weblate is taken care of when changing internal
interfaces or refactoring the code.

.. warning::

   Neither internal interfaces nor templates are considered a stable API.
   Please review your own customizations for every upgrade, the interfaces or their
   semantics might change without notice.

.. seealso::

   :ref:`contributing`

.. _custom-module:

Creating a Python module
------------------------

If you are not familiar with Python, you might want to look into `Python For
Beginners <https://www.python.org/about/gettingstarted/>`_, explaining the
basics and pointing to further tutorials.

To write some custom Python code (called a module), a
place to store it is needed, either in the system path (usually something like
:file:`/usr/lib/python3.7/site-packages/`) or in the Weblate directory, which
is also added to the interpreter search path.

Better yet, turn your customization into a proper Python package:

1. Create a folder for your package (we will use `weblate_customization`).
2. Within it, create a :file:`setup.py` file to describe the package:

    .. code-block:: python

        from setuptools import setup

        setup(
            name="weblate_customization",
            version="0.0.1",
            author="Your name",
            author_email="yourname@example.com",
            description="Sample Custom check for Weblate.",
            license="GPLv3+",
            keywords="Weblate check example",
            packages=["weblate_customization"],
        )

3. Create a folder for the Python module (also called ``weblate_customization``)
   for the customization code.
4. Within it, create a :file:`__init__.py` file to make sure Python can import the module.
5. This package can now be installed using :command:`pip install -e`. More info to be found in :ref:`pip:editable-installs`.
6. Once installed, the module can be used in the Weblate configuration
   (for example ``weblate_customization.checks.FooCheck``).

Your module structure should look like this:

.. code-block:: text

    weblate_customization
    ├── setup.py
    └── weblate_customization
        ├── __init__.py
        ├── addons.py
        └── checks.py

You can find an example of customizing Weblate at
<https://github.com/WeblateOrg/customize-example>, it covers all the topics
described below.

Changing the logo
-----------------

1. Create a simple Django app containing the static files you want to overwrite
   (see :ref:`custom-module`).

   Branding appears in the following files:

   :file:`icons/weblate.svg`
       Logo shown in the navigation bar.
   :file:`logo-*.png`
       Web icons depending on screen resolution and web-browser.
   :file:`favicon.ico`
       Web icon used by legacy browsers.
   :file:`weblate-*.png`
       Avatars for bots or anonymous users. Some web-browsers use these as shortcut icons.
   :file:`email-logo.png`
       Used in notifications e-mails.

2. Add it to :setting:`django:INSTALLED_APPS`:

   .. code-block:: python

      INSTALLED_APPS = (
          # Add your customization as first
          "weblate_customization",
          # Weblate apps are here…
      )

3. Run :samp:`weblate collectstatic --noinput`, to collect static files served to
   clients.

.. seealso::

   :doc:`django:howto/static-files/index`,
   :ref:`static-files`

.. _custom-addon-modules:
.. _custom-check-modules:

Custom quality checks, addons and auto-fixes
--------------------------------------------

To install your code for :ref:`custom-autofix`, :ref:`own-checks` or
:ref:`own-addon` in Weblate:

1. Place the files into your Python module containing the Weblate customization
   (see :ref:`custom-module`).
2. Add its fully-qualified path to the Python class in the dedicated settings
   (:setting:`WEBLATE_ADDONS`, :setting:`CHECK_LIST` or :setting:`AUTOFIX_LIST`):

.. code-block:: python

    # Checks
    CHECK_LIST += ("weblate_customization.checks.FooCheck",)

    # Autofixes
    AUTOFIX_LIST += ("weblate_customization.autofix.FooFixer",)

    # Addons
    WEBLATE_ADDONS += ("weblate_customization.addons.ExamplePreAddon",)

.. seealso::

    :ref:`custom-autofix`, :ref:`own-checks`, :ref:`own-addon`, :ref:`addon-script`
