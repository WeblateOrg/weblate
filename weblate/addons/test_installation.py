# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise the installation lifecycle of every default add-on."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from unittest.mock import patch

from django.db import transaction
from django.http import QueryDict
from django.test import SimpleTestCase, override_settings
from fedora_messaging.config import LazyConfig

from weblate.addons.defaults import DEFAULT_WEBLATE_ADDONS
from weblate.addons.models import ADDONS, Addon
from weblate.machinery.models import MachineryInstallation
from weblate.machinery.openai import OpenAITranslation
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Component
from weblate.trans.tests.test_views import ReusableComponentTestCase
from weblate.utils.change_origin import acting_user_context
from weblate.utils.unittest import tempdir_setting

if TYPE_CHECKING:
    from weblate.addons.forms import BaseAddonForm


@dataclass(frozen=True)
class InstallationCase:
    configuration: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] | None = None
    fixture: str = "po"
    scope: Literal["component", "project", "site"] = "component"


EXTRACTION_CONFIGURATION = {
    "interval": "weekly",
    "normalize_header": False,
    "location_mode": "file",
}
XGETTEXT_CONFIGURATION = {
    **EXTRACTION_CONFIGURATION,
    "comment_mode": "all",
    "comment_tag": "",
    "checks": [],
    "data_dirs": [],
    "keyword": [],
    "keyword_exclusive": False,
}
WORKFLOW = {"version": 1, "triggers": [], "actions": []}

