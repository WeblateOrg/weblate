# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from lxml import etree

from weblate.utils.validators import validate_filename

GETTEXT_DATA_DIR = Path(__file__).resolve().parent / "extractors" / "gettext"
ITS_NAMESPACE = "http://www.w3.org/2005/11/its"
GETTEXT_NAMESPACE = "https://www.gnu.org/s/gettext/ns/its/extensions/1.0"


def get_bundled_rules_fingerprint(directory: Path) -> str:
    """Fingerprint the bundled rules, including their locating filenames."""
    digest = sha256()
    for path in sorted((directory / "its").iterdir()):
        if path.suffix in {".its", ".loc"} and path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_data_dirs(value: object) -> list[str]:
    """Validate the serialized configuration, including at runtime."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError(gettext("ITS directories must be a list of strings."))
    for name in value:
        if not name or ":" in name or "\\" in name or ".." in Path(name).parts:
            raise ValidationError(gettext("Invalid ITS directory path."))
        if name != ".":
            validate_filename(name)
    return value


def validate_rule_file(filename: Path) -> None:
    """Check rules without loading DTDs, entities, or external resources."""
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        remove_comments=True,
        remove_pis=True,
    )
    tree = etree.parse(str(filename), parser)
    if tree.docinfo.doctype:
        raise ValidationError(gettext("ITS rules must not contain a document type."))
    root = tree.getroot()
    expected = (
        "locatingRules" if filename.suffix == ".loc" else f"{{{ITS_NAMESPACE}}}rules"
    )
    if root.tag != expected:
        raise ValidationError(gettext("Invalid ITS rule document root."))
    for element in root.iter():
        if not isinstance(element.tag, str):
            raise ValidationError(gettext("Unsupported ITS rule content."))
        tag = etree.QName(element)
        if filename.suffix == ".loc":
            if tag.namespace or tag.localname not in {
                "locatingRules",
                "locatingRule",
                "documentRule",
            }:
                raise ValidationError(gettext("Unsupported ITS locating rule."))
            if tag.localname == "locatingRule" and not element.get("pattern"):
                raise ValidationError(gettext("ITS locating rules require a pattern."))
            if (
                tag.localname == "locatingRule"
                and not element.get("target")
                and element.find("documentRule") is None
            ):
                raise ValidationError(
                    gettext("ITS locating rules require a target or a document rule.")
                )
            if tag.localname == "documentRule" and not element.get("target"):
                raise ValidationError(gettext("ITS document rules require a target."))
        elif tag.namespace not in {ITS_NAMESPACE, GETTEXT_NAMESPACE}:
            raise ValidationError(gettext("Unsupported ITS rule namespace."))
        for attribute, value in element.attrib.items():
            name = etree.QName(attribute).localname
            if name in {"href", "base", "schemaLocation", "noNamespaceSchemaLocation"}:
                raise ValidationError(
                    gettext("External ITS rule references are not allowed.")
                )
            if name == "target":
                validate_rule_target(filename, value)
            if name == "selector" or name.endswith("Pointer"):
                etree.XPath(
                    value,
                    namespaces={key: uri for key, uri in element.nsmap.items() if key},
                )


def validate_rule_target(filename: Path, value: str) -> None:
    if (
        not value.endswith(".its")
        or "/" in value
        or "\\" in value
        or ":" in value
        or value.startswith(".")
    ):
        raise ValidationError(
            gettext("ITS targets must name a rule in the same directory.")
        )
    target = filename.parent / value
    if target.is_symlink() or not target.is_file():
        raise ValidationError(gettext("ITS target is missing or is a symbolic link."))


def resolve_data_dirs(root: Path, names: object) -> list[Path]:
    """Resolve and validate repository-local gettext data directories."""
    result = []
    for name in validate_data_dirs(names):
        relative = Path(name) / "its"
        directory = root
        for part in relative.parts:
            directory /= part
            if directory.is_symlink():
                raise ValidationError(
                    gettext("ITS directories must not contain symbolic links.")
                )
        if not directory.is_dir():
            raise ValidationError(
                gettext("ITS directory does not exist: %(path)s"),
                params={"path": relative},
            )
        for filename in sorted(directory.iterdir()):
            if filename.suffix not in {".its", ".loc"}:
                continue
            if filename.is_symlink() or not filename.is_file():
                raise ValidationError(
                    gettext("ITS rules must be regular files, not symbolic links.")
                )
            try:
                validate_rule_file(filename)
            except ValidationError as error:
                raise ValidationError(
                    gettext("Invalid ITS rule %(path)s: %(error)s"),
                    params={
                        "path": filename.relative_to(root),
                        "error": " ".join(error.messages),
                    },
                ) from error
            except (OSError, etree.LxmlError) as error:
                raise ValidationError(
                    gettext("Could not parse ITS rule: %(path)s"),
                    params={"path": filename.relative_to(root)},
                ) from error
        result.append(directory.parent)
    return result
