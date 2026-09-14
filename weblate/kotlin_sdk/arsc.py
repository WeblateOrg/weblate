# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write Kotlin SDK translation tables without an Android toolchain."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from lxml import etree

QUANTITIES = {
    name: 0x01000004 + index
    for index, name in enumerate(("other", "zero", "one", "two", "few", "many"))
}
SPAN_TAGS = frozenset(
    {
        "b",
        "i",
        "u",
        "tt",
        "big",
        "small",
        "sup",
        "sub",
        "strike",
        "li",
        "marquee",
        "font",
        "a",
        "annotation",
    }
)
ANDROID_WHITESPACE = " \t\n\r\f\v"


@dataclass(frozen=True)
class Text:
    value: str
    spans: tuple[tuple[str, int, int], ...] = ()


type ResourceValue = Text | dict[str, Text]
type ResourceTable = dict[int, tuple[str, ResourceValue]]


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


# Escaping and nested spans share the whitespace/quoting state.
def android_text(value: str, *, markup: bool = False) -> Text:  # ruff: ignore[complex-structure]
    """
    Decode Android quoting/escapes and retain actual XML spans.

    Escaped HTML and CDATA are passed with markup=False, as literal text.
    """
    output: list[str] = []
    spans: list[tuple[str, int, int]] = []
    quoted = False
    last_space = False
    output_length = 0

    def append(text: str) -> None:
        nonlocal quoted, last_space, output_length
        index = 0
        while index < len(text):
            char = text[index]
            index += 1
            if char == "\\":
                last_space = False
                if index == len(text):
                    msg = "Trailing Android string escape"
                    raise ValueError(msg)
                char = text[index]
                index += 1
                if char == "u":
                    digits = text[index : index + 4]
                    if not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                        msg = "Invalid Android Unicode escape"
                        raise ValueError(msg)
                    char = chr(int(digits, 16))
                    index += 4
                else:
                    char = {"n": "\n", "t": "\t"}.get(char, char)
            elif char == '"':
                quoted = not quoted
                continue
            elif char in ANDROID_WHITESPACE and not quoted:
                if not last_space:
                    output.append(" ")
                    output_length += 1
                last_space = True
                continue
            else:
                last_space = False
            output.append(char)
            output_length += 2 if ord(char) > 0xFFFF else 1

    def visit(node: etree._Element) -> None:
        nonlocal quoted, last_space
        append(node.text or "")
        for child in node:
            name = etree.QName(child).localname
            namespace = etree.QName(child).namespace
            is_xliff = (
                namespace == "urn:oasis:names:tc:xliff:document:1.2" and name == "g"
            )
            if not is_xliff and (namespace or name not in SPAN_TAGS):
                msg = f"Unsupported Android span: {name}"
                raise ValueError(msg)
            start = output_length
            span_index = len(spans)
            tag = name + "".join(
                f";{key}={val}" for key, val in sorted(child.attrib.items())
            )
            if not is_xliff:
                quoted = last_space = False
                spans.append((tag, start, start - 1))
            visit(child)
            end = output_length - 1
            if not is_xliff:
                spans[span_index] = (tag, start, end)
                quoted = last_space = False
            append(child.tail or "")

    if markup:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(
            f'<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">{value}</resources>'.encode(),
            parser,
        )
        # AAPT2 trims raw boundary text only for resources without styling.
        if not any(
            etree.QName(node).namespace is None for node in root.iterdescendants()
        ):
            texts = root.xpath(".//text()")
            if texts:
                for text, side in ((texts[0], "left"), (texts[-1], "right")):
                    parent = text.getparent()
                    attribute = "tail" if text.is_tail else "text"
                    raw = getattr(parent, attribute) or ""
                    setattr(
                        parent,
                        attribute,
                        raw.lstrip(ANDROID_WHITESPACE)
                        if side == "left"
                        else raw.rstrip(ANDROID_WHITESPACE),
                    )
        visit(root)
    else:
        append(value.strip(ANDROID_WHITESPACE))
    if quoted:
        msg = "Unterminated Android string quote"
        raise ValueError(msg)
    normalized = (
        "".join(output).encode("utf-16-le", errors="surrogatepass").decode("utf-16-le")
    )
    return Text(normalized, tuple(span for span in spans if span[2] >= span[1]))


def chunk(kind: int, header: bytes, data: bytes = b"") -> bytes:
    return (
        struct.pack("<HHI", kind, 8 + len(header), 8 + len(header) + len(data))
        + header
        + data
    )


def padded(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % 4)


def string_pool(values: list[Text]) -> bytes:
    strings = list(values)
    known = set(strings)
    for text in values:
        for tag, _, _ in text.spans:
            if Text(tag) not in known:
                strings.append(Text(tag))
                known.add(Text(tag))
    indexes = {text: index for index, text in enumerate(strings)}
    data = bytearray()
    offsets = []
    for text in strings:
        offsets.append(len(data))
        encoded = text.value.encode("utf-16-le")
        size = len(encoded) // 2
        if size > 0x7FFFFFFF:
            msg = "Android string is too long"
            raise ValueError(msg)
        data.extend(
            struct.pack("<HH", (size >> 16) | 0x8000, size & 0xFFFF)
            if size > 0x7FFF
            else struct.pack("<H", size)
        )
        data.extend(encoded + b"\0\0")
    styles = bytearray()
    style_offsets = []
    if any(text.spans for text in strings):
        for text in strings:
            style_offsets.append(len(styles))
            if text.spans:
                for tag, start, end in text.spans:
                    styles.extend(struct.pack("<III", indexes[Text(tag)], start, end))
            styles.extend(struct.pack("<III", 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF))
    start = 28 + 4 * (len(offsets) + len(style_offsets))
    payload = struct.pack(
        f"<{len(offsets) + len(style_offsets)}I", *offsets, *style_offsets
    ) + padded(bytes(data))
    header = struct.pack(
        "<IIIII",
        len(strings),
        len(style_offsets),
        0,
        start,
        28 + len(payload) if styles else 0,
    )
    return chunk(1, header, payload + bytes(styles))