# Keep this explicit: each new built-in needs valid input and a supported fixture.
INSTALLATION_CASES = {
    "weblate.automation.automation": InstallationCase({"workflow": WORKFLOW}),
    "weblate.gettext.mo": InstallationCase({"path": "", "fuzzy": True}),
    "weblate.gettext.linguas": InstallationCase(),
    "weblate.gettext.configure": InstallationCase(),
    "weblate.gettext.msgmerge": InstallationCase(),
    "weblate.gettext.xgettext": InstallationCase(
        {
            **XGETTEXT_CONFIGURATION,
            "input_mode": "patterns",
            "language": "Python",
            "source_patterns": ["src/*.py"],
            "potfiles_path": "",
        },
        fixture="xgettext",
    ),
    "weblate.gettext.meson": InstallationCase(
        {**XGETTEXT_CONFIGURATION, "preset": "glib"}, fixture="meson"
    ),
    "weblate.gettext.django": InstallationCase(
        EXTRACTION_CONFIGURATION, fixture="django"
    ),
    "weblate.gettext.sphinx": InstallationCase(
        {**EXTRACTION_CONFIGURATION, "filter_mode": "none"}, fixture="sphinx"
    ),
    "weblate.cleanup.generic": InstallationCase(fixture="json_mono"),
    "weblate.cleanup.blank": InstallationCase(fixture="json_mono"),
    "weblate.hosted.reset": InstallationCase(fixture="sandbox"),
    "weblate.consistency.languages": InstallationCase(
        data={"confirm": True}, scope="project"
    ),
    "weblate.discovery.discovery": InstallationCase(
        {
            "match": r"(?P<component>po)/(?P<language>[^/.]*)\.po",
            "file_format": "po",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "filemask_template": "",
            "language_regex": "^[^.]+$",
            "copy_addons": False,
            "remove": False,
        }
    ),
    "weblate.autotranslate.autotranslate": InstallationCase(
        {
            "mode": "suggest",
            "q": "state:<translated",
            "auto_source": "others",
            "component": None,
            "engines": [],
            "threshold": 80,
        }
    ),
    "weblate.ai.quality": InstallationCase(
        {
            "service": OpenAITranslation.get_identifier(),
            "q": "state:>=translated",
            "interval": "weekly",
            "on_change": False,
            "on_update": False,
        }
    ),
    "weblate.flags.source_edit": InstallationCase(fixture="json_mono"),
    "weblate.flags.target_edit": InstallationCase(fixture="json_mono"),
    "weblate.flags.same_edit": InstallationCase(fixture="json_mono"),
    "weblate.flags.bulk": InstallationCase(
        {
            "q": "state:empty",
            "state": "-1",
            "search": "",
            "replacement": "",
            "search_type": "text",
            "path": "",
            "add_flags": "",
            "remove_flags": "",
            "add_translation_flags": "",
            "remove_translation_flags": "",
            "add_labels": [],
            "remove_labels": [],
        }
    ),
    "weblate.flags.target_repo_update": InstallationCase(),
    "weblate.generate.generate": InstallationCase(
        {
            "scope": "translation",
            "filename": "stats/{{ language_code }}.json",
            "template": '{"code":"{{ language_code }}"}',
        }
    ),
    "weblate.generate.pseudolocale": InstallationCase(
        {
            "prefix": "[",
            "suffix": "]",
            "var_prefix": "",
            "var_suffix": "",
            "var_multiplier": 0.1,
            "include_readonly": False,
        }
    ),
    "weblate.generate.prefill": InstallationCase(),
    "weblate.generate.fill_read_only": InstallationCase(),
    "weblate.properties.sort": InstallationCase(
        {"case_sensitive": True}, fixture="java"
    ),
    "weblate.git.squash": InstallationCase(
        {"squash": "language", "append_trailers": True, "commit_message": ""}
    ),
    "weblate.removal.comments": InstallationCase({"age": 30}),
    "weblate.removal.suggestions": InstallationCase({"age": 30, "votes": None}),
    "weblate.resx.update": InstallationCase(fixture="resx"),
    "weblate.cdn.cdnjs": InstallationCase(
        {
            "threshold": 50,
            "css_selector": "[data-i18n]",
            "cookie_name": "",
            "files": "",
        },
        fixture="json_mono",
    ),
    "weblate.cdn.files": InstallationCase(fixture="json_mono"),
    "weblate.cdn.kotlin": InstallationCase(
        {"maximum_age": 365, "maximum_versions": 20}, fixture="android"
    ),
    "weblate.webhook.webhook": InstallationCase(
        {
            "webhook_url": "https://example.com/webhook",
            "event_filter": "content",
            "events": [],
            "secret": "",
        }
    ),
    "weblate.webhook.slack": InstallationCase(
        {
            "webhook_url": "https://example.com/slack",
            "event_filter": "content",
            "events": [],
        }
    ),
    "weblate.fedora_messaging.publish": InstallationCase(
        {
            "amqp_url": "amqp://guest:guest@example.com:5672/%2F",
            "topic_prefix": "weblate",
            "ca_cert": "",
            "client_key": "",
            "client_cert": "",
            "publish_timeout": 5,
            "connection_attempts": 1,
            "retry_delay": 2,
            "event_filter": "content",
            "events": [],
        },
        scope="site",
    ),
}


@override_settings(WEBLATE_ADDONS=DEFAULT_WEBLATE_ADDONS)
class InstallationCoverageTest(SimpleTestCase):
    def test_registry_coverage(self) -> None:
        self.assertEqual(set(INSTALLATION_CASES), set(ADDONS))


