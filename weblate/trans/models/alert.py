#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.template.loader import render_to_string
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
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
        unique_together = ("component", "name")
        verbose_name = "component alert"
        verbose_name_plural = "component alerts"

    def __str__(self):
        return force_str(self.obj.verbose)

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

    def render(self):
        return self.obj.render()


class BaseAlert:
    verbose = ""
    on_import = False
    link_wide = False
    dismissable = False

    def __init__(self, instance):
        self.instance = instance

    def get_analysis(self):
        return {}

    def get_context(self):
        result = {
            "alert": self.instance,
            "component": self.instance.component,
            "timestamp": self.instance.timestamp,
            "details": self.instance.details,
            "analysis": self.get_analysis(),
        }
        result.update(self.instance.details)
        return result

    def render(self):
        return render_to_string(
            "trans/alert/{}.html".format(self.__class__.__name__.lower()),
            self.get_context(),
        )


class ErrorAlert(BaseAlert):
    def __init__(self, instance, error):
        super().__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    def __init__(self, instance, occurrences):
        super().__init__(instance)
        self.occurrences = self.process_occurrences(occurrences)

    def get_context(self):
        result = super().get_context()
        result["occurrences"] = self.occurrences
        return result

    def process_occurrences(self, occurrences):
        from weblate.lang.models import Language
        from weblate.trans.models import Unit

        processors = (
            ("language_code", "language", Language, "code"),
            ("unit_pk", "unit", Unit, "pk"),
        )
        for occurrence in occurrences:
            for key, target, obj, lookup in processors:
                if key not in occurrence:
                    continue
                try:
                    occurrence[target] = obj.objects.get(**{lookup: occurrence[key]})
                except ObjectDoesNotExist:
                    occurrence[target] = None
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
        result = {}
        source = self.instance.component.source_language
        for occurrence in self.occurrences:
            if occurrence["language"] == source:
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
    verbose = _("Duplicated filemask.")
    link_wide = True

    def __init__(self, instance, duplicates):
        super().__init__(instance)
        self.duplicates = duplicates


@register
class MergeFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not merge the repository.")
    link_wide = True


@register
class UpdateFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not update the repository.")
    link_wide = True


@register
class PushFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _("Could not push the repository.")
    link_wide = True


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


@register
class MissingLicense(BaseAlert):
    # Translators: Name of an alert
    verbose = _("License info missing.")


@register
class AddonScriptError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run addon.")


@register
class CDNAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run addon.")


@register
class MsgmergeAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = _("Could not run addon.")


@register
class MonolingualTranslation(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Misconfigured monolingual translation.")


@register
class UnsupportedConfiguration(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Unsupported component configuration")

    def __init__(self, instance, vcs, file_format):
        super().__init__(instance)
        self.vcs = vcs
        self.file_format = file_format


@register
class BrokenBrowserURL(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Broken repository browser URL")
    dismissable = True

    def __init__(self, instance, link, error):
        super().__init__(instance)
        self.link = link
        self.error = error


@register
class BrokenProjectURL(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Broken project website URL")
    dismissable = True

    def __init__(self, instance, error=None):
        super().__init__(instance)
        self.error = error


@register
class UnusedScreenshot(BaseAlert):
    # Translators: Name of an alert
    verbose = _("Unused screenshot")
