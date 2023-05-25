#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from collections import defaultdict

from django.db import models
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from weblate_language_data.ambiguous import AMBIGUOUS
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.utils.fields import JSONField

ALERTS = {}
ALERTS_IMPORT = set()


def register(cls):
    name = cls.__name__
    ALERTS[name] = cls
    if cls.on_import:
        ALERTS_IMPORT.add(name)
    return cls


class Alert(models.Model):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=150)
    dismissed = models.BooleanField(default=False, db_index=True)
    details = JSONField(default={})

    class Meta:
        unique_together = [("component", "name")]
        verbose_name = "component alert"
        verbose_name_plural = "component alerts"

    def __str__(self):
        return str(self.obj.verbose)

    def save(self, *args, **kwargs):
        is_new = not self.id
        super().save(*args, **kwargs)
        if is_new:
            from weblate.trans.models import Change

            Change.objects.create(
                action=Change.ACTION_ALERT,
                component=self.component,
                alert=self,
                details={"alert": self.name},
            )

    @cached_property
    def obj(self):
        return ALERTS[self.name](self, **self.details)

    def render(self, user):
        return self.obj.render(user)


class BaseAlert:
    verbose = ""
    on_import = False
    link_wide = False
    project_wide = False
    dismissable = False
    doc_page = ""
    doc_anchor = ""

    def __init__(self, instance):
        self.instance = instance

    def get_analysis(self):
        return {}

    def get_context(self, user):
        result = {
            "alert": self.instance,
            "component": self.instance.component,
            "timestamp": self.instance.timestamp,
            "details": self.instance.details,
            "analysis": self.get_analysis(),
            "user": user,
        }
        result.update(self.instance.details)
        return result

    def render(self, user):
        return render_to_string(
            f"trans/alert/{self.__class__.__name__.lower()}.html",
            self.get_context(user),
        )


class ErrorAlert(BaseAlert):
    def __init__(self, instance, error):
        super().__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    occurrences_limit = 100

    def __init__(self, instance, occurrences):
        super().__init__(instance)
        self.occurrences = self.process_occurrences(
            occurrences[: self.occurrences_limit]
        )
        self.total_occurrences = len(occurrences)
        self.missed_occurrences = self.total_occurrences > self.occurrences_limit

    def get_context(self, user):
        result = super().get_context(user)
        result["occurrences"] = self.occurrences
        result["total_occurrences"] = self.total_occurrences
        result["missed_occurrences"] = self.missed_occurrences
        return result

    def process_occurrences(self, occurrences):
        from weblate.lang.models import Language
        from weblate.trans.models import Unit

        processors = (
            ("language_code", "language", Language.objects.all(), "code"),
            ("unit_pk", "unit", Unit.objects.prefetch(), "pk"),
        )
        for key, target, base, lookup in processors:
            # Extract list to fetch
            updates = defaultdict(list)
            for occurrence in occurrences:
                if key not in occurrence:
                    continue

                updates[occurrence[key]].append(occurrence)

            if not updates:
                continue

            result = base.filter(**{f"{lookup}__in": updates.keys()})
            for match in result:
                for occurrence in updates[getattr(match, lookup)]:
                    occurrence[target] = match

        return occurrences


