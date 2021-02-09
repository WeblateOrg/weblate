#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Change
from weblate.utils.docs import get_doc_url

GUIDELINES = []


def register(cls):
    GUIDELINES.append(cls)
    return cls


class Guideline:
    description = ""
    group = False
    url = ""
    anchor = ""

    def __init__(self, component):
        self.component = component
        self.passed = self.is_passing()

    def is_passing(self):
        raise NotImplementedError()

    def is_relevant(self):
        return True

    def get_url(self):
        url = reverse(self.url, kwargs=self.component.get_reverse_url_kwargs())
        if self.anchor:
            url = f"{url}#{self.anchor}"
        return url

    def get_doc_url(self, user=None):
        return ""


class Group(Guideline):
    group = True

    def is_passing(self):
        # Not used
        return False

    def get_url(self):
        # Not used
        return ""


@register
class VCSGroup(Group):
    description = _("Version control integration")

    def get_doc_url(self, user=None):
        return get_doc_url("vcs", user=user)


@register
class HookGuideline(Guideline):
    description = _(
        "Configure repository hooks for automated flow of updates to Weblate."
    )
    url = "settings"
    anchor = "vcs"

    def is_passing(self):
        return self.component.change_set.filter(action=Change.ACTION_HOOK).exists()

    def is_relevant(self):
        return not self.component.is_repo_link

    def get_url(self):
        return self.get_doc_url()

    def get_doc_url(self, user=None):
        return get_doc_url("admin/continuous", "update-vcs", user=user)


@register
class PushGuideline(Guideline):
    description = _(
        "Configure push URL for automated flow of translations from Weblate."
    )
    url = "settings"
    anchor = "vcs"

    def is_passing(self):
        return self.component.can_push()

    def get_doc_url(self, user=None):
        return get_doc_url("admin/continuous", "push-changes", user=user)


@register
class CommunityGroup(Group):
    description = _("Building community")

    def get_doc_url(self, user=None):
        return get_doc_url("devel/community", user=user)


@register
class InstructionsGuideline(Guideline):
    description = _("Define translation instructions to give translators a guideline.")

    def is_passing(self):
        return bool(self.component.project.instructions)

    def get_url(self):
        return reverse(
            "settings", kwargs=self.component.project.get_reverse_url_kwargs()
        )

    def get_doc_url(self, user=None):
        return get_doc_url("admin/projects", "project", user=user)


@register
class LicenseGuideline(Guideline):
    description = _("Make your translations available under a libre license.")
    url = "settings"
    anchor = "basic"

    def is_passing(self):
        return self.component.libre_license

    def get_doc_url(self, user=None):
        return "https://choosealicense.com/"


@register
class AlertGuideline(Guideline):
    description = _("Fix this component to clear its alerts.")
    url = "component"
    anchor = "alerts"

    def is_passing(self):
        return not self.component.all_alerts

    def get_doc_url(self, user=None):
        return get_doc_url("devel/alerts", user=user)


@register
class ContextGroup(Group):
    description = _("Provide context to the translators")

    def get_doc_url(self, user=None):
        return get_doc_url("admin/translating", "additional", user=user)


@register
class ScreenshotGuideline(Guideline):
    description = _("Add screenshots to show where strings are being used.")
    url = "screenshots"

    def is_passing(self):
        from weblate.screenshots.models import Screenshot

        return Screenshot.objects.filter(translation__component=self.component).exists()

    def get_doc_url(self, user=None):
        return get_doc_url("admin/translating", "screenshots", user=user)


@register
class FlagsGuideline(Guideline):
    description = _("Use flags to indicate special strings in your translation.")
    url = "settings"
    anchor = "translation"

    def is_passing(self):
        return (
            bool(self.component.check_flags)
            or self.component.source_translation.unit_set.exclude(
                extra_flags=""
            ).exists()
        )

    def get_doc_url(self, user=None):
        return get_doc_url("admin/checks", "custom-checks", user=user)


@register
class SafeHTMLGuideline(Guideline):
    description = _("Add safe-html flag to avoid dangerous HTML from translators.")
    url = "settings"
    anchor = "translation"

    def is_relevant(self):
        return self.component.source_translation.unit_set.filter(
            source__contains="<a "
        ).exists()

    def is_passing(self):
        return (
            "safe-html" in self.component.check_flags
            or self.component.source_translation.unit_set.filter(
                extra_flags__contains="safe-html"
            ).exists()
        )

    def get_doc_url(self, user=None):
        return get_doc_url("user/checks", "check-safe-html", user=user)


@register
class AddonsGroup(Group):
    description = _("Workflow customization")

    def get_doc_url(self, user=None):
        return get_doc_url("admin/addons", user=user)


class AddonGuideline(Guideline):
    addon = ""
    url = "addons"

    def is_passing(self):
        return (
            Addon.objects.filter_component(self.component)
            .filter(name=self.addon)
            .exists()
        )

    def is_relevant(self):
        if self.addon not in ADDONS:
            return False
        addon = ADDONS[self.addon]
        return addon.can_install(self.component, None)

    def get_doc_url(self, user=None):
        return get_doc_url(
            "admin/addons", ADDONS[self.addon].get_doc_anchor(), user=user
        )

    @property
    def description(self):
        return render_to_string(
            "trans/guide/addon.html",
            {
                "name": ADDONS[self.addon].verbose,
                "description": ADDONS[self.addon].description,
            },
        )


@register
class LanguageConsistencyGuideline(AddonGuideline):
    addon = "weblate.consistency.languages"

    def is_relevant(self):
        if self.component.project.component_set.exclude(is_glossary=True).count() <= 1:
            return False
        return super().is_relevant()


@register
class LinguasGuideline(AddonGuideline):
    addon = "weblate.gettext.linguas"


@register
class ConfigureGuideline(AddonGuideline):
    addon = "weblate.gettext.configure"
