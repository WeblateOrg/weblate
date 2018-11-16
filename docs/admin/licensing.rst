Licensing translations
======================

Weblate allows you to specify under which license the translations are
contributed. This is especially important to specify if the translations are
open to the public to raise proper expectations what can be done with the
translations. 

There are two things you specify on the :ref:`component` - license information
and the contributor agreement.

License information
-------------------

Upon specifying license information (license name and URL), this information is
shown in the translation information, but it is not enforced in any way.

Usually this is best location to place information on licensing where no
explicit consent is required.

Contributor agreement
---------------------

Once you specify contributor agreement, only users who have agreed to it will
be able to contribute. This is clearly visible when accessing the translation:

.. image:: /images/contributor-agreement.png

The entered text is formatted into paragraphs and external links are possible.
HTML markup can not be used.

Signed off by
-------------

Should your project require ``Signed-off-by`` header in the commits, you should
enable contributor agreement with the DCO text and add the header to the commit
message (see :ref:`markup` for more details). The full commit message can look like:

.. code-block:: django

    Translated using Weblate ({{ language_name }})

    Currently translated at {{ stats.translated_percent }}% ({{ stats.translated }} of {{ stats.all }} strings)

    Translation: {{ project_name }}/{{ component_name }}
    Translate-URL: {{ url }}
    Signed-off-by: {{ author }}

User licenses
-------------

User can review licenses on projects he is contributing to in the profile:

.. image:: /images/profile-licenses.png
