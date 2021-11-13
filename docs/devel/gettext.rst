Translating software using GNU gettext
--------------------------------------

`GNU gettext`_ is one of the most widely used tool for internationalization of
free software. It provides a simple yet flexible way to localize the software.
It has great support for plurals, it can add further context to the translated
string and there are quite a lot of tools built around it. Of course it has
great support in Weblate (see :ref:`gettext` file format description).

.. note::

    If you are about to use it in proprietary software, please consult
    licensing first, it might not be suitable for you.

GNU gettext can be used from a variety of languages (C, Python, PHP, Ruby,
JavaScript and many more) and usually the UI frameworks already come with some
support for it. The standard usage is through the `gettext()` function call,
which is often aliased to `_()` to make the code simpler and easier to read.

Additionally it provides `pgettext()` call to provide additional context to
translators and `ngettext()` which can handle plural types as defined for
target language.

As a widely spread tool, it has many wrappers which make its usage really
simple, instead of manual invoking of gettext described below, you might want
to try one of them, for example `intltool`_.

Workflow overview
+++++++++++++++++

The GNU gettext uses several files to manage the localization:

* :file:`PACKAGE.pot` contains strings extracted from your source code, typically using `xgettext`_ or some high level wrappers such as `intltool`_.
* :file:`LANGUAGE.po` contains strings with a translation to single language. It has to be updated by `msgmerge`_ once the :file:`PACKAGE.pot` is updated. You can create new language files using `msginit`_ or within Weblate.
* :file:`LANGUAGE.mo` contains binary representation of :file:`LANGUAGE.po` and is used at application runtime. Typically it is not kept under version control, but generated at compilation time using `msgfmt`_. In case you want to have it in the version control, you can generate it in Weblate using :ref:`addon-weblate.gettext.mo` addon.

Overall the GNU gettext workflow looks like this:

.. graphviz::

    digraph translations {
        graph [fontname = "sans-serif", fontsize=10];
        node [fontname = "sans-serif", fontsize=10, shape=note, margin=0.1, height=0];
        edge [fontname = "monospace", fontsize=10];

        "Source code" -> "PACKAGE.pot" [label=" xgettext "];
        "PACKAGE.pot" -> "LANGUAGE.po" [label=" msgmerge "];
        "LANGUAGE.po" -> "LANGUAGE.mo" [label=" msgfmt "];
    }




.. seealso::

   `Overview of GNU gettext <https://www.gnu.org/software/gettext/manual/html_node/Overview.html>`_

Sample program
++++++++++++++

The simple program in C using gettext might look like following:

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

Extracting translatable strings
+++++++++++++++++++++++++++++++

Once you have code using the gettext calls, you can use `xgettext`_ to
extract messages from it and store them into a `.pot
<https://www.gnu.org/software/gettext/manual/gettext.html#index-files_002c-_002epot>`_:

.. code-block:: console

    $ xgettext main.c -o po/hello.pot

.. note::

    There are alternative programs to extract strings from the code, for example
    `pybabel`_.

This creates a template file, which you can use for starting new translations
(using `msginit`_) or updating existing ones after code change (you
would use `msgmerge`_ for that). The resulting file is simply
a structured text file:

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

Each ``msgid`` line defines a string to translate, the special empty string
in the beginning is the file header containing metadata about the translation.

Starting new translation
++++++++++++++++++++++++

With the template in place, we can start our first translation:

.. code-block:: console

    $ msginit -i po/hello.pot -l cs --no-translator -o po/cs.po
    Created cs.po.

The just created :file:`cs.po` already has some information filled in. Most
importantly it got the proper plural forms definition for chosen language and you
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


This file is compiled into an optimized binary form, the `.mo
<https://www.gnu.org/software/gettext/manual/gettext.html#MO-Files>`_
file used by the `GNU gettext`_ functions at runtime.

Updating strings
++++++++++++++++

Once you add more strings or change some strings in your program, you execute again
`xgettext`_ which regenerates the template file:

.. code-block:: console

    $ xgettext main.c -o po/hello.pot

Then you can update individual translation files to match newly created templates
(this includes reordering the strings to match new template):

.. code-block:: console

    $ msgmerge --previous --update po/cs.po po/hello.pot

Importing to Weblate
++++++++++++++++++++

To import such translation into Weblate, all you need to define are the following
fields when creating component (see :ref:`component` for detailed description
of the fields):

=============================== ==================================================
Field                           Value
=============================== ==================================================
Source code repository          URL of the VCS repository with your project

File mask                       ``po/*.po``

Template for new translations   ``po/hello.pot``

File format                     Choose :guilabel:`gettext PO file`

New language                    Choose :guilabel:`Create new language file`
=============================== ==================================================

And that's it, you're now ready to start translating your software!

.. seealso::

    You can find a gettext example with many languages in the Weblate Hello project on
    GitHub: <https://github.com/WeblateOrg/hello>.

.. _GNU gettext: https://www.gnu.org/software/gettext/
.. _xgettext: https://www.gnu.org/software/gettext/manual/html_node/xgettext-Invocation.html
.. _msgmerge: https://www.gnu.org/software/gettext/manual/html_node/msgmerge-Invocation.html
.. _msgfmt: https://www.gnu.org/software/gettext/manual/html_node/msgfmt-Invocation.html
.. _msginit: https://www.gnu.org/software/gettext/manual/html_node/msginit-Invocation.html
.. _intltool: https://freedesktop.org/wiki/Software/intltool/
.. _pybabel: http://babel.pocoo.org/
