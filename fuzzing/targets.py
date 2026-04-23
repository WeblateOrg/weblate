# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import contextlib
import json
import warnings
from base64 import b64encode
from binascii import Error as BinasciiError
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from django.core.exceptions import ValidationError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from lxml.etree import XMLSyntaxError
from pyparsing import ParseException
from rest_framework.exceptions import ParseError
from translate.storage.base import ParseError as TranslateToolkitParseError

from fuzzing.atheris_compat import FuzzedDataProvider
from fuzzing.bootstrap import bootstrap_django

_MARKDOWN_STATE = {"patched": False}


def _no_mentions(_text: str) -> list[object]:
    return []


def _bootstrap_targets() -> None:
    bootstrap_django()


def _bootstrap_markdown() -> None:
    _bootstrap_targets()
    if _MARKDOWN_STATE["patched"]:
        return

    from weblate.utils import markdown as markdown_utils

    markdown_utils.get_mention_users = _no_mentions
    _MARKDOWN_STATE["patched"] = True


VALID_MEMORY_JSON = json.dumps(
    [
        {
            "source": "Hello, world!\n",
            "target": "Ahoj svete!\n",
            "source_language": "en",
            "target_language": "cs",
            "origin": "test/test",
            "category": 10000001,
        }
    ]
).encode()

VALID_BACKUP_JSON = json.dumps(
    {
        "metadata": {
            "version": "5.17",
            "server": "Weblate",
            "domain": "example.com",
            "timestamp": "2026-04-10T12:00:00+00:00",
        },
        "project": {
            "name": "Test",
            "slug": "test",
            "web": "https://example.com/",
            "instructions": "",
            "access_control": 0,
            "language_aliases": "",
            "set_language_team": True,
            "use_shared_tm": True,
            "contribute_shared_tm": True,
            "translation_review": False,
            "source_review": False,
            "enable_hooks": True,
        },
        "labels": [],
    }
).encode()

FORMAT_EXTENSIONS = [
    ".po",
    ".json",
    ".xliff",
    ".xliff2",
    ".tbx",
    ".csv",
    ".xml",
    ".ini",
    ".properties",
    ".resx",
    ".ts",
    ".strings",
    ".ftl",
    ".toml",
    ".pyml",
]

SSH_KEY_LINE = "github.com ssh-ed25519 " + b64encode(b"weblate fuzz seed" * 4).decode()


def _consume_bytes(fdp: FuzzedDataProvider, max_length: int = 4096) -> bytes:
    return fdp.consume_bytes(min(max_length, fdp.remaining_bytes()))


def _consume_text(
    fdp: FuzzedDataProvider, max_length: int = 128, *, default: str = ""
) -> str:
    text = fdp.consume_unicode_no_surrogates(max_length)
    return text or default


def _consume_name(fdp: FuzzedDataProvider, default: str, max_length: int = 24) -> str:
    text = _consume_text(fdp, max_length=max_length, default=default)
    sanitized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in text.strip()
    )
    return sanitized.strip("-") or default


def _consume_branch_ref(fdp: FuzzedDataProvider) -> str:
    branch = _consume_name(fdp, "main", max_length=32)
    if fdp.consume_bool():
        return f"refs/heads/{branch}"
    return branch


def _build_github_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    base_url = f"https://github.com/{owner}/{slug}"
    repository = {
        "url": base_url,
        "name": slug,
        "owner": {"login": owner, "name": owner},
    }
    if fdp.consume_bool():
        repository.update(
            {
                "clone_url": f"{base_url}.git",
                "git_url": f"git://github.com/{owner}/{slug}.git",
                "ssh_url": f"git@github.com:{owner}/{slug}.git",
                "html_url": base_url,
            }
        )
    return {
        "repository": repository,
        "ref": _consume_branch_ref(fdp),
    }


def _build_gitea_like_payload(fdp: FuzzedDataProvider, host: str) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    base_url = f"https://{host}/{owner}/{slug}"
    return {
        "repository": {
            "html_url": base_url,
            "clone_url": f"{base_url}.git",
            "ssh_url": f"git@{host}:{owner}/{slug}.git",
            "full_name": f"{owner}/{slug}",
        },
        "ref": _consume_branch_ref(fdp),
    }


def _build_gitee_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    base_url = f"https://gitee.com/{owner}/{slug}"
    return {
        "repository": {
            "html_url": base_url,
            "git_http_url": f"{base_url}.git",
            "git_ssh_url": f"git@gitee.com:{owner}/{slug}.git",
            "git_url": f"git://gitee.com/{owner}/{slug}.git",
            "ssh_url": f"git@gitee.com:{owner}/{slug}.git",
            "path_with_namespace": f"{owner}/{slug}",
        },
        "ref": _consume_branch_ref(fdp),
    }


def _build_gitlab_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    base_url = f"https://gitlab.example.com/{owner}/{slug}"
    return {
        "repository": {
            "url": f"git@gitlab.example.com:{owner}/{slug}.git",
            "homepage": base_url,
            "git_http_url": f"{base_url}.git",
            "git_ssh_url": f"git@gitlab.example.com:{owner}/{slug}.git",
        },
        "project": {"path_with_namespace": f"{owner}/{slug}"},
        "ref": _consume_branch_ref(fdp),
    }


