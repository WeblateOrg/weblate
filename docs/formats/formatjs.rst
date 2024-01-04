.. _formatjs:

Format.JS JSON file
-------------------

.. versionadded:: 5.4

File format used when translating Format.JS and React-Intl applications.

.. seealso::

    :doc:`tt:formats/json`,
    `Format.JS Message Extraction <https://formatjs.io/docs/getting-started/message-extraction>`_

Example file:

.. code-block:: json

   {
      {
     "hak27d": {
       "defaultMessage": "Control Panel",
       "description": "title of control panel section"
     },
     "haqsd": {
       "defaultMessage": "Delete user {name}",
       "description": "delete button"
     },
     "19hjs": {
       "defaultMessage": "New Password",
       "description": "placeholder text"
     },
     "explicit-id": {
       "defaultMessage": "Confirm Password",
       "description": "placeholder text"
     }
   }

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``src/lang/*.json``              |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/extracted/en.json``        |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Format.JS JSON file`            |
+--------------------------------+----------------------------------+
