.. _internals:

Internals
=========

.. note::

    This chapter will give you basic overview of Weblate internals.

Weblate is based on `Django`_ and most of its code structure comes from that.
If you are not familiar with Django, you might want to check
:doc:`django:intro/overview` to get basic understanding of files structure.

Modules
-------

Weblate consists of several Django applications (some of them are optional, see
:doc:`admin/optionals`):

``accounts```

    User account, profiles and notifications.

``addons``

    Addons to tweak Weblate behavior, see :ref:`addons`.

``api``

    API based on `Django REST framework`_.

``auth``
    
    Authentication and permissions.

``billing``

    The optional :ref:`billing` module.

``formats``

    File formats abstraction layer based on translate-toolkit.

``gitexport``

    The optional :ref:`git-exporter` module.

``lang``

    Module defining language and plural models.

``langdata``

    Language data definitions.

``legal``

    The optional :ref:`legal` module.

``machinery```

    Machine translation services integration.

``memory``

    Built in translation memory, see :ref:`translation-memory`.

``permissions``

    Obsolete.

``screenshots``

    Screenshots management and OCR module.

``trans``

    Main module handling translations.

``utils``

    Various helper utilities.

``vcs``

    Version control system abstraction.

``wladmin``

    Django admin interface customization.
    

.. _Django: https://www.djangoproject.com/
.. _Django REST framework: http://www.django-rest-framework.org/
