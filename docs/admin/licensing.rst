Licensing translations
======================

Weblate allows you to specify which license translations are
contributed under. This is especially important to do if the translations are
open to the public in order stipulate what they can be used for.

There are two things you specify on the :ref:`component` - license info
and if applicable, a contributor license agreement.

License information
-------------------

Upon specifying license info (license name and URL), this info is
shown in the translation info section.

Usually this is best location to place info on licensing where no
explicit consent is required, like if your project or translation is not libre.

Contributor agreement
---------------------

Once you specify a contributor license agreement, only users who have agreed to it will
be able to contribute. This is clearly visible when accessing the translation:

.. image:: /images/contributor-agreement.png

The entered text is formatted into paragraphs and external links can be included.
HTML markup can not be used.

Signed-off-by
-------------

Should your project require a ``Signed-off-by`` header in the commits, you should
turn on contributor license agreement with the DCO text and add the header to the commit
message (see :ref:`markup` for more details). The full commit message can look like this:

.. code-block:: django

    Translated using Weblate ({{ language_name }})

    Currently translated at {{ stats.translated_percent }}% ({{ stats.translated }} of {{ stats.all }} strings)

    Translation: {{ project_name }}/{{ component_name }}
    Translate-URL: {{ url }}
    Signed-off-by: {{ author }}

User licenses
-------------

Any user can review the translation licenses of all public projects on the instance in their profile:

.. image:: /images/profile-licenses.png
