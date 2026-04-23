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


Typing add-on configuration
---------------------------

Add-on configuration is stored in the ``Addon.configuration`` JSON field, so
the model keeps the persisted data as raw JSON. Add-on implementations can type
their own configuration by parameterizing ``BaseAddon`` and ``BaseAddonForm``.

Use two ``TypedDict`` classes when the stored JSON can differ from the runtime
shape: a permissive, usually ``total=False``, stored configuration for legacy
or missing values, and a total runtime configuration returned by
``normalize_configuration()``. Runtime add-on code should read
``self.configuration`` or ``self.get_configuration()`` so it sees normalized
defaults instead of raw persisted JSON.

For simple add-ons where the stored and runtime shapes are identical, define a
single ``TypedDict`` and use it for both ``BaseAddon`` type parameters. Keep
the form's ``serialize_form()`` return type aligned with the stored
configuration type.
