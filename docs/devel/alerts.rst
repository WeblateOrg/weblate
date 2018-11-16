.. _alerts:

Translation component alerts
============================

The alerts are there to tell you there is something wrong with your translation
component. They can indicate problem in Weblate configuration or in your
translation project and they will give you a guidance how to address found issue.

The alerts currently cover following areas:

* Duplicate source strings in translation files
* Duplicate languages within translations
* Merge or update failure on the repository
* Unused new base in component settings
* Parse error in the translation files

You can find alerts on the component page as :guilabel:`Alerts`. If there is no
such tab, no alert was triggered on this particular component. There is no way
to ignore an alert, it will disappear automatically after underlying problem
has been fixed.

For example component having both duplicate strinsg and languages will have this:

.. image:: /images/alerts.png
