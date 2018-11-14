# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.db import models
from django.template.loader import render_to_string
from django.utils.encoding import python_2_unicode_compatible, force_text
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
    component = models.ForeignKey(
        'Component', on_delete=models.deletion.CASCADE
    )
    timestamp = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=150)
    details = JSONField(default={})

    class Meta(object):
        ordering = ['name']
        unique_together = ('component', 'name')

    @cached_property
    def obj(self):
        return ALERTS[self.name](self, **self.details)

    def __str__(self):
        return force_text(self.obj.verbose)

    def render(self):
        return self.obj.render()


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
            self.get_context()
        )


class ErrorAlert(BaseAlert):
    def __init__(self, instance, error):
        super(ErrorAlert, self).__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    def __init__(self, instance, occurences):
        super(MultiAlert, self).__init__(instance)
        self.occurences = self.process_occurences(occurences)

    def get_context(self):
        result = super(MultiAlert, self).get_context()
        result['occurences'] = self.occurences
        return result

    def process_occurences(self, occurences):
        from weblate.lang.models import Language
        from weblate.trans.models import Unit
        processors = (
            ('language_code', 'language', Language, 'code'),
            ('unit_pk', 'unit', Unit, 'pk'),
        )
        for occurence in occurences:
            for key, target, obj, lookup in processors:
                if key not in occurence:
                    continue
                try:
                    occurence[target] = obj.objects.get(
                        **{lookup: occurence[key]}
                    )
                except Language.DoesNotExist:
                    occurence[target] = None
        return occurences


@register
class DuplicateString(MultiAlert):
    verbose = _('Duplicated string for translation.')
    on_import = True


@register
class DuplicateLanguage(MultiAlert):
    verbose = _('Duplicated translation.')
    on_import = True


@register
class MergeFailure(ErrorAlert):
    verbose = _('Could not merge the repository.')


@register
class UpdateFailure(ErrorAlert):
    verbose = _('Could not update the repository.')


@register
class UnusedNewBase(BaseAlert):
    verbose = _('Unused base file for new translations.')


@register
class ParseError(MultiAlert):
    verbose = _('Could not parse translation files.')
    on_import = True


@register
class BillingLimit(BaseAlert):
    verbose = _('Your billing plan has exceeded its limits.')


@register
class RepositoryOutdated(BaseAlert):
    verbose = _('Repository outdated.')


@register
class RepositoryChanges(BaseAlert):
    verbose = _('Repository has changes.')
