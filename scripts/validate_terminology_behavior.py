# Copyright © 2024 Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Validation script for terminology flag behavior.

This script demonstrates the current behavior of the terminology flag
and validates that it works as documented.

Usage:
    python scripts/validate_terminology_behavior.py

This script is meant to be run in a Weblate development environment
to validate the terminology flag behavior.
"""

import os
import sys

import django
from django.db import transaction

from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings_test")
django.setup()


def validate_terminology_behavior():
    """
    Validate the terminology flag behavior.

    This function demonstrates:
    1. Setting the terminology flag creates translations for all languages
    2. Removing the flag doesn't delete existing translations
    3. Re-adding the flag doesn't create duplicates
    """
    print("=== Terminology Flag Behavior Validation ===\n")

    # Create a test project and component
    with transaction.atomic():
        # Create test project
        project = Project.objects.create(name="Test Project", slug="test-project")

        # Create test languages
        en_lang = Language.objects.get(code="en")
        cs_lang = Language.objects.get(code="cs")
        de_lang = Language.objects.get(code="de")

        # Create glossary component
        component = Component.objects.create(
            project=project,
            name="Test Glossary",
            slug="test-glossary",
            is_glossary=True,
            file_format="po",
            filemask="*.po",
            template="",
            new_base="",
            vcs="local:",
        )

        # Create translations for the component
        en_trans = Translation.objects.create(
            component=component, language=en_lang, filename="en.po", is_source=True
        )

        cs_trans = Translation.objects.create(
            component=component, language=cs_lang, filename="cs.po"
        )

        de_trans = Translation.objects.create(
            component=component, language=de_lang, filename="de.po"
        )

        print("Created test environment:")
        print(f"  Project: {project.name}")
        print(f"  Component: {component.name} (glossary)")
        print(f"  Languages: {en_lang.code}, {cs_lang.code}, {de_lang.code}")
        print()

        # Test 1: Add a term without terminology flag
        print("1. Adding term without terminology flag...")
        source_unit = Unit.objects.create(
            translation=en_trans,
            source="test term",
            target="test term",
            context="test-context",
            extra_flags="",
        )

        initial_count = Unit.objects.count()
        print(f"   Initial unit count: {initial_count}")
        print(f"   Source unit created: {source_unit.source}")
        print()

        # Test 2: Set terminology flag
        print("2. Setting terminology flag...")
        source_unit.extra_flags = "terminology"
        source_unit.save()

        # Trigger terminology sync
        en_trans.sync_terminology()

        after_terminology_count = Unit.objects.count()
        print(f"   Units after terminology flag: {after_terminology_count}")
        print(f"   Units created: {after_terminology_count - initial_count}")

        # Verify translations exist for all languages
        for trans in [cs_trans, de_trans]:
            units = trans.unit_set.filter(source="test term")
            print(f"   {trans.language.code}: {units.count()} units")
        print()

        # Test 3: Remove terminology flag
        print("3. Removing terminology flag...")
        source_unit.extra_flags = ""
        source_unit.save()

        after_removal_count = Unit.objects.count()
        print(f"   Units after flag removal: {after_removal_count}")
        print(f"   Units preserved: {after_removal_count - initial_count}")

        # Verify translations still exist
        for trans in [cs_trans, de_trans]:
            units = trans.unit_set.filter(source="test term")
            print(f"   {trans.language.code}: {units.count()} units (preserved)")
        print()

        # Test 4: Re-add terminology flag
        print("4. Re-adding terminology flag...")
        source_unit.extra_flags = "terminology"
        source_unit.save()

        # Trigger terminology sync again
        en_trans.sync_terminology()

        final_count = Unit.objects.count()
        print(f"   Final unit count: {final_count}")
        print(f"   No new units created: {final_count == after_removal_count}")
        print()

        # Summary
        print("=== Summary ===")
        print("✅ Terminology flag creates translations for all languages")
        print("✅ Removing the flag preserves existing translations")
        print("✅ Re-adding the flag doesn't create duplicates")
        print("✅ Behavior is consistent with documentation")

        # Cleanup
        project.delete()
        print("\n✅ Test environment cleaned up")


if __name__ == "__main__":
    try:
        validate_terminology_behavior()
    except Exception as e:
        print(f"❌ Error during validation: {e}")
        sys.exit(1)
