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

Changing logo
-------------

To change logo you need to create simple Django app which will contain static
files which you want to overwrite. Then you add it into
:setting:`django:INSTALLED_APPS`:

.. code-block:: python

   INSTALLED_APPS = (
      # Weblate apps are here...

      # Add your customization as last
      'weblate_customization',
   )

And then execute :samp:`./manage.py collectstatic --noinput`, this will collect
static files served to clients.

You can find example application for this at <https://github.com/WeblateOrg/customize-example>.

.. seealso::

   :doc:`django:howto/static-files/index`,
   :ref:`static-files`
