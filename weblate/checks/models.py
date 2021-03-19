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

import json

from appconf import AppConf
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader


class ChecksLoader(ClassLoader):
    @cached_property
    def source(self):
        return {k: v for k, v in self.items() if v.source}

    @cached_property
    def target(self):
        return {k: v for k, v in self.items() if v.target}


# Initialize checks list
CHECKS = ChecksLoader("CHECK_LIST")


class WeblateChecksConf(AppConf):
    # List of quality checks
    CHECK_LIST = (
        "weblate.checks.same.SameCheck",
        "weblate.checks.chars.BeginNewlineCheck",
        "weblate.checks.chars.EndNewlineCheck",
        "weblate.checks.chars.BeginSpaceCheck",
        "weblate.checks.chars.EndSpaceCheck",
        "weblate.checks.chars.DoubleSpaceCheck",
        "weblate.checks.chars.EndStopCheck",
        "weblate.checks.chars.EndColonCheck",
        "weblate.checks.chars.EndQuestionCheck",
        "weblate.checks.chars.EndExclamationCheck",
        "weblate.checks.chars.EndEllipsisCheck",
        "weblate.checks.chars.EndSemicolonCheck",
        "weblate.checks.chars.MaxLengthCheck",
        "weblate.checks.chars.KashidaCheck",
        "weblate.checks.chars.PunctuationSpacingCheck",
        "weblate.checks.format.PythonFormatCheck",
        "weblate.checks.format.PythonBraceFormatCheck",
        "weblate.checks.format.PHPFormatCheck",
        "weblate.checks.format.CFormatCheck",
        "weblate.checks.format.PerlFormatCheck",
        "weblate.checks.format.JavaScriptFormatCheck",
        "weblate.checks.format.LuaFormatCheck",
        "weblate.checks.format.SchemeFormatCheck",
        "weblate.checks.format.CSharpFormatCheck",
        "weblate.checks.format.JavaFormatCheck",
        "weblate.checks.format.JavaMessageFormatCheck",
        "weblate.checks.format.PercentPlaceholdersCheck",
        "weblate.checks.format.VueFormattingCheck",
        "weblate.checks.format.I18NextInterpolationCheck",
        "weblate.checks.format.ESTemplateLiteralsCheck",
        "weblate.checks.angularjs.AngularJSInterpolationCheck",
        "weblate.checks.qt.QtFormatCheck",
        "weblate.checks.qt.QtPluralCheck",
        "weblate.checks.ruby.RubyFormatCheck",
        "weblate.checks.consistency.PluralsCheck",
        "weblate.checks.consistency.SamePluralsCheck",
        "weblate.checks.consistency.ConsistencyCheck",
        "weblate.checks.consistency.TranslatedCheck",
        "weblate.checks.chars.EscapedNewlineCountingCheck",
        "weblate.checks.chars.NewLineCountCheck",
        "weblate.checks.markup.BBCodeCheck",
        "weblate.checks.chars.ZeroWidthSpaceCheck",
        "weblate.checks.render.MaxSizeCheck",
        "weblate.checks.markup.XMLValidityCheck",
        "weblate.checks.markup.XMLTagsCheck",
        "weblate.checks.markup.MarkdownRefLinkCheck",
        "weblate.checks.markup.MarkdownLinkCheck",
        "weblate.checks.markup.MarkdownSyntaxCheck",
        "weblate.checks.markup.URLCheck",
        "weblate.checks.markup.SafeHTMLCheck",
        "weblate.checks.placeholders.PlaceholderCheck",
        "weblate.checks.placeholders.RegexCheck",
        "weblate.checks.duplicate.DuplicateCheck",
        "weblate.checks.source.OptionalPluralCheck",
        "weblate.checks.source.EllipsisCheck",
        "weblate.checks.source.MultipleFailingCheck",
        "weblate.checks.source.LongUntranslatedCheck",
        "weblate.checks.format.MultipleUnnamedFormatsCheck",
        "weblate.checks.glossary.GlossaryCheck",
    )

    class Meta:
        prefix = ""


class CheckQuerySet(models.QuerySet):
    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(unit__translation__component__project_id__in=user.allowed_project_ids)
            & (
                Q(unit__translation__component__restricted=False)
                | Q(unit__translation__component_id__in=user.component_permissions)
            )
        )


class Check(models.Model):
    unit = models.ForeignKey("trans.Unit", on_delete=models.deletion.CASCADE)
    check = models.CharField(max_length=50, choices=CHECKS.get_choices())
    dismissed = models.BooleanField(db_index=True, default=False)

    objects = CheckQuerySet.as_manager()

    class Meta:
        unique_together = ("unit", "check")

    def __str__(self):
        return str(self.get_name())

    @cached_property
    def check_obj(self):
        try:
            return CHECKS[self.check]
        except KeyError:
            return None

    def is_enforced(self):
        return self.check in self.unit.translation.component.enforced_checks

    def get_description(self):
        if self.check_obj:
            return self.check_obj.get_description(self)
        return self.check

    def get_fixup(self):
        if self.check_obj:
            return self.check_obj.get_fixup(self.unit)
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

    def get_doc_url(self, user=None):
        if self.check_obj:
            return self.check_obj.get_doc_url(user=user)
        return ""

    def set_dismiss(self, state=True):
        """Set ignore flag."""
        self.dismissed = state
        self.save(update_fields=["dismissed"])
        self.unit.translation.invalidate_cache()


def get_display_checks(unit):
    for check, check_obj in CHECKS.target.items():
        if check_obj.should_display(unit):
            yield Check(unit=unit, dismissed=False, check=check)
