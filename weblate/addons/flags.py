# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_UNIT_PRE_CREATE
from weblate.addons.forms import BulkEditAddonForm
from weblate.trans.bulk import bulk_perform
from weblate.trans.models import Unit
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED


class FlagBase(BaseAddon):
    events = (EVENT_UNIT_PRE_CREATE,)
    icon = "flag.svg"

    @classmethod
    def can_install(cls, component, user):
        # Following formats support fuzzy flag, so avoid messing up with them
        if component.file_format in {"ts", "po", "po-mono"}:
            return False
        return super().can_install(component, user)


class SourceEditAddon(FlagBase):
    name = "weblate.flags.source_edit"
    verbose = _('Flag new source strings as "Needs editing"')
    description = _(
        "Whenever a new source string is imported from the VCS, it is "
        "flagged as needing editing in Weblate. This way you can easily "
        "filter and edit source strings written by the developers."
    )
    compat = {
        "edit_template": {True},
    }

    def unit_pre_create(self, unit):
        if (
            unit.translation.is_template
            and unit.state >= STATE_TRANSLATED
            and not unit.readonly
        ):
            unit.state = STATE_FUZZY


class TargetEditAddon(FlagBase):
    name = "weblate.flags.target_edit"
    verbose = _('Flag new translations as "Needs editing"')
    description = _(
        "Whenever a new translatable string is imported from the VCS, it is "
        "flagged as needing editing in Weblate. This way you can easily "
        "filter and edit translations created by the developers."
    )

    def unit_pre_create(self, unit):
        if (
            not unit.translation.is_template
            and unit.state >= STATE_TRANSLATED
            and not unit.readonly
        ):
            unit.state = STATE_FUZZY


class SameEditAddon(FlagBase):
    name = "weblate.flags.same_edit"
    verbose = _('Flag unchanged translations as "Needs editing"')
    description = _(
        "Whenever a new translatable string is imported from the VCS and it matches a "
        "source string, it is flagged as needing editing in Weblate. Especially "
        "useful for file formats that include source strings for untranslated strings."
    )

    def unit_pre_create(self, unit):
        if (
            not unit.translation.is_template
            and unit.source == unit.target
            and "ignore-same" not in unit.all_flags
            and unit.state >= STATE_TRANSLATED
            and not unit.readonly
        ):
            unit.state = STATE_FUZZY


class BulkEditAddon(BaseAddon):
    events = (EVENT_COMPONENT_UPDATE,)
    name = "weblate.flags.bulk"
    verbose = _("Bulk edit")
    description = _("Bulk edit flags, labels, or states of strings.")
    settings_form = BulkEditAddonForm
    multiple = True

    def component_update(self, component):
        label_set = component.project.label_set
        bulk_perform(
            None,
            Unit.objects.filter(translation__component=component),
            components=[component],
            query=self.instance.configuration["q"],
            target_state=self.instance.configuration["state"],
            add_flags=self.instance.configuration["add_flags"],
            remove_flags=self.instance.configuration["remove_flags"],
            add_labels=label_set.filter(
                name__in=self.instance.configuration["add_labels"]
            ),
            remove_labels=label_set.filter(
                name__in=self.instance.configuration["remove_labels"]
            ),
            project=component.project,
        )