def _build_pagure_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    return {
        "topic": "git.receive",
        "msg": {
            "pagure_instance": "https://pagure.io/",
            "project_fullname": f"{owner}/{slug}",
            "branch": _consume_name(fdp, "main"),
        },
    }


def _build_azure_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    organization = _consume_name(fdp, "weblate")
    project = _consume_name(fdp, "project")
    repository = _consume_name(fdp, "weblate")
    repo_id = _consume_name(fdp, "repo-id")
    project_id = _consume_name(fdp, "project-id")
    return {
        "eventType": "git.push",
        "resource": {
            "remoteUrl": (
                f"https://dev.azure.com/{organization}/{project}/_git/{repository}"
            ),
            "refUpdates": [{"name": _consume_branch_ref(fdp)}],
            "repository": {
                "remoteUrl": (
                    f"https://dev.azure.com/{organization}/{project}/_git/{repository}"
                ),
                "name": repository,
                "id": repo_id,
                "project": {"name": project, "id": project_id},
            },
        },
    }


def _build_bitbucket_payload(fdp: FuzzedDataProvider) -> dict[str, object]:
    owner = _consume_name(fdp, "weblate")
    slug = _consume_name(fdp, "weblate")
    base_url = f"https://bitbucket.org/{owner}/{slug}"
    return {
        "repository": {
            "full_name": f"{owner}/{slug}",
            "links": {
                "html": {"href": base_url},
                "clone": [
                    {"href": f"{base_url}.git"},
                    {"href": f"git@bitbucket.org:{owner}/{slug}.git"},
                ],
            },
        },
        "push": {"changes": [{"new": {"name": _consume_name(fdp, "main")}}]},
    }


HOOK_BUILDERS = {
    "azure": _build_azure_payload,
    "bitbucket": _build_bitbucket_payload,
    "forgejo": lambda fdp: _build_gitea_like_payload(fdp, "forgejo.example.com"),
    "github": _build_github_payload,
    "gitea": lambda fdp: _build_gitea_like_payload(fdp, "gitea.example.com"),
    "gitee": _build_gitee_payload,
    "gitlab": _build_gitlab_payload,
    "pagure": _build_pagure_payload,
}


def _build_backup_archive(data: bytes) -> bytes:
    fdp = FuzzedDataProvider(data)
    buffer = BytesIO()
    compression = ZIP_DEFLATED if fdp.consume_bool() else ZIP_STORED
    member_names: list[str] = []

    # The backup module promotes zipfile warnings to errors, but for fuzzing we
    # intentionally want to synthesize duplicate members and let validation code
    # reject them later.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Duplicate name: .*",
            category=UserWarning,
            module="zipfile",
        )
        with ZipFile(buffer, "w", compression=compression) as archive:
            if fdp.consume_bool():
                archive.writestr(
                    "weblate-backup.json",
                    VALID_BACKUP_JSON
                    if fdp.consume_bool()
                    else _consume_bytes(fdp, 2048),
                )
                member_names.append("weblate-backup.json")
            if fdp.consume_bool():
                archive.writestr(
                    "weblate-memory.json",
                    VALID_MEMORY_JSON
                    if fdp.consume_bool()
                    else _consume_bytes(fdp, 2048),
                )
                member_names.append("weblate-memory.json")

            for _unused in range(fdp.consume_int_in_range(0, 4)):
                if member_names and fdp.consume_bool():
                    filename = fdp.pick_value_in_list(member_names)
                else:
                    filename = fdp.pick_value_in_list(
                        [
                            "components/test.json",
                            "components/../test.json",
                            "vcs/test/.git/config",
                            "vcs/test/.git/hooks/post-checkout",
                            f"{_consume_name(fdp, 'entry')}.txt",
                        ]
                    )
                    member_names.append(filename)
                archive.writestr(filename, _consume_bytes(fdp, 4096))

    return buffer.getvalue()


def _build_tmx_payload(fdp: FuzzedDataProvider) -> bytes:
    source = escape(_consume_text(fdp, max_length=128, default="Hello"))
    target = escape(_consume_text(fdp, max_length=128, default="Ahoj"))
    source_language = fdp.pick_value_in_list(["en", "en_US", "cs", "de"])
    target_language = fdp.pick_value_in_list(["cs", "de", "fr", "es"])
    if not fdp.consume_bool():
        return _consume_bytes(fdp, 2048)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<tmx version="1.4">'
        f'<header srclang="{source_language}" />'
        "<body>"
        "<tu>"
        f'<tuv xml:lang="{source_language}"><seg>{source}</seg></tuv>'
        f'<tuv xml:lang="{target_language}"><seg>{target}</seg></tuv>'
        "</tu>"
        "</body>"
        "</tmx>"
    ).encode()


def _is_invalid_iso_timestamp(error: ValueError) -> bool:
    return any(isinstance(arg, str) and "isoformat" in arg for arg in error.args)


