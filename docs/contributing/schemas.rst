Data schemas
============

Weblate uses `JSON Schema <https://json-schema.org/>`_ to define layout of external JSON files.

.. _schema-memory:

.. jsonschema:: ../schemas/weblate-memory.schema.json

.. seealso::

    :ref:`translation-memory`,
    :djadmin:`dump_memory`,
    :djadmin:`import_memory`

.. _schema-userdata:

.. jsonschema:: ../schemas/weblate-userdata.schema.json

.. seealso::

    :ref:`user-profile`,
    :djadmin:`dumpuserdata`