@register
class DuplicateString(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Duplicated string found in the file.")
    on_import = True


@register
class DuplicateLanguage(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Duplicated translation.")
    on_import = True

    def get_analysis(self):
        component = self.instance.component
        result = {"monolingual": bool(component.template)}
        source = component.source_language.code
        for occurrence in self.occurrences:
            if occurrence["language_code"] == source:
                result["source_language"] = True
            codes = {
                code.strip().replace("-", "_").lower()
                for code in occurrence["codes"].split(",")
            }
            if codes.intersection(DEFAULT_LANGS):
                result["default_country"] = True
        return result


@register
class DuplicateFilemask(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Duplicated file mask.")
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def __init__(self, instance, duplicates):
        super().__init__(instance)
        self.duplicates = duplicates


@register
class MergeFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not merge the repository.")
    link_wide = True
    doc_page = "faq"
    doc_anchor = "merge"


@register
class UpdateFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not update the repository.")
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-repo"


@register
class PushFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not push the repository.")
    link_wide = True
    behind_message = "The tip of your current branch is behind its remote counterpart"
    terminal_message = "terminal prompts disabled"
    doc_page = "admin/projects"
    doc_anchor = "component-push"

    def get_analysis(self):
        terminal_disabled = self.terminal_message in self.error
        repo_suggestion = None
        force_push_suggestion = False
        component = self.instance.component

        # Missing credentials
        if terminal_disabled:
            if component.push:
                if component.push.startswith("https://github.com/"):
                    repo_suggestion = f"git@github.com:{component.push[19:]}"
            elif component.repo.startswith("https://github.com/"):
                repo_suggestion = f"git@github.com:{component.repo[19:]}"

        # Missing commits
        behind = self.behind_message in self.error
        if behind:
            force_push_suggestion = (
                component.vcs == "git"
                and component.merge_style == "rebase"
                and component.bool(component.push_branch)
            )

        return {
            "terminal": terminal_disabled,
            "behind": behind,
            "repo_suggestion": repo_suggestion,
            "force_push_suggestion": force_push_suggestion,
        }


@register
class ParseError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not parse translation files.")
    on_import = True


@register
class BillingLimit(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Your billing plan has exceeded its limits.")


@register
class RepositoryOutdated(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Repository outdated.")
    link_wide = True


@register
class RepositoryChanges(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Repository has changes.")
    link_wide = True
    dismissable = True


@register
class MissingLicense(BaseAlert):
    # Translators: Name of an alert
    verbose = _("License info missing.")
    doc_page = "admin/projects"
    doc_anchor = "component-license"


@register
class AddonScriptError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run add-on.")
    doc_page = "adons"


@register
class CDNAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run add-on.")
    doc_page = "adons"
    doc_anchor = "addon-weblate-cdn-cdnjs"


@register
class MsgmergeAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run add-on.")
    doc_page = "adons"
    doc_anchor = "addon-weblate-gettext-msgmerge"


@register
class MonolingualTranslation(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Misconfigured monolingual translation.")
    doc_page = "formats"
    doc_anchor = "bimono"


@register
class UnsupportedConfiguration(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Unsupported component configuration")
    doc_page = "admin/projects"
    doc_anchor = "component"

    def __init__(self, instance, vcs, file_format):
        super().__init__(instance)
        self.vcs = vcs
        self.file_format = file_format


@register
class BrokenBrowserURL(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Broken repository browser URL")
    dismissable = True
    doc_page = "admin/projects"
    doc_anchor = "component-repoweb"

    def __init__(self, instance, link, error):
        super().__init__(instance)
        self.link = link
        self.error = error


@register
class BrokenProjectURL(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Broken project website URL")
    dismissable = True
    doc_page = "admin/projects"
    doc_anchor = "project-web"
    project_wide = True

    def __init__(self, instance, error=None):
        super().__init__(instance)
        self.error = error


@register
class UnusedScreenshot(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Unused screenshot")
    doc_page = "admin/translating"
    doc_anchor = "screenshots"


@register
class AmbiguousLanguage(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Ambiguous language code.")
    dismissable = True
    doc_page = "admin/languages"
    doc_anchor = "ambiguous-languages"

    def get_context(self, user):
        result = super().get_context(user)
        ambgiuous = self.instance.component.get_ambiguous_translations().values_list(
            "language__code", flat=True
        )
        result["ambiguous"] = {code: AMBIGUOUS[code] for code in ambgiuous}
        return result


@register
class NoLibreConditions(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Does not meet Libre hosting conditions.")


@register
class UnusedEnforcedCheck(BaseAlert):
    verbose = _("Unused enforced checks.")
    doc_page = "admin/checks"
    doc_anchor = "enforcing-checks"


@register
class NoMaskMatches(BaseAlert):
    verbose = _("No file mask matches.")
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def get_analysis(self):
        return {
            "can_add": self.instance.component.can_add_new_language(None, fast=True),
        }


@register
class InexistantFiles(BaseAlert):
    verbose = _("Inexistent files.")
    doc_page = "admin/projects"
    doc_anchor = "component-template"

    def __init__(self, instance, files):
        super().__init__(instance)
        self.files = files
