# Copyright © 2024 Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Terminology Flag Semantics Solution

This document explains the solution to the "Unclear Semantics of 'terminology' Flag" issue in Weblate.

## Problem Summary

The original issue raised concerns about unclear semantics of the "terminology" flag in Weblate glossaries:

1. **Operational first-time behavior**: When set, it creates empty translation strings for all languages
2. **State Indication**: Unclear what state the flag represents
3. **Irreversible behavior**: Removing the flag doesn't revert the operation
4. **Business logic**: Unclear what happens when the flag is removed

## Solution Overview

The solution clarifies the semantics and documents the intentional behavior of the terminology flag.

### Key Behavioral Clarifications

1. **One-time Trigger**: The terminology flag acts as a one-time trigger for creating missing translations
2. **Preservation Intent**: Removing the flag intentionally preserves existing translations to prevent data loss
3. **State Indication**: The flag indicates "should be available in all languages"
4. **No Duplicates**: Re-adding the flag doesn't create duplicate translations

## Changes Made

### 1. Enhanced Documentation (`docs/user/glossary.rst`)

**Before:**
```
Flagging certain glossary terms as ``terminology`` by bulk-editing, typing in the flag,
or by using :guilabel:`Tools` ↓ :guilabel:`Mark as terminology` adds entries for them
to all languages in the glossary. Use this for important terms that should
be well thought out, and retain a consistent meaning across all languages.
```

**After:**
```
Flagging certain glossary terms as ``terminology`` by bulk-editing, typing in the flag,
or by using :guilabel:`Tools` ↓ :guilabel:`Mark as terminology` ensures that the term
is available for translation in all languages of the glossary.

**What happens when you mark a term as terminology:**

* **First-time behavior**: When a term is marked as terminology for the first time, 
  Weblate automatically creates empty translation entries for all languages in the glossary 
  that don't already have a translation for this term.
* **Ongoing behavior**: The flag indicates that this term should be consistently 
  available across all languages in the glossary.
* **Removing the flag**: When you unmark a term as terminology, the existing translations 
  remain in place. The flag removal does not delete any translations that were already created.

**Use cases:**

* **Important terms**: Use this for key terminology that should be consistently 
  translated across all languages in your project.
* **Cross-language consistency**: Ensures that important terms are not missing 
  from any language in the glossary.
* **Quality assurance**: Helps maintain consistent terminology across all 
  translations by making sure all languages have the opportunity to translate 
  important terms.

**Important notes:**

* The terminology flag is a **one-time trigger** for creating missing translations.
* Once translations are created, removing the flag will **not** delete them.
* This behavior is intentional to preserve existing work and prevent accidental 
  data loss.
* If you need to remove translations, you must do so manually for each language.
```

### 2. Improved Code Documentation

#### `weblate/trans/models/translation.py` - `sync_terminology()` function

Added comprehensive docstring explaining:
- Purpose of the function
- Behavior when flag is set/removed
- Intentional preservation of existing translations
- Reference to user documentation

#### `weblate/glossary/tasks.py` - `sync_terminology()` task

Enhanced documentation to clarify:
- What the task ensures
- Intentional behavior regarding translation preservation
- Prevention of accidental data loss

#### `weblate/checks/flags.py` - Terminology flag definition

Added inline comments explaining:
- Purpose of the flag
- One-time trigger nature
- Irreversible behavior

### 3. Comprehensive Test Coverage

Added `test_terminology_flag_removal_behavior()` in `weblate/glossary/tests.py` that:

1. **Tests flag setting**: Verifies translations are created for all languages
2. **Tests flag removal**: Confirms existing translations are preserved
3. **Tests flag re-addition**: Ensures no duplicates are created
4. **Documents behavior**: Serves as living documentation of expected behavior

### 4. Validation Script

Created `scripts/validate_terminology_behavior.py` that:
- Demonstrates the complete behavior cycle
- Validates the documented behavior
- Provides a testable example for developers

## Testing the Solution

### Option 1: Run the Test Suite (Recommended)

```bash
# In a Weblate development environment
python -m pytest weblate/glossary/tests.py::GlossaryTest::test_terminology_flag_removal_behavior -v
```

### Option 2: Run the Validation Script

```bash
# In a Weblate development environment
python scripts/validate_terminology_behavior.py
```

### Option 3: Manual Testing

1. Create a glossary component in Weblate
2. Add a term without the terminology flag
3. Mark it as terminology - observe translations created for all languages
4. Remove the terminology flag - observe translations remain
5. Re-add the terminology flag - observe no duplicates created

## Benefits of This Solution

1. **Clarity**: Users now understand exactly what the terminology flag does
2. **Consistency**: Behavior is documented and tested
3. **Safety**: Intentional preservation prevents accidental data loss
4. **Maintainability**: Clear documentation helps future developers
5. **User Experience**: Users know what to expect when using the feature

## Future Considerations

While this solution addresses the immediate concerns, future enhancements could include:

1. **UI Indicators**: Visual cues showing which terms have the terminology flag
2. **Bulk Operations**: Tools for managing terminology flags across multiple terms
3. **Audit Trail**: Better tracking of when terminology flags were set/removed
4. **Export Options**: Include terminology flag status in glossary exports

## Conclusion

This solution successfully addresses the unclear semantics of the terminology flag by:

- **Documenting the current behavior** as intentional and beneficial
- **Explaining the one-time trigger nature** of the flag
- **Clarifying the preservation intent** when removing the flag
- **Providing comprehensive test coverage** to ensure consistency
- **Creating validation tools** for developers and users

The terminology flag now has clear, well-documented semantics that users can rely on for managing their glossary terms effectively.
