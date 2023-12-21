Building a translators community
================================

Following these recommendations supports the creation of a full, multilingual post-editing tool. Good translations are defined through the systemic-functional model of House which aims at a contextual correct translation. Write your own `post-editing guide <https://en.wikipedia.org/wiki/Postediting>`_ and alter these recommendations to fit your own definitions. In most cases the `browser-plugin of languageTool <https://languagetool.org/#firefox_chrome>`_  is useful as a proof-reading tool.

Many times translators will find problems with the source strings. Make sure it is easy for them to report such problems.
To gather this feedback, you can set up the :ref:`component-repoweb` field on your Weblate component, for translators to
propose their changes to the upstream repository. You can also receive translator comments if you setup :ref:`component-report_source_bugs`.

Community localization checklist
--------------------------------

The :guilabel:`Community localization checklist` which can be found in the
menu of each component can give you guidance to make your
localization process easy for community translators.



.. image:: /screenshots/guide.webp

Terminology management
----------------------
Post-editing of MT with terminology assignment influences each level of the translation process.
The machine translation system can be adapted to the specific vocabulary and style with a continued training or `neural fuzzy repair <https://aclanthology.org/P19-1175.pdf>`_. `Import <https://docs.weblate.org/en/latest/admin/memory.html#imported-translation-memory>`_ your existing translation memory into weblate or create an initial scope with your basic terminology. In the end the lector should be instructed with additional terminology documents to guarantee a good knowledge and output in the field.

Machine translation
-------------------
The quality of the automatic translation (often measured with the BLEU-score) correlates with editing time [1]. Choose a machine backend which supports the needed languages and domains. Make clear how the translation backend functions and which quality the post-editor has to expect.

Review translations
-------------------
The translations should be reviewed by a second person after the post-editing. With an impartial and competent reviewer, the two people rule reduces the errors and improves the quality and consistency of the content.
Providing reviewers with previews or alpha translations will make for the best review.
Screenshots, explanations also help to review the strings in context.

Structured feedback
-------------------
There are many :doc:`/user/checks` in Weblate that provide structured feedback on the quality of the translations.
They also give visual feedback during translation. This prevents recurring mistakes, and helps translators to understand how the code works.

Translation definition
----------------------
In addition to the mentalistic and impact-based definitions which make a strong reduction, the text-based linguistic approach fits best with the implemented translation methods. A well-formulated theory for translation evaluation is House's systemic-functional model, which focuses on the relation between original and translation. The model assumes that translation is an attempt to keep the semantic, pragmatic, and textual meaning of a text equivalent when crossing from one linguistic code to another.

The degree of quality of a translation is based on the degree of equivalence, the correspondence between the text profile and the text function. Because it cannot be calculated automatically, sufficient information should be collected to enable a uniform human evaluation. The two main parameters of agreement in a corresponding model are the macro-context – i.e. embedding in a larger social and literary context – and the micro-context consisting of field, tenor and mode.

Sources
-------
1. Marina Sanchez-Torron and Philipp Koehn in Machine Translation Quality and Post-Editor Productivity, Figure 1: https://www.cs.jhu.edu/~phi/publications/machine-translation-quality.pdf
2. Joanna Best und Sylvia Kalina.Übersetzen und Dolmetschen: eine Orientierungs-hilfe. A. Francke Verlag Tübingen und Base, 2002. Möglichkeiten der Übersetzungskritik starting on page number 101
3. neural fuzzy repair, Bram Bulté and Arda Tezcan in Neural Fuzzy Repair: Integrating Fuzzy Matches into Neural Machine Translation, 2019 https://aclanthology.org/P19-1175.pdf
