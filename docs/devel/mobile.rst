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

Translation propagation only reuses matching strings. The source text and
context have to be identical. For monolingual formats, the key has to match as
well. Propagation does not convert message syntax or semantics, so strings
using different placeholder syntaxes, such as ``Hello {name}`` and
``Hello %s``, do not match.

When consumers use the same messages but require different runtime
representations, consider keeping one canonical localization format and
generating consumer-specific resources in the build pipeline. This also allows
the generated resources to contain only the strings and languages needed by
each consumer. Use separate components when translators need to maintain
genuinely different messages. Disable translation propagation for these
components, or assign distinct keys or contexts to platform-specific messages,
so later edits do not overwrite intentional differences.

.. seealso::

   * :ref:`translation-consistency`
   * :ref:`translating-special-text`