@override_settings(
    WEBLATE_ADDONS=DEFAULT_WEBLATE_ADDONS,
    LOCALIZE_CDN_URL="https://cdn.example.com/",
)
class AddonInstallationTest(ReusableComponentTestCase):
    def create_component(self) -> Component:
        return self.create_po_new_base(new_lang="add")

    def prepare_component(self, fixture: str) -> Component:
        if fixture == "sandbox":
            return self.create_po_new_base(
                project=self.create_project(name="Sandbox", slug="sandbox"),
                new_lang="add",
            )
        if fixture == "resx":
            return self._create_component(
                "resx",
                "resx/*.resx",
                "resx/en.resx",
                project=self.project,
                name=fixture,
            )
        if fixture in {"json_mono", "java", "android"}:
            return getattr(self, f"create_{fixture}")(
                project=self.project,
                name=fixture,
                **({"edit_template": True} if fixture == "json_mono" else {}),
            )
        component = Component.objects.get(pk=self.component.pk)
        self.enterContext(acting_user_context(self.user))
        root = Path(component.full_path)
        if fixture in {"xgettext", "meson"}:
            (root / "src").mkdir(exist_ok=True)
            (root / "src/messages.py").write_text(
                'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
            )
            if fixture == "meson":
                (root / "meson.build").write_text("project('test')\n", encoding="utf-8")
                (root / "po/meson.build").write_text(
                    "i18n.gettext('test')\n", encoding="utf-8"
                )
                (root / "po/POTFILES").write_text("src/messages.py\n", encoding="utf-8")
        elif fixture in {"django", "sphinx"}:
            new_base = (
                "locale/django.pot" if fixture == "django" else "docs/locales/test.pot"
            )
            destination = root / new_base
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((root / component.new_base).read_bytes())
            if fixture == "sphinx":
                (root / "docs/conf.py").write_text(
                    "project = 'Test'\n", encoding="utf-8"
                )
            Component.objects.filter(pk=component.pk).update(new_base=new_base)
            component.refresh_from_db()
        return component

    def check_installation(self, name: str, case: InstallationCase) -> None:
        component = self.prepare_component(case.fixture)
        scope: dict[str, Any] = {}
        if case.scope == "project":
            scope["project"] = component.project
        elif case.scope == "component":
            scope["component"] = component
        addon_class = ADDONS[name]
        self.assertTrue(addon_class.can_install(**scope))
        configuration = case.configuration.copy()
        if name == "weblate.generate.pseudolocale":
            configuration.update(
                source=component.source_translation.pk,
                target=component.translation_set.get(language_code="cs").pk,
            )
        data = QueryDict(mutable=True)
        for key, value in (
            case.data if case.data is not None else configuration
        ).items():
            if isinstance(value, list):
                data.setlist(key, [str(item) for item in value])
            elif isinstance(value, dict):
                data[key] = json.dumps(value)
            elif value is not None:
                data[key] = (
                    str(value)
                    if not isinstance(value, bool)
                    else ("on" if value else "")
                )
        if name == "weblate.discovery.discovery":
            data["confirm"] = "on"
        form: BaseAddonForm | None = addon_class.get_add_form(
            self.user, **scope, data=data
        )
        if form is None:
            storage = addon_class.create(acting_user=self.user, **scope).instance
        else:
            self.assertIsNone(form._addon.instance.pk)  # ruff: ignore[private-member-access]
            self.assertTrue(form.is_valid(), form.errors)
            storage = form.save()
        self.assertIsNotNone(storage.pk)
        storage = Addon.objects.get(pk=storage.pk)
        self.assertEqual(storage.name, name)
        self.assertEqual(
            Change.objects.get(addon=storage, action=ActionEvents.ADDON_CREATE).user,
            self.user,
        )
        self.assertEqual(storage.configuration, configuration)
        self.assertEqual(
            storage.component_id, component.pk if case.scope == "component" else None
        )
        self.assertEqual(
            storage.project_id,
            component.project_id if case.scope == "project" else None,
        )
        self.assertIsNone(storage.category_id)
        self.assertEqual(
            set(storage.event_set.values_list("event", flat=True)),
            storage.addon.configured_events,
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_installations(self) -> None:
        with (
            patch("weblate.addons.tasks.postconfigure_addon"),
            patch("fedora_messaging.config.conf", LazyConfig()),
            patch(
                "weblate.addons.fedora_messaging.FedoraMessagingAddon._reset_fedora_messaging_service",
                return_value=True,
            ),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
            ),
            patch.object(OpenAITranslation, "fetch_llm_translations") as fetch,
        ):
            for name, case in INSTALLATION_CASES.items():
                with self.subTest(addon=name), transaction.atomic():
                    MachineryInstallation.objects.create(
                        project=self.project,
                        engine=OpenAITranslation.get_identifier(),
                        configuration={"key": "test", "model": "gpt-4o-mini"},
                    )
                    self.check_installation(name, case)
                    # Each case installs from an empty add-on state.
                    transaction.set_rollback(True)
            fetch.assert_not_called()
