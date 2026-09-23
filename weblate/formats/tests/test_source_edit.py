# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from translate.storage import applestrings_xliff, po, tbx, xliff, xliff2

from weblate.formats.models import FILE_FORMATS
from weblate.formats.source_edit import clone_for_edit, edit_identity, find_identity
from weblate.trans.util import join_plural


@pytest.mark.parametrize(
    ("format_id", "content", "new_key"),
    [
        ("json", '{"old": "Value", "keep": "Other"}', "new"),
        ("json-nested", '{"group": {"old": "Value"}}', "group.new"),
        ("arb", '{"old": "Value", "@old": {"description": "Note"}}', "new"),
        ("webextension", '{"old": {"message": "Value", "description": "Note"}}', "new"),
        ("i18next", '{"old": "Value", "old_plural": "Values"}', "new"),
        ("i18nextv4", '{"old_one": "Value", "old_other": "Values"}', "new"),
        ("yaml", "old: Value\nkeep: Other\n", "new"),
        ("ruby-yaml", "en:\n  old:\n    one: Value\n    other: Values\n", "new"),
        ("toml", 'old = "Value"\nkeep = "Other"\n', "new"),
        ("go-i18n-toml", '[old]\none = "Value"\nother = "Values"\n', "new"),
        ("properties", "# Note\nold=Value\nkeep=Other\n", "new"),
        ("gwt", "# Note\nold=Values\nold[one]=Value\n", "new"),
        ("php", '<?php\n// Note\n$old = "Value";\n', "$new"),
        ("dtd", '<!-- Note -->\n<!ENTITY old "Value">\n', "new"),
        ("fluent", "# Note\nold = Value\n", "new"),
        (
            "aresource",
            '<resources><string name="old">Value</string></resources>',
            "new",
        ),
        (
            "resx",
            '<root><data name="old"><value>Value</value><comment>Note</comment></data></root>',
            "new",
        ),
    ],
)
def test_key_roundtrip(format_id: str, content: str, new_key: str) -> None:
    cls = FILE_FORMATS[format_id]
    store = cls(BytesIO(content.encode()), is_template=True)
    store = clone_for_edit(store)
    raw = next(iter(store.all_store_units))
    unit = store.unit_class(store, raw, raw)
    target = unit.target
    notes = unit.notes
    edit_identity(store, unit, {"source": unit.source, "context": new_key})
    reloaded = cls(BytesIO(store.serialize(store.store)), is_template=True)
    edited = find_identity(reloaded, {"source": unit.source, "context": new_key})
    assert edited.target == target
    assert edited.notes == notes


@pytest.mark.parametrize(
    "format_id", ["po", "tbx", "plainxliff", "xliff2", "apple-xliff"]
)
def test_bilingual_source_roundtrip(format_id: str) -> None:
    cls = FILE_FORMATS[format_id]
    raw_cls = {
        "po": po.pofile,
        "tbx": tbx.tbxfile,
        "plainxliff": xliff.xlifffile,
        "xliff2": xliff2.Xliff2File,
        "apple-xliff": applestrings_xliff.AppleStringsXliffFile,
    }[format_id]
    store = cls(BytesIO(bytes(raw_cls())), source_language="en", language_code="cs")
    unit = store.new_unit("key", "Original", "Translation")
    old = {"context": unit.context, "source": unit.source}
    store = clone_for_edit(store)
    unit = find_identity(store, old)
    edit_identity(store, unit, {"source": "Updated", "context": unit.context})
    reloaded = cls(
        BytesIO(store.serialize(store.store)), source_language="en", language_code="cs"
    )
    edited = find_identity(reloaded, {"source": "Updated", "context": unit.context})
    assert edited.target == "Translation"


@pytest.mark.parametrize(
    "content",
    [
        "old = Value\n    .title = Title\n",
        "old = { $count ->\n    [one] Value\n   *[other] Values\n}\n",
    ],
)
def test_complex_fluent_edit_rejected(content: str) -> None:
    store = FILE_FORMATS["fluent"](BytesIO(content.encode()), is_template=True)
    raw = next(iter(store.all_store_units))
    unit = store.unit_class(store, raw, raw)
    original = store.serialize(store.store)
    with pytest.raises(ValidationError, match="attributes or selectors"):
        edit_identity(store, unit, {"source": unit.source, "context": "new"})
    assert store.serialize(store.store) == original


def test_inline_source_edit_rejected() -> None:
    cls = FILE_FORMATS["plainxliff"]
    content = b'<xliff version="1.2"><file source-language="en" target-language="cs" original="test"><body><trans-unit id="key"><source>Hello <g id="1">world</g></source><target>Translation</target></trans-unit></body></file></xliff>'
    store = cls(BytesIO(content))
    unit = store.content_units[0]
    original = store.serialize(store.store)
    with pytest.raises(ValidationError, match="inline markup"):
        edit_identity(store, unit, {"source": "Changed", "context": unit.context})
    assert store.serialize(store.store) == original


@pytest.mark.parametrize(
    ("format_id", "content"),
    [
        ("yaml", "old: Value\nkeep: Other\n"),
        ("toml", 'old = "Value"\nkeep = "Other"\n'),
    ],
)
def test_retained_key_collision(format_id: str, content: str) -> None:
    cls = FILE_FORMATS[format_id]
    store = cls(BytesIO(content.encode()), is_template=True)
    unit = find_identity(store, {"context": "old", "source": "Value"})
    original = store.serialize(store.store)
    with pytest.raises(ValidationError):
        edit_identity(store, unit, {"context": "keep", "source": "Value"})
    assert store.serialize(store.store) == original


def test_tbx_source_metadata() -> None:
    content = b'<martif><text><body><termEntry id="key"><descrip type="definition">Definition</descrip><langSet xml:lang="en"><tig id="first"><term>Original</term><termNote type="partOfSpeech">noun</termNote></tig><tig id="second"><term>Alternative</term></tig></langSet><langSet xml:lang="cs"><tig><term>Translation</term></tig></langSet></termEntry></body></text></martif>'
    cls = FILE_FORMATS["tbx"]
    store = cls(BytesIO(content), source_language="en", language_code="cs")
    unit = store.content_units[0]
    edit_identity(
        store,
        unit,
        {"source": join_plural(["Updated", "Alternative"]), "context": "renamed"},
    )
    reloaded = cls(
        BytesIO(store.serialize(store.store)), source_language="en", language_code="cs"
    )
    edited = reloaded.content_units[0]
    assert edited.source == join_plural(["Updated", "Alternative"])
    assert edited.context == "renamed"
    assert edited.target == "Translation"
    assert edited.unit.get_source_terms()[0].id == "first"
    assert b"noun" in store.serialize(store.store)
    assert b"Definition" in store.serialize(store.store)
