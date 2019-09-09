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

import json

from appconf import AppConf
from django.db import IntegrityError, models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.checks import CHECKS
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.unitdata import UnitData


class WeblateChecksConf(AppConf):
    # List of quality checks
    CHECK_LIST = (
        'weblate.checks.same.SameCheck',
        'weblate.checks.chars.BeginNewlineCheck',
        'weblate.checks.chars.EndNewlineCheck',
        'weblate.checks.chars.BeginSpaceCheck',
        'weblate.checks.chars.EndSpaceCheck',
        'weblate.checks.chars.EndStopCheck',
        'weblate.checks.chars.EndColonCheck',
        'weblate.checks.chars.EndQuestionCheck',
        'weblate.checks.chars.EndExclamationCheck',
        'weblate.checks.chars.EndEllipsisCheck',
        'weblate.checks.chars.EndSemicolonCheck',
        'weblate.checks.chars.MaxLengthCheck',
        'weblate.checks.chars.KashidaCheck',
        'weblate.checks.chars.PuctuationSpacingCheck',
        'weblate.checks.format.PythonFormatCheck',
        'weblate.checks.format.PythonBraceFormatCheck',
        'weblate.checks.format.PHPFormatCheck',
        'weblate.checks.format.CFormatCheck',
        'weblate.checks.format.PerlFormatCheck',
        'weblate.checks.format.JavaScriptFormatCheck',
        'weblate.checks.format.CSharpFormatCheck',
        'weblate.checks.format.JavaFormatCheck',
        'weblate.checks.format.JavaMessageFormatCheck',
        'weblate.checks.angularjs.AngularJSInterpolationCheck',
        'weblate.checks.qt.QtFormatCheck',
        'weblate.checks.qt.QtPluralCheck',
        'weblate.checks.ruby.RubyFormatCheck',
        'weblate.checks.consistency.PluralsCheck',
        'weblate.checks.consistency.SamePluralsCheck',
        'weblate.checks.consistency.ConsistencyCheck',
        'weblate.checks.consistency.TranslatedCheck',
        'weblate.checks.chars.NewlineCountingCheck',
        'weblate.checks.markup.BBCodeCheck',
        'weblate.checks.chars.ZeroWidthSpaceCheck',
        'weblate.checks.render.MaxSizeCheck',
        'weblate.checks.markup.XMLValidityCheck',
        'weblate.checks.markup.XMLTagsCheck',
        'weblate.checks.markup.MarkdownRefLinkCheck',
        'weblate.checks.markup.MarkdownLinkCheck',
        'weblate.checks.markup.MarkdownSyntaxCheck',
        'weblate.checks.markup.URLCheck',
        'weblate.checks.markup.SafeHTMLCheck',
        'weblate.checks.placeholders.PlaceholderCheck',
        'weblate.checks.placeholders.RegexCheck',
        'weblate.checks.source.OptionalPluralCheck',
        'weblate.checks.source.EllipsisCheck',
        'weblate.checks.source.MultipleFailingCheck',
    )

    class Meta(object):
        prefix = ''


class CheckManager(models.Manager):
    # pylint: disable=no-init

    def copy(self, project):
        """Copy checks to new project

        This is used on moving component to other project and ensures nothing
        is lost. We don't actually look where the check belongs as it
        would make the operation really expensive and it should be done in the
        cleanup cron job.
        """
        checks = []
        for check in self.iterator():
            checks.append(Check(
                project=project,
                check=check.check,
                ignore=check.ignore,
                content_hash=check.content_hash,
            ))
        # The batch size is needed for MySQL
        self.bulk_create(checks, batch_size=500)

    def bulk_create_ignore(self, objs):
        """Wrapper to bulk_create to ignore existing entries.

        Once we require Django 2.2 this can be replaced with
        bulk_create(ignore_conflicts=True).
        """
        try:
            with transaction.atomic():
                self.bulk_create(objs, batch_size=500)
        except IntegrityError:
            for obj in objs:
                try:
                    with transaction.atomic():
                        obj.save()
                except IntegrityError:
                    continue


@python_2_unicode_compatible
class Check(UnitData):
    check = models.CharField(max_length=50, choices=CHECKS.get_choices())
    ignore = models.BooleanField(db_index=True, default=False)

    objects = CheckManager()

    @cached_property
    def check_obj(self):
        try:
            return CHECKS[self.check]
        except KeyError:
            return None

    class Meta(object):
        unique_together = ('content_hash', 'project', 'language', 'check')
        index_together = [
            ('project', 'language', 'content_hash'),
        ]

    def __str__(self):
        return '{0}/{1}: {2}'.format(
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        if self.check_obj:
            try:
                return self.check_obj.get_description(self.related_units[0])
            except IndexError:
                return self.check_obj.description
        return self.check

    def get_fixup(self):
        if self.check_obj:
            try:
                return self.check_obj.get_fixup(self.related_units[0])
            except IndexError:
                return None
        return None

    def get_fixup_json(self):
        fixup = self.get_fixup()
        if not fixup:
            return None
        return json.dumps(fixup)

    def get_name(self):
        if self.check_obj:
            return self.check_obj.name
        return self.check

    def get_severity(self):
        if self.check_obj:
            return self.check_obj.severity
        return 'info'

    def get_doc_url(self):
        if self.check_obj:
            return self.check_obj.get_doc_url()
        return ''

    def set_ignore(self):
        """Set ignore flag."""
        self.ignore = True
        self.save()


@receiver(post_save, sender=Check)
@disable_for_loaddata
def update_failed_check_flag(sender, instance, created, **kwargs):
    """Update related unit failed check flag."""
    if instance.language is None or created:
        return
    related = instance.related_units
    try:
        related[0].update_has_failing_check(
            has_checks=None if instance.ignore else True,
            invalidate=True
        )
    except IndexError:
        return
