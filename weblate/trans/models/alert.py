# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.template.loader import render_to_string
from django.utils.encoding import force_text, python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from weblate.utils.fields import JSONField

ALERTS = {}
ALERTS_IMPORT = set()


def register(cls):
    name = cls.__name__
    ALERTS[name] = cls
    if cls.on_import:
        ALERTS_IMPORT.add(name)
    return cls


@python_2_unicode_compatible
class Alert(models.Model):
    component = models.ForeignKey('Component', on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=150)
    details = JSONField(default={})

    class Meta(object):
        unique_together = ('component', 'name')

    @cached_property
    def obj(self):
        return ALERTS[self.name](self, **self.details)

    def __str__(self):
        return force_text(self.obj.verbose)

    def render(self):
        return self.obj.render()

    def save(self, *args, **kwargs):
        is_new = not self.id
        super(Alert, self).save(*args, **kwargs)
        if is_new:
            from weblate.trans.models import Change

            Change.objects.create(
                action=Change.ACTION_ALERT,
                component=self.component,
                alert=self,
                details={'alert': self.name},
            )


class BaseAlert(object):
    verbose = ''
    on_import = False

    def __init__(self, instance):
        self.instance = instance

    def get_context(self):
        result = {
            'alert': self.instance,
            'component': self.instance.component,
            'timestamp': self.instance.timestamp,
            'details': self.instance.details,
        }
        result.update(self.instance.details)
        return result

    def render(self):
        return render_to_string(
            'trans/alert/{}.html'.format(self.__class__.__name__.lower()),
            self.get_context(),
        )


class ErrorAlert(BaseAlert):
    def __init__(self, instance, error):
        super(ErrorAlert, self).__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    def __init__(self, instance, occurrences):
        super(MultiAlert, self).__init__(instance)
        self.occurrences = self.process_occurrences(occurrences)

    def get_context(self):
        result = super(MultiAlert, self).get_context()
        result['occurrences'] = self.occurrences
        return result

    def process_occurrences(self, occurrences):
        from weblate.lang.models import Language
        from weblate.trans.models import Unit

        processors = (
            ('language_code', 'language', Language, 'code'),
            ('unit_pk', 'unit', Unit, 'pk'),
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
    verbose = _('Duplicated string found in the file.')
    on_import = True


@register
class DuplicateLanguage(MultiAlert):
    # Translators: Name of an alert
    verbose = _('Duplicated translation.')
    on_import = True


@register
class MergeFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _('Could not merge the repository.')


@register
class UpdateFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _('Could not update the repository.')


@register
class PushFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = _('Could not push the repository.')


@register
class ParseError(MultiAlert):
    # Translators: Name of an alert
    verbose = _('Could not parse translation files.')
    on_import = True


@register
class BillingLimit(BaseAlert):
    # Translators: Name of an alert
    verbose = _('Your billing plan has exceeded its limits.')


@register
class RepositoryOutdated(BaseAlert):
    # Translators: Name of an alert
    verbose = _('Repository outdated.')


@register
class RepositoryChanges(BaseAlert):
    # Translators: Name of an alert
    verbose = _('Repository has changes.')


@register
class MissingLicense(BaseAlert):
    # Translators: Name of an alert
    verbose = _('License info missing.')


@register
class AddonScriptError(MultiAlert):
    # Translators: Name of an alert
    verbose = _('Could not run addon.')


@register
class MsgmergeAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = _('Could not run addon.')


@register
class MonolingualTranslation(BaseAlert):
    # Translators: Name of an alert
    verbose = _('Misconfigured monolingual translation.')


@register
class UnsupportedConfiguration(BaseAlert):
    # Translators: Name of an alert
    verbose = _('Unsupported component configuration')

    def __init__(self, instance, vcs, file_format):
        super(UnsupportedConfiguration, self).__init__(instance)
        self.vcs = vcs
        self.file_format = file_format
