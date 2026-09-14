# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from translate.storage.po import pofile

from weblate.addons.gettext import MesonAddon, XgettextAddon
from weblate.addons.gettext_rules import GETTEXT_DATA_DIR, resolve_data_dirs
from weblate.trans.tests.test_views import ViewTestCase

if TYPE_CHECKING:
    from translate.storage.po import pounit

    from weblate.trans.models import Component


class ITSValidationTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.rules = self.root / "po" / "its"
        self.rules.mkdir(parents=True)
        for name in ("polkit.its", "polkit.loc"):
            shutil.copyfile(GETTEXT_DATA_DIR / "its" / name, self.rules / name)

    def test_valid_rules(self) -> None:
        self.assertEqual(resolve_data_dirs(self.root, ["po"]), [self.root / "po"])
        self.assertEqual(resolve_data_dirs(GETTEXT_DATA_DIR, ["."]), [GETTEXT_DATA_DIR])

    def test_invalid_paths(self) -> None:
        for names in (
            ["../outside"],
            [".."],
            [str(self.root)],
            ["po:other"],
            ["missing"],
            [1],
            "po",
        ):
            with self.subTest(names=names), self.assertRaises(ValidationError):
                resolve_data_dirs(self.root, names)

    def test_symlinks(self) -> None:
        (self.root / "linked").symlink_to(self.root / "po", target_is_directory=True)
        with self.assertRaises(ValidationError):
            resolve_data_dirs(self.root, ["linked"])
        target = self.rules / "polkit.its"
        target.unlink()
        target.symlink_to(GETTEXT_DATA_DIR / "its" / "polkit.its")
        with self.assertRaises(ValidationError):
            resolve_data_dirs(self.root, ["po"])

    def test_unsafe_or_invalid_rules(self) -> None:
        filename = self.rules / "polkit.its"
        for content in (
            '<!DOCTYPE rules SYSTEM "file:///etc/passwd"><rules/>',
            '<!DOCTYPE rules [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rules>&secret;</rules>',
            "<rules>",
            "<rules/>",
            '<its:rules xmlns:its="http://www.w3.org/2005/11/its" its:href="https://example.com/rules.its"/>',
            '<its:rules xmlns:its="http://www.w3.org/2005/11/its"><its:translateRule selector="[" translate="yes"/></its:rules>',
        ):
            with self.subTest(content=content):
                filename.write_text(content, encoding="utf-8")
                with self.assertRaises(ValidationError):
                    resolve_data_dirs(self.root, ["po"])

    def test_locating_rule_requires_target(self) -> None:
        (self.rules / "polkit.loc").write_text(
            '<locatingRules><locatingRule pattern="*.policy"/></locatingRules>',
            encoding="utf-8",
        )
        with self.assertRaisesMessage(ValidationError, "polkit.loc"):
            resolve_data_dirs(self.root, ["po"])

    def test_invalid_targets(self) -> None:
        filename = self.rules / "polkit.loc"
        for target in (
            "../polkit.its",
            str(self.rules / "polkit.its"),
            "https://example.com/rules.its",
            "missing.its",
        ):
            with self.subTest(target=target):
                filename.write_text(
                    f'<locatingRules><locatingRule pattern="*.policy" target="{target}"/></locatingRules>',
                    encoding="utf-8",
                )
                with self.assertRaises(ValidationError):
                    resolve_data_dirs(self.root, ["po"])


