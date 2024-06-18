Developing add-ons
==================

:ref:`addons` are way to customize localization workflow in Weblate.

.. currentmodule:: weblate.addons.base

.. autoclass:: BaseAddon
    :members:

.. currentmodule:: weblate.addons.models

.. class:: Addon

   ORM object for an add-on.

.. currentmodule:: weblate.trans.models

.. class:: Component

   ORM object for a component.

.. class:: Translation

   ORM object for a translation.

.. class:: Project

   ORM object for a project.

.. class:: Unit

   ORM object for an unit.

.. class:: User

   ORM object for an user.

.. class:: TranslationFormat

   Translation file wrapper.

Here is an example add-on:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python
