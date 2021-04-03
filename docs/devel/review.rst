.. _source-review:

Reviewing strings
=================

.. _reports:

Activity reports
----------------

Activity reports check changes of translations, for projects, components or individual users.

The activity reports for a project or component is accessible from its dashboard, on the :guilabel:`Info`
tab.

.. image:: /images/activity.png

More reports are accessible on the :guilabel:`Insights`
tab, selecting :guilabel:`Translation reports`.

The activity of the currently signed in user can be seen by clicking on
:guilabel:`Profile` from the user menu on the top right.

Source strings checks
---------------------

There are many :ref:`checks`, some of them focus on improving the
quality of source strings. Many failing checks suggest a hint to make source strings
easier to translate. All types of failing source checks are displayed on the :guilabel:`Source`
tab of every component.

Translation string checks
-------------------------

Erroneous failing translation string checks indicate the problem is with
the source string. Translators sometimes fix mistakes in the translation
instead of reporting it - a typical example is a missing full stop at the end of
a sentence.

Reviewing all failing checks can provide valuable feedback to improve its
source strings. To make source strings review easier, Weblate automatically
creates a translation for the source language and shows you source level checks
there:

.. image:: /images/source-review.png

One of the most interesting checks here is the :ref:`check-multiple-failures` -
it is triggered whenever there is failure on multiple translations of a given string.
Usually this is something to look for, as this is a string which translators have
problems translating properly.

The detailed listing is a per language overview:

.. image:: /images/source-review-detail.png

.. _report-source:

Receiving source string feedback
--------------------------------

Translators can comment on both translation and source strings. Each
:ref:`component` can be configured to receive such comments to an e-mail
address (see :ref:`component-report_source_bugs`), and using the developers
mailing list is usually the best approach.  This way you can keep an eye on
when problems arise in translation, take care of them, and fix them quickly.

.. seealso::

    :ref:`user-comments`
