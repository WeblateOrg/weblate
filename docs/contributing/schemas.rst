Data schemas
============

Weblate uses `JSON Schema <https://json-schema.org/>`_ to define layout of external JSON files.

The published schemas use JSON Schema Draft 2020-12. External validators must
support this draft and enable format checking to enforce dates, hostnames, and
IRIs, as Weblate does. Reusable schema definitions use ``$defs``.

.. only:: not gettext

   .. _schema-memory:

   .. jsonschema:: ../specs/schemas/weblate-memory.schema.json

.. seealso::

   * :ref:`translation-memory`
   * :wladmin:`dump_memory`
   * :wladmin:`import_memory`


.. only:: not gettext

   .. _schema-userdata:

   .. jsonschema:: ../specs/schemas/weblate-userdata.schema.json

.. seealso::

   * :ref:`user-profile`
   * :wladmin:`dumpuserdata`



.. only:: not gettext

   .. _schema-messaging:

   .. jsonschema:: ../specs/schemas/weblate-messaging.schema.json

.. seealso::

   * :ref:`fedora-messaging`
   * :ref:`addon-weblate.webhook.webhook`
   * :ref:`change-actions`


.. only:: not gettext

   .. _schema-cdn-manifest:

   .. jsonschema:: ../specs/schemas/weblate-cdn-manifest.schema.json

.. seealso::

   * :ref:`CDN manifests <cdn-manifest>`


.. only:: not gettext

   .. _schema-kotlin-sdk-build:

   .. jsonschema:: ../specs/schemas/weblate-kotlin-sdk-build.schema.json
      :lift_definitions:
      :auto_reference:

.. seealso::

   * :ref:`kotlin-sdk`
   * :ref:`addon-weblate.cdn.kotlin`


.. only:: not gettext

   .. _schema-kotlin-sdk-manifest:

   .. jsonschema:: ../specs/schemas/weblate-kotlin-sdk-manifest.schema.json

.. seealso::

   * :ref:`kotlin-sdk`
   * :ref:`addon-weblate.cdn.kotlin`
