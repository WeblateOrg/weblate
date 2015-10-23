Starting with internationalization
==================================

You have a project and want to to translate it into several languages? This
guide will help you to do so. We will showcase several usual situations, but
most of the examples are generic and can be applied to other scenarios as
well.

Before translating any software, you should realize that languages around
world are really different and you should not make any assumption based on
your experience. For most of languages it will look weird if you try to
concatenate sentence out of translated segments. You also should properly
handle plural forms because many languages have complex rules for that and the
internationalization framework you end up using should support this. 

Last but not least, sometimes it might be necessary to add some context to the
translated string. Imagine translator would get string ``Sun`` to translate.
Without context most people would translate that as our closest star, but you
might be actually used as abbreviated name of day of week...


Translating software using GNU Gettext
--------------------------------------

`GNU Gettext`_ is one of the most widely used tool for internationalization of
free software. It provides simple yet flexible way to localize the software.
It has great support for plurals, it can add further context to the translated
string and there are quite a lot of tools built around it. Of course it has
great support in Weblate (see :ref:`gettext` file format description).

.. note::
   
    If you are about to use it in proprietary software, please consult
    licensing first, it might not be suitable for you.

GNU Gettext can be used from variety of languages (C, Python, PHP, Ruby,
Javascript and much more) and usually the UI frameworks already come with some
support for it. The standard usage is though the `gettext()` function call,
which is often aliased to `_()` to make the code simpler and easier to read.

Additionally it provides `pgettext()` call to provide additional context to
translators and `ngettext()` which can handle plural types as defined for
target language.

The simple program in C using Gettext might look like following:

.. code-block:: c

    #include <libintl.h>
    #include <locale.h>
    #include <stdio.h>
    #include <stdlib.h>

    int main(void)
    {
        int count = 1;
        setlocale(LC_ALL, "");
        bindtextdomain("hello", "/usr/share/locale");
        textdomain("hello");
        printf( 
            ngettext( 
                "Orangutan has %d banana.\n", 
                "Orangutan has %d bananas.\n", 
                count 
            ), 
            count 
        );
        printf("%s\n", gettext("Thank you for using Weblate."));
        exit(0);
    }

Once you have code using the gettext calls, you can use :program:`xgettext` to
extract message from it:

.. code-block:: console

    $ xgettext main.c -o po/hello.pot

This creates template file, which you can use for starting new translations
(using :program:`msginit`) or updating existing ones after code change (you
would use :program:`msgmerge` for that). The resulting file is simply
structured text file:

.. code-block:: po

    # SOME DESCRIPTIVE TITLE.
    # Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER
    # This file is distributed under the same license as the PACKAGE package.
    # FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
    #
    #, fuzzy
    msgid ""
    msgstr ""
    "Project-Id-Version: PACKAGE VERSION\n"
    "Report-Msgid-Bugs-To: \n"
    "POT-Creation-Date: 2015-10-23 11:02+0200\n"
    "PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
    "Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
    "Language-Team: LANGUAGE <LL@li.org>\n"
    "Language: \n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=CHARSET\n"
    "Content-Transfer-Encoding: 8bit\n"
    "Plural-Forms: nplurals=INTEGER; plural=EXPRESSION;\n"
    
    #: main.c:14
    #, c-format
    msgid "Orangutan has %d banana.\n"
    msgid_plural "Orangutan has %d bananas.\n"
    msgstr[0] ""
    msgstr[1] ""
    
    #: main.c:20
    msgid "Thank you for using Weblate."
    msgstr ""

The each ``msgid`` line defines string to translate, the special empty string
in the beginning is the file header containing metadata about the translation.

With the template in place, we can start first translation:

.. code-block:: console

    $ msginit -i po/hello.pot -l cs --no-translator -o po/cs.po
    Created cs.po.

The just created :file:`cs.po` has already some information filled in. Most
importantly it got proper plural forms definition for chosen language and you
can see number of plurals have changed according to that:

.. code-block:: po
    
    # Czech translations for PACKAGE package.
    # Copyright (C) 2015 THE PACKAGE'S COPYRIGHT HOLDER
    # This file is distributed under the same license as the PACKAGE package.
    # Automatically generated, 2015.
    #
    msgid ""
    msgstr ""
    "Project-Id-Version: PACKAGE VERSION\n"
    "Report-Msgid-Bugs-To: \n"
    "POT-Creation-Date: 2015-10-23 11:02+0200\n"
    "PO-Revision-Date: 2015-10-23 11:02+0200\n"
    "Last-Translator: Automatically generated\n"
    "Language-Team: none\n"
    "Language: cs\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=ASCII\n"
    "Content-Transfer-Encoding: 8bit\n"
    "Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\n"
    
    #: main.c:14
    #, c-format
    msgid "Orangutan has %d banana.\n"
    msgid_plural "Orangutan has %d bananas.\n"
    msgstr[0] ""
    msgstr[1] ""
    msgstr[2] ""
    
    #: main.c:20
    msgid "Thank you for using Weblate."
    msgstr ""

To import such translation into Weblate, all you need to define are following
fields when creating component (see :ref:`component` for detailed description
of the fields):

=============================== ==================================================
Field                           Value
=============================== ==================================================
Source code repository          URL of the VCS repository with your project

File mask                       ``po/*.po``

Base file for new translations  ``po/hello.pot``

File format                     Choose :guilabel:`Gettext PO file`

New language                    Choose :guilabel:`Automatically add language file`
=============================== ==================================================

And that's it, you're now ready to start translating your software!

.. note::

    You can find more complex of using Gettext in the weblate-hello project on
    GitHub: <http://github.com/nijel/weblate-hello>.


.. _GNU Gettext: http://www.gnu.org/software/gettext/