def fuzz_translation_formats(data: bytes) -> None:
    _bootstrap_targets()

    from weblate.formats.auto import try_load

    fdp = FuzzedDataProvider(data)
    filename = (
        f"{_consume_name(fdp, 'input')}{fdp.pick_value_in_list(FORMAT_EXTENSIONS)}"
    )
    content = _consume_bytes(fdp, 16 * 1024) or b"\n"

    try:
        store = try_load(filename, content, None, None)
        list(store.iterate_merge(""))
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        ParseException,
        SyntaxError,
        TypeError,
        TranslateToolkitParseError,
        UnicodeDecodeError,
        ValueError,
        XMLSyntaxError,
    ):
        pass


def fuzz_webhooks(data: bytes) -> None:
    _bootstrap_targets()

    from weblate.trans.views.hooks import (
        HOOK_HANDLERS,
        HookPayloadError,
        extract_payload,
    )

    fdp = FuzzedDataProvider(data)
    service = fdp.pick_value_in_list(sorted(HOOK_BUILDERS))
    payload = HOOK_BUILDERS[service](fdp)
    serialized = json.dumps(payload).encode()

    with contextlib.suppress(ParseError, UnicodeDecodeError):
        extract_payload(
            {
                "payload": (
                    serialized
                    if fdp.consume_bool()
                    else serialized + _consume_bytes(fdp, 8)
                )
            }
        )

    with contextlib.suppress(HookPayloadError, TypeError, ValueError):
        HOOK_HANDLERS[service](payload, None)


def fuzz_backups(data: bytes) -> None:
    _bootstrap_targets()

    from weblate.trans.backups import ProjectBackup

    archive_bytes = _build_backup_archive(data)
    backup = ProjectBackup(fileio=BytesIO(archive_bytes))

    with ZipFile(BytesIO(archive_bytes), "r") as archive:
        with contextlib.suppress(ValueError, ValidationError):
            backup.validate_zip_members(archive)

        try:
            with contextlib.suppress(
                json.JSONDecodeError,
                JSONSchemaValidationError,
                KeyError,
                TypeError,
                UnicodeDecodeError,
            ):
                backup.load_data(archive)
        # Invalid timestamps in fuzzed backup metadata are expected malformed input.
        # Keep other ValueError cases visible so the harness still catches real bugs.
        except ValueError as error:
            if not _is_invalid_iso_timestamp(error):
                raise

        with contextlib.suppress(
            json.JSONDecodeError,
            JSONSchemaValidationError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
        ):
            backup.load_memory(archive)


def fuzz_markup(data: bytes) -> None:
    _bootstrap_markdown()

    from weblate.checks.markup import XMLTagsCheck, XMLValidityCheck
    from weblate.utils.markdown import render_markdown
    from weblate.utils.xml import parse_xml

    fdp = FuzzedDataProvider(data)
    source = _consume_text(fdp, max_length=512, default="<b>Hello</b>")
    target = _consume_text(fdp, max_length=512, default=source)
    xml_input = _consume_bytes(fdp, 2048) or source.encode()

    with contextlib.suppress(SyntaxError, ValueError, XMLSyntaxError):
        parse_xml(xml_input)

    for check in (XMLValidityCheck(), XMLTagsCheck()):
        with contextlib.suppress(SyntaxError, ValueError, XMLSyntaxError):
            check.check_single(source, target, None)  # type: ignore[arg-type]

    render_markdown(target)


def fuzz_memory_import(data: bytes) -> None:
    _bootstrap_targets()

    from weblate.memory.models import load_memory_json_data, load_memory_tmx_store

    fdp = FuzzedDataProvider(data)
    mode = fdp.pick_value_in_list(["json", "tmx"])

    if mode == "json":
        payload = VALID_MEMORY_JSON if fdp.consume_bool() else _consume_bytes(fdp, 2048)
        try:
            load_memory_json_data(payload)
        except (
            json.JSONDecodeError,
            JSONSchemaValidationError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ):
            return
        return

    try:
        store = load_memory_tmx_store(BytesIO(_build_tmx_payload(fdp)))
        list(store.units)
    except (
        AssertionError,
        SyntaxError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        XMLSyntaxError,
    ):
        pass


def fuzz_ssh(data: bytes) -> None:
    _bootstrap_targets()

    from weblate.vcs.ssh import extract_url_host_port, parse_hosts_line

    fdp = FuzzedDataProvider(data)
    if fdp.consume_bool():
        line = _consume_text(fdp, max_length=256, default=SSH_KEY_LINE)
        try:
            parse_hosts_line(line)
        except (BinasciiError, TypeError, ValueError):
            return
        return

    url = _consume_text(
        fdp,
        max_length=256,
        default="ssh://git@example.com:2222/weblate/weblate.git",
    )
    extract_url_host_port(url)


TARGETS = {
    "backups": fuzz_backups,
    "markup": fuzz_markup,
    "memory_import": fuzz_memory_import,
    "ssh": fuzz_ssh,
    "translation_formats": fuzz_translation_formats,
    "webhooks": fuzz_webhooks,
}
