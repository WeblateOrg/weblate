Multi-platform localization
===========================

When translating apps for multiple platforms (e.g., Android and iOS), configure
separate components for each platform. The :ref:`translation-propagation` will
help you to keep the strings in sync.

Best practices:

- Create one component per platform (e.g., `MyApp Android`, `MyApp iOS`).
- Ensure identical source strings and keys are used across platforms where possible.
- Enable :ref:`component-allow_translation_propagation` to automatically reuse translations for matching strings.

This setup avoids duplicate work and keeps translations consistent across platforms.

.. seealso::

   :ref:`translation-consistency`
