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


import json

from appconf import AppConf
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader
from weblate.utils.decorators import disable_for_loaddata


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
        "weblate.checks.chars.PuctuationSpacingCheck",
        "weblate.checks.format.PythonFormatCheck",
        "weblate.checks.format.PythonBraceFormatCheck",
        "weblate.checks.format.PHPFormatCheck",
        "weblate.checks.format.CFormatCheck",
        "weblate.checks.format.PerlFormatCheck",
        "weblate.checks.format.JavaScriptFormatCheck",
        "weblate.checks.format.CSharpFormatCheck",
        "weblate.checks.format.JavaFormatCheck",
        "weblate.checks.format.JavaMessageFormatCheck",
        "weblate.checks.format.PercentPlaceholdersCheck",
        "weblate.checks.format.I18NextInterpolationCheck",
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
        "weblate.checks.source.OptionalPluralCheck",
        "weblate.checks.source.EllipsisCheck",
        "weblate.checks.source.MultipleFailingCheck",
    )

    class Meta:
        prefix = ""


class Check(models.Model):
    unit = models.ForeignKey("trans.Unit", on_delete=models.deletion.CASCADE)
    check = models.CharField(max_length=50, choices=CHECKS.get_choices())
    ignore = models.BooleanField(db_index=True, default=False)

    @cached_property
    def check_obj(self):
        try:
            return CHECKS[self.check]
        except KeyError:
            return None

    class Meta:
        unique_together = ("unit", "check")

    def __str__(self):
        return "{0}: {1}".format(self.unit, self.check)

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

    def get_severity(self):
        if self.check_obj:
            return self.check_obj.severity
        return "info"

    def get_doc_url(self):
        if self.check_obj:
            return self.check_obj.get_doc_url()
        return ""

    def set_ignore(self, state=True):
        """Set ignore flag."""
        self.ignore = state
        self.save()


@receiver(post_save, sender=Check)
@disable_for_loaddata
def check_post_save(sender, instance, created, **kwargs):
    """Handle check creation or updates."""
    if created:
        check_obj = instance.check_obj
        if not check_obj:
            return
        # Propagate checks that should do it
        if check_obj.propagates:
            for unit in instance.unit.same_source_units:
                unit.run_checks()
        # Update source checks if needed
        if check_obj.target:
            instance.unit.source_info.is_batch_update = instance.unit.is_batch_update
            instance.unit.source_info.run_checks()
    else:
        # Update related unit failed check flag (the check was (un)ignored)
        instance.unit.update_has_failing_check(
            has_checks=None if instance.ignore else True
        )


@receiver(post_delete, sender=Check)
@disable_for_loaddata
def remove_complimentary_checks(sender, instance, **kwargs):
    """Remove propagate checks from all units."""
    check_obj = instance.check_obj
    if not check_obj:
        return

    # Handle propagating checks
    if check_obj.propagates:
        for unit in instance.unit.same_source_units:
            if unit.check_set.filter(check=instance.check).delete()[0]:
                if not instance.unit.is_batch_update:
                    unit.update_has_failing_check()

    # Update source checks if needed
    if check_obj.target:
        unit = instance.unit
        if unit.is_batch_update:
            unit.translation.component.updated_sources[unit.id_hash] = unit.source_info
        else:
            try:
                unit.source_info.run_checks()
            except ObjectDoesNotExist:
                pass