class ITSExtractionTest(ViewTestCase):
    def create_component(self) -> Component:
        return self.create_po_new_base(new_lang="add")

    def setUp(self) -> None:
        super().setUp()
        self.root = Path(self.component.full_path)
        self.sources = {
            "main.py": '_("Shared message")\n',
            "app.desktop": "[Desktop Entry]\nName=Desktop name\nComment=Shared message\nComment[de]=Localized desktop\n",
            "app.policy": '<policyconfig><action id="example"><description>Policy description</description><message>Shared message</message></action></policyconfig>',
            "app.metainfo.xml": "<component><id>example.app</id><name>Catalog name</name><summary>Shared message</summary></component>",
            "app.gschema.xml": '<schemalist><schema id="example.app"><key name="example" type="s"><summary>Setting summary</summary><description>Shared message</description><default l10n="messages" context="setting">"Setting default"</default></key></schema></schemalist>',
            "app.ui": '<interface><object class="GtkLabel"><property name="label" translatable="yes" context="label">UI label</property><property name="tooltip-text" translatable="yes">Shared message</property></object></interface>',
            "app.xml": '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info"><mime-type type="application/x-example"><comment>MIME description</comment></mime-type></mime-info>',
        }
        for name, content in self.sources.items():
            (self.root / name).write_text(content, encoding="utf-8")

    def create_addon(
        self, addon_class: type[XgettextAddon] = XgettextAddon, **configuration: object
    ) -> XgettextAddon:
        return addon_class.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "source_patterns": list(self.sources),
                **configuration,
            },
        )

    def read_template(self) -> list[pounit]:
        with (self.root / self.component.new_base).open("rb") as handle:
            return [unit for unit in pofile(handle).units if not unit.isheader()]

    def test_data_dirs_form_roundtrip(self) -> None:
        self.write_custom_rules("po", "//description")
        (self.root / "meson.build").write_text("", encoding="utf-8")
        (self.root / "po" / "meson.build").write_text("", encoding="utf-8")
        (self.root / "po" / "POTFILES").write_text("main.py", encoding="utf-8")
        for addon_class in (XgettextAddon, MesonAddon):
            with self.subTest(addon=addon_class.name):
                addon = self.create_addon(addon_class, data_dirs=["po"])
                form = addon.settings_form(
                    None,
                    addon,
                    data={
                        "interval": "weekly",
                        "source_patterns": "*.py",
                        "data_dirs": ["po"],
                        "preset": "glib",
                    },
                )
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["data_dirs"], ["po"])
                self.assertEqual(form["data_dirs"].value(), "po")
                addon.instance.delete()

    def test_mixed_extraction(self) -> None:
        for addon_class, input_mode in (
            (XgettextAddon, "patterns"),
            (XgettextAddon, "potfiles"),
            (MesonAddon, "potfiles"),
        ):
            with self.subTest(addon=addon_class.name, mode=input_mode):
                (self.root / "po" / "POTFILES").write_text(
                    "\n".join(self.sources), encoding="utf-8"
                )
                (self.root / "po" / "meson.build").write_text("", encoding="utf-8")
                addon = self.create_addon(
                    addon_class, input_mode=input_mode, potfiles_path="po/POTFILES"
                )
                self.assertTrue(
                    addon.execute_update(self.component, "", []), addon.alerts
                )
                entries = self.read_template()
                for message in (
                    "Desktop name",
                    "Policy description",
                    "Catalog name",
                    "Setting summary",
                    "UI label",
                    "MIME description",
                ):
                    self.assertIn(message, [entry.source for entry in entries])
                self.assertNotIn(
                    "Localized desktop", [entry.source for entry in entries]
                )
                shared = [
                    entry for entry in entries if entry.source == "Shared message"
                ]
                self.assertEqual(len(shared), 1)
                self.assertEqual(
                    {
                        name
                        for name, line in [
                            location.rsplit(":", 1)
                            for location in shared[0].getlocations()
                        ]
                    },
                    set(self.sources) - {"app.xml"},
                )
                self.assertEqual(
                    next(
                        entry for entry in entries if entry.source == "UI label"
                    ).getcontext(),
                    "label",
                )
                addon.instance.delete()

    def test_locations_and_skip(self) -> None:
        (self.root / "po" / "POTFILES").write_text(
            "\n".join(self.sources), encoding="utf-8"
        )
        (self.root / "po" / "POTFILES.skip").write_text(
            "app.policy\n", encoding="utf-8"
        )
        addon = self.create_addon(
            input_mode="potfiles", potfiles_path="po/POTFILES", location_mode="omit"
        )
        self.assertTrue(addon.execute_update(self.component, "", []), addon.alerts)
        entries = self.read_template()
        self.assertNotIn("Policy description", [entry.source for entry in entries])
        self.assertTrue(all(not entry.getlocations() for entry in entries))

    def write_custom_rules(self, directory: str, selector: str) -> None:
        rules = self.root / directory / "its"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / "polkit.loc").write_text(
            '<locatingRules><locatingRule pattern="*.policy" target="polkit.its"/><locatingRule pattern="*.custom" target="polkit.its"/></locatingRules>',
            encoding="utf-8",
        )
        (rules / "polkit.its").write_text(
            '<its:rules xmlns:its="http://www.w3.org/2005/11/its" version="2.0"><its:translateRule selector="//*" translate="no"/>'
            f'<its:translateRule selector="{selector}" translate="yes"/></its:rules>',
            encoding="utf-8",
        )

    def test_project_override_and_directory_order(self) -> None:
        self.write_custom_rules("first", "//description")
        self.write_custom_rules("second", "//message")
        (self.root / "app.custom").write_text(
            "<document><description>Custom format</description></document>",
            encoding="utf-8",
        )
        for directories, expected in (
            (["first", "second"], "Policy description"),
            (["second", "first"], "Shared message"),
        ):
            with self.subTest(directories=directories):
                addon = self.create_addon(
                    data_dirs=directories, source_patterns=["app.policy", "app.custom"]
                )
                self.assertTrue(
                    addon.execute_update(self.component, "", []), addon.alerts
                )
                messages = {entry.source for entry in self.read_template()}
                self.assertIn(expected, messages)
                self.assertNotIn(
                    "Shared message"
                    if expected == "Policy description"
                    else "Policy description",
                    messages,
                )
                self.assertEqual("Custom format" in messages, directories[0] == "first")
                addon.instance.delete()

    def test_rule_changes_are_relevant(self) -> None:
        self.write_custom_rules("po", "//description")
        addon = self.create_addon(data_dirs=["po"])
        revision = self.component.repository.last_revision
        addon.mark_successful_run(self.component, revision)
        for changed in (
            "po/its/new.loc",
            "po/its/polkit.its",
            "app.desktop",
            "app.policy",
        ):
            with self.subTest(changed=changed):
                self.assertTrue(
                    addon.has_relevant_changes(self.component, revision, [changed])
                )
        self.assertFalse(
            addon.has_relevant_changes(self.component, revision, ["README"])
        )
        (self.root / "po" / "its" / "polkit.its").unlink()
        addon = XgettextAddon(addon.instance)
        self.assertTrue(addon.has_relevant_changes(self.component, revision, []))

    def test_invalid_rules_leave_template_and_success_state_unchanged(self) -> None:
        addon = self.create_addon(data_dirs=["missing"])
        before = (self.root / self.component.new_base).read_bytes()
        with (
            patch.object(addon, "run_process") as process,
            patch.object(addon, "get_msgmerge_addon") as merge,
        ):
            addon.update_translations(self.component, "", [])
        process.assert_not_called()
        merge.assert_not_called()
        self.assertTrue(self.component.alert_set.filter(name=addon.alert).exists())
        self.assertEqual((self.root / self.component.new_base).read_bytes(), before)
        self.assertFalse(addon.successful_components)
        self.assertFalse(addon.pending_successful_revisions)

    def test_bundled_rule_changes_invalidate_success_state(self) -> None:
        (self.root / "po/POTFILES").write_text("main.py\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            shutil.copytree(GETTEXT_DATA_DIR / "its", bundle / "its")
            rule = bundle / "its/polkit.its"
            added = bundle / "its/new.loc"
            renamed = bundle / "its/renamed.loc"
            with patch("weblate.addons.gettext.GETTEXT_DATA_DIR", bundle):
                for addon_class in (XgettextAddon, MesonAddon):
                    with self.subTest(addon=addon_class.name):
                        addon = self.create_addon(
                            addon_class, potfiles_path="po/POTFILES"
                        )
                        revision = self.component.repository.last_revision
                        addon.mark_successful_run(self.component, revision)
                        self.assertFalse(
                            addon.has_relevant_changes(self.component, revision, [])
                        )
                        (bundle / "README.md").write_text(
                            "Documentation", encoding="utf-8"
                        )
                        self.assertFalse(
                            addon.has_relevant_changes(self.component, revision, [])
                        )
                        for change in ("content", "add", "rename", "remove"):
                            with self.subTest(change=change):
                                if change == "content":
                                    rule.write_bytes(rule.read_bytes() + b"\n")
                                elif change == "add":
                                    added.write_bytes(b"<locatingRules/>")
                                elif change == "rename":
                                    added.rename(renamed)
                                else:
                                    renamed.unlink()
                                self.assertTrue(
                                    addon.has_relevant_changes(
                                        self.component, revision, []
                                    )
                                )
                                addon.mark_successful_run(self.component, revision)
                                self.assertFalse(
                                    addon.has_relevant_changes(
                                        self.component, revision, []
                                    )
                                )
                        signature = addon.get_last_successful_configuration_signature(
                            self.component
                        )
                        rule.write_bytes(rule.read_bytes() + b"\n")
                        with (
                            patch.object(addon, "is_schedule_due", return_value=True),
                            patch.object(
                                addon, "execute_update", return_value=False
                            ) as execute,
                        ):
                            addon.update_translations(self.component, revision, [])
                        execute.assert_called_once()
                        self.assertEqual(
                            addon.get_last_successful_configuration_signature(
                                self.component
                            ),
                            signature,
                        )
                        self.assertFalse(addon.pending_successful_revisions)
                        self.assertTrue(
                            addon.has_relevant_changes(self.component, revision, [])
                        )
                        addon.instance.delete()
