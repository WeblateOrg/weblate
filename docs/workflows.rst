Translation workflows
=====================

Weblate can be configured to support several translation workflows. This
document is not a complete listing of ways to configure Weblate, there are
certainly more options. However you can base another workflows based on
examples listed here.

Translation access
------------------

The :ref:`privileges` is not much discussed in the workflows as each of
access control options can be applied to any workflows. Please consult that
documentation for information how to manage access to translations.

Direct translation
------------------
This is most usual setup for smaller teams - anybody can directly translate.
This is also default setup in Weblate.

+------------------------+------------+-------------------------------------+
| Setting                |   Value    |   Note                              |
+========================+============+=====================================+
| Enable suggestions     | enabled    | it is useful for users to be able   |
|                        |            | suggest when they are not sure      |
+------------------------+------------+-------------------------------------+
| Suggestion voting      | disabled   |                                     |
+------------------------+------------+-------------------------------------+
| Autoaccept suggestions | 0          |                                     |
+------------------------+------------+-------------------------------------+
| Translators group      | Users      | or Translate with access control    |
+------------------------+------------+-------------------------------------+
| Reviewers group        | N/A        | not used                            |
+------------------------+------------+-------------------------------------+

Peer review
-----------

With this workflow, anybody can add suggestions, however they need approval
from additional member before it is accepted as a translation.

+------------------------+------------+-------------------------------------+
| Setting                |   Value    |   Note                              |
+========================+============+=====================================+
| Enable suggestions     | enabled    |                                     |
+------------------------+------------+-------------------------------------+
| Suggestion voting      | enabled    |                                     |
+------------------------+------------+-------------------------------------+
| Autoaccept suggestions | 1          | you can set higher value to require |
|                        |            | more peer reviews                   |
+------------------------+------------+-------------------------------------+
| Translators group      | Users      | or Translate with access control    |
+------------------------+------------+-------------------------------------+
| Reviewers group        | N/A        | not used, all translators review    |
+------------------------+------------+-------------------------------------+

Dedicated reviewers
-------------------

.. versionadded:: 2.18

    The proper review workflow is supported since Weblate 2.18.

With dedicated reviewers you have two groups of users - one which can submit
translations and one which reviews them. Review is there to ensure the
translations are consistent and in a good quality.

+------------------------+------------+-------------------------------------+
| Setting                |   Value    |   Note                              |
+========================+============+=====================================+
| Enable suggestions     | enabled    | it is useful for users to be able   |
|                        |            | suggest when they are not sure      |
+------------------------+------------+-------------------------------------+
| Suggestion voting      | disabled   |                                     |
+------------------------+------------+-------------------------------------+
| Autoaccept suggestions | 0          |                                     |
+------------------------+------------+-------------------------------------+
| Translators group      | Users      | or Translate with access control    |
+------------------------+------------+-------------------------------------+
| Reviewers group        | Reviewers  | or Review with access control       |
+------------------------+------------+-------------------------------------+
