Translation progress reporting
==============================

Reporting features give insight into how a translation progresses over a given
period. A summary of contributions to any given component over time is provided.
The reporting tool is found in the :guilabel:`Insights` menu of any translation component:

.. image:: /images/reporting.png
    
Several reporting tools are available on this page and all can produce output
in HTML, reStructuredText or JSON. The first two formats are suitable for
embedding statistics into existing documentation, while JSON is useful for further
processing of the data.

.. _credits:

Translator credits
------------------

Generates a document usable for crediting translators - sorted by language
and lists all contributors to a given language:

.. code-block:: rst

    * Czech

        * Michal Čihař <michal@cihar.com>
        * John Doe <john@example.com>

    * Dutch

        * Jane Doe <jane@example.com>


It will render as:

    * Czech

        * Michal Čihař <michal@cihar.com>
        * John Doe <john@example.com>

    * Dutch

        * Jae Doe <jane@example.com>

.. _stats:


Contributor stats
-----------------

Generates the number of translated words and strings by translator name:

.. code-block:: rst

    ======================================== ======================================== ========== ==========
    Name                                     Email                                    Words      Count     
    ======================================== ======================================== ========== ==========
    Michal Čihař                             michal@cihar.com                               2332        421 
    John Doe                                 john@example.com                                 25          8 
    ======================================== ======================================== ========== ==========

And it will get rendered as:

    ======================================== ======================================== ========== ==========
    Name                                     Email                                    Words      Count     
    ======================================== ======================================== ========== ==========
    Michal Čihař                             michal@cihar.com                               2332        421 
    John Doe                                 john@example.com                                 25          8 
    ======================================== ======================================== ========== ==========
