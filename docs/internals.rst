.. _internals:

Internals
=========

.. note::

    This chapter will give you basic overview of Weblate internals.

Weblate is based on `Django`_ and most of it's code structure comes from that.
If you are not familiar with Django, you might want to check
:doc:`django:intro/overview` to get basic understanding of files structure.

Modules
-------

Weblate consists of several Django applications (some of them are optional, see
:doc:`admin/optionals`):

``accounts```

    User account, profiles and notifications.

``api``

    API based on `Django REST framework`_.

``billing``

    The optional :ref:`billing` module.

``gitexport``

    The optional :ref:`git-exporter` module.

``lang``

    Module defining language parameters.

``legal``

    The optional :ref:`legal` module.

``permissions``

    The :ref:`groupacl` code with various helpers.

``screenshots``

    Screenshots management and OCR module.

``trans``

    Main module handling translations.

``utils``

    Various helper utilities.
    

.. _Django: https://www.djangoproject.com/
.. _Django REST framework: http://www.django-rest-framework.org/