def locale_config(locale: str) -> bytes:
    """Encode language/region/script qualifiers in a 64-byte ResTable_config."""
    config = bytearray(64)
    struct.pack_into("<I", config, 0, 64)
    parts = locale.replace("_", "-").split("-")
    if parts[0] == "b" or locale.startswith("b+"):
        parts = locale.split("+")[1:]
    language = parts.pop(0)

    def packed(value: str, base: str) -> bytes:
        if len(value) == 2:
            return value.encode("ascii")
        if len(value) != 3:
            msg = f"Unsupported Android locale: {locale}"
            raise ValueError(msg)
        a, b, c = (ord(char) - ord(base) for char in value)
        if not all(0 <= item < 32 for item in (a, b, c)):
            msg = f"Invalid Android locale: {locale}"
            raise ValueError(msg)
        return bytes((0x80 | (c << 2) | (b >> 3), (b << 5 & 0xFF) | a))

    if not re.fullmatch(r"[a-z]{2,3}", language):
        msg = f"Invalid Android language: {locale}"
        raise ValueError(msg)
    config[8:10] = packed(language, "a")
    for part in parts:
        if re.fullmatch(r"r?[A-Z]{2}|[0-9]{3}", part):
            config[10:12] = packed(part.removeprefix("r"), "0")
        elif re.fullmatch(r"[A-Z][a-z]{3}", part):
            config[36:40] = part.encode("ascii")
        elif re.fullmatch(r"[a-zA-Z0-9]{5,8}|[0-9][a-zA-Z0-9]{3}", part):
            config[40:48] = part.encode("ascii").ljust(8, b"\0")
        else:
            msg = f"Unsupported Android locale qualifier: {part}"
            raise ValueError(msg)
    return bytes(config)


def generate(
    package: str, locale: str, resources: dict[int, tuple[str, Text | dict[str, Text]]]
) -> bytes:
    """Serialize self-contained strings and plural bags with caller-assigned IDs."""
    if not resources:
        msg = "No translated resources"
        raise ValueError(msg)
    resources = dict(sorted(resources.items()))
    package_ids = {resource_id >> 24 for resource_id in resources}
    if len(package_ids) != 1:
        msg = "Resource IDs must belong to one package"
        raise ValueError(msg)
    names = sorted({name for name, _ in resources.values()})
    keys = {name: index for index, name in enumerate(names)}
    values = list(
        dict.fromkeys(
            text
            for _, value in resources.values()
            for text in (value.values() if isinstance(value, dict) else [value])
        )
    )
    value_ids = {text: index for index, text in enumerate(values)}
    type_ids = sorted({resource_id >> 16 & 0xFF for resource_id in resources})
    if not type_ids[0]:
        msg = "Invalid resource type ID"
        raise ValueError(msg)
    types = [Text("") for _ in range(max(type_ids))]
    type_chunks: list[bytes] = []
    for type_id in type_ids:
        entries = {
            resource_id & 0xFFFF: value
            for resource_id, value in resources.items()
            if resource_id >> 16 & 0xFF == type_id
        }
        kinds = {isinstance(value, dict) for _, value in entries.values()}
        if len(kinds) != 1:
            msg = "Strings and plurals need distinct resource types"
            raise ValueError(msg)
        types[type_id - 1] = Text("plurals" if True in kinds else "string")
        count = max(entries) + 1
        spec = chunk(
            0x0202,
            struct.pack("<BBHI", type_id, 0, 0, count),
            struct.pack(
                f"<{count}I", *[4 if index in entries else 0 for index in range(count)]
            ),
        )
        offsets = [0xFFFFFFFF] * count
        data = bytearray()
        for index, (name, value) in sorted(entries.items()):
            offsets[index] = len(data)
            if isinstance(value, dict):
                if "other" not in value or value.keys() - QUANTITIES.keys():
                    msg = "Invalid plural quantities"
                    raise ValueError(msg)
                data.extend(struct.pack("<HHIII", 16, 1, keys[name], 0, len(value)))
                for quantity, text in sorted(
                    value.items(), key=lambda item: QUANTITIES[item[0]]
                ):
                    data.extend(
                        struct.pack(
                            "<IHBBI", QUANTITIES[quantity], 8, 0, 3, value_ids[text]
                        )
                    )
            else:
                data.extend(
                    struct.pack("<HHIHBBI", 8, 0, keys[name], 8, 0, 3, value_ids[value])
                )
        header = struct.pack(
            "<BBHII", type_id, 0, 0, count, 84 + count * 4
        ) + locale_config(locale)
        type_chunks.extend(
            (
                spec,
                chunk(
                    0x0201, header, struct.pack(f"<{count}I", *offsets) + bytes(data)
                ),
            )
        )
    type_pool = string_pool(types)
    key_pool = string_pool([Text(name) for name in names])
    package_name = package.encode("utf-16-le")
    if len(package_name) > 254:
        msg = "Android resource package name is too long"
        raise ValueError(msg)
    package_header = (
        struct.pack("<I", next(iter(package_ids)))
        + package_name.ljust(256, b"\0")
        + struct.pack("<IIIII", 288, len(types), 288 + len(type_pool), len(names), 0)
    )
    package_chunk = chunk(
        0x0200, package_header, type_pool + key_pool + b"".join(type_chunks)
    )
    return chunk(2, struct.pack("<I", 1), string_pool(values) + package_chunk)
