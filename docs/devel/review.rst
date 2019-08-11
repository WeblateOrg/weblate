.. _source-review:

Reviewing source strings
========================

.. _reports:

Activity reports
----------------

Check changes of translations, projects or for individual users.

.. image:: /images/activity.png

Source strings checks
---------------------

There are many :ref:`checks`, some of them focus on improving the
quality of source strings. Many failing checks make for a hint to make source strings
easier to translate. All types failing source checks are displayed on the :guilabel:`Source`
tab of every component.

Translation string checks
-----------------------------

Erroneous failing translation string checks indicate the problem is with
the source string. Translators sometimes fix mistakes in the translation
instead of reporting it - a typical example is a missing full stop at the end of
a sentence.

Reviewing all failing checks of your translation, for every language, can 
provide valuable feedback to improve its source strings.

:guilabel:`Source strings review` is in the :guilabel:`Tools`
menu of any given translation component. A similar view is presented when opening
a translation, with slightly different checks displayed:

.. image:: /images/source-review.png

One of the most interesting checks here is the :ref:`check-multiple-failures` -
it is triggered whenever there is failure on multiple translations of a given string.
Usually this is something to look for, as this is a string translators have
problems translating properly.

The detailed listing is a per language overview:

.. image:: /images/source-review-detail.png

String comments
---------------

Translators can comment on both translation and source strings.
Each :ref:`component` can be configured to receive such comments to an e-mail
address, and using the developers mailing list is usually the best approach.
This way you can keep an eye on when problems arise in translation, tend to, and fix them quickly.

