.. _starting:

Starting with internationalization
==================================

Have a project and want to translate it into several languages? This
guide will help you do so. Several typical situations are showcased, but
most of the examples are generic and can be applied to other scenarios as
well.

Before translating any software, you should realize that languages around the
world are really different and you should not make any assumption based on
your experience. For most of languages it will look weird if you try to
concatenate a sentence out of translated segments. You also should properly
handle plural forms because many languages have complex rules for that and the
internationalization framework you end up using should support this.

Last but not least, sometimes it might be necessary to add some context to the
translated string. Imagine a translator would get string ``Sun`` to translate.
Without context most people would translate that as our closest star, but it
might be actually used as an abbreviation for Sunday.

Choosing internationalization framework
---------------------------------------

Choose whatever is standard on your platform, try to avoid reinventing the
wheel by creating your own framework to handle localizations. Weblate supports
most of the widely used frameworks, see :ref:`formats` for more information
(especially :ref:`fmt_capabs`).

Our personal recommendation for some platforms is in the following table. This
is based on our experience, but that can not cover all use cases, so always
consider your environment when doing the choice.

+--------------------------+--------------------------+
| Platform                 | Recommended format       |
+==========================+==========================+
| Android                  | :ref:`aresource`         |
+--------------------------+--------------------------+
| iOS                      | :ref:`apple`             |
+--------------------------+--------------------------+
| Qt                       | :ref:`qtling`            |
+--------------------------+--------------------------+
| Python                   | :ref:`gettext`           |
+--------------------------+--------------------------+
| PHP                      | :ref:`gettext` [#php]_   |
+--------------------------+--------------------------+
| C/C++                    | :ref:`gettext`           |
+--------------------------+--------------------------+
| C#                       | :ref:`dotnet`            |
+--------------------------+--------------------------+
| Perl                     | :ref:`gettext`           |
+--------------------------+--------------------------+
| Ruby                     | :ref:`ryaml`             |
+--------------------------+--------------------------+
| Web extensions           | :ref:`webex`             |
+--------------------------+--------------------------+
| Java                     | :ref:`xliff` [#java]_    |
+--------------------------+--------------------------+
| JavaScript               | :ref:`js-i18next` [#js]_ |
+--------------------------+--------------------------+

.. [#php]

   The native Gettext support in PHP is buggy and often missing on Windows
   builds, it is recommended to use third party library `motranslator
   <https://github.com/phpmyadmin/motranslator>`_ instead.

.. [#java]

   You can also use :ref:`javaprop` if plurals are not needed.

.. [#js]

   You can also use plain :ref:`json` if plurals are not needed.

The more detailed workflow for some formats is described in following chapters:

* :doc:`gettext`
* :doc:`sphinx`
* :doc:`html`

.. seealso::

   * :doc:`integration`
   * :ref:`continuous-translation`

Educating developers for proper internationalization
----------------------------------------------------

Software internationalization is not just about being able to translate strings
but about making the whole software look native to a user from another country.
This also includes things like date or number formatting, currency display, or
inputting text in the right direction. Most software frameworks have good
support for this, so please follow their instructions for all these areas.

The string translation might not be a straightforward task as well. This is
especially true for short strings like captions or button labels. Different
languages have different rules, and it is not reasonable to expect that the
same string will always be translated the same. In many situations it also
might not be clear how to translate. In many situations it is even challenging
to distinguish whether the word is a verb or a noun.

All developers should understand this and uniquely identify strings used in
different scopes. "None" as none user might be translated different from "None"
as none items. Use different keys or contexts to distinguish these terms for
the translators. You can provide additional context in Weblate such as
:ref:`screenshots` or :ref:`additional-explanation`.

.. seealso::


   * :ref:`source-context`
