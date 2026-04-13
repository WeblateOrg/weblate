Developing add-ons
==================

:ref:`addons` are a way to customize localization workflow in Weblate.

.. currentmodule:: weblate.addons.base

.. autoclass:: BaseAddon
    :members:

Add-on hooks receive ORM objects from the ``weblate.*.models`` modules,
including ``Addon``, ``Component``, ``Translation``, ``Category``, ``Project``,
``Unit``, ``Change``, and ``User``. Add-on configuration forms should subclass
``weblate.addons.forms.BaseAddonForm``.

Here is an example add-on:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python
