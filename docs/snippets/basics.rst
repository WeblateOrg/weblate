Weblate basics
++++++++++++++

Project and component structure
-------------------------------

In Weblate translations are organized into projects and components. Each project
can contain number of components and those contain translations into individual
languages. The component corresponds to one translatable file (for example
:ref:`gettext` or :ref:`aresource`). The projects are there to help you
organize component into logical sets (for example to group all translations
used within one application).

Additionally, components within projects can be structured using categories.
Components can belong to a category, and categories can be nested.

Internally, each project has translations to common strings propagated across
other components within it by default. This lightens the burden of repetitive
and multi version translation. The translation propagation can be disabled per
:ref:`component` using :ref:`component-allow_translation_propagation` in case
the translations should diverge.

Repository integration
----------------------

Weblate is built to integrate with upstream version control repository,
:doc:`/admin/continuous` describes building blocks and how the changes flow
between them.

.. seealso::

   :ref:`architecture` describes how Weblate works internally.

User attribution
----------------

Weblate keeps the translations properly authored by translators in the version
control repository by using name and e-mail. Having a real e-mail attached to
the commit follows the distributed version control spirits and allows services
like GitHub to associate your contributions done in Weblate with your GitHub
profile.

This feature also brings in risk of misusing e-mail published in the version
control commits. Moreover, once such a commit is published on public hosting
(such as GitHub), there is effectively no way to redact it. Weblate allows
choosing a private commit e-mail in :ref:`profile-account` to avoid this.

Therefore, admins should consider this while configuring Weblate:

* Such a usage of e-mail should be clearly described in service terms in case such document is needed. :ref:`legal` can help with that.
* :setting:`PRIVATE_COMMIT_EMAIL_OPT_IN` can make e-mails private by default.
