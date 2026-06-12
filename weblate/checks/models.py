# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from appconf import AppConf
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property

from weblate.checks.defaults import DEFAULT_CHECK_LIST
from weblate.utils.classloader import ClassLoader

from .base import BaseCheck

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models import Unit

    from .base import FixupType


class ChecksLoader(ClassLoader[BaseCheck]):
    def __init__(self) -> None:
        super().__init__("CHECK_LIST", base_class=BaseCheck)

    @cached_property
    def source(self):
        return {k: v for k, v in self.items() if v.source}

    @cached_property
    def target(self):
        return {k: v for k, v in self.items() if v.target}

    @cached_property
    def glossary(self):
        return {k: v for k, v in self.items() if v.glossary}


# Initialize checks list
CHECKS = ChecksLoader()


class WeblateChecksConf(AppConf):
    # List of quality checks
    CHECK_LIST = DEFAULT_CHECK_LIST

    class Meta:
        prefix = ""


class CheckQuerySet(models.QuerySet["Check", "Check"]):
    def order(self):
        return self.order_by("name")

    def filter_access(self, user: User):
        result = self
        if user.needs_project_filter:
            result = result.filter(
                user.get_project_access_query("unit__translation__component__project")
            )
        if user.needs_component_restrictions_filter:
            result = result.filter(
                Q(unit__translation__component__restricted=False)
                | Q(unit__translation__component_id__in=user.component_permissions)
            )
        return result


class Check(models.Model):
    unit = models.ForeignKey(
        "trans.Unit", on_delete=models.deletion.CASCADE, db_index=False
    )
    name = models.CharField(max_length=50, choices=CHECKS.get_choices())
    dismissed = models.BooleanField(db_index=True, default=False)

    objects = CheckQuerySet.as_manager()

    class Meta:
        unique_together = [  # noqa: RUF012
            ("unit", "name"),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=["unit"],
                condition=Q(dismissed=False),
                name="checks_active_unit_idx",
            ),
        ]
        verbose_name = "Quality check"
        verbose_name_plural = "Quality checks"

    def __str__(self) -> str:
        return str(self.get_name())

    @cached_property
    def check_obj(self) -> BaseCheck | None:
        try:
            return CHECKS[self.name]
        except KeyError:
            return None

    def is_enforced(self) -> bool:
        return self.name in self.unit.translation.component.enforced_checks

    def get_description(self) -> StrOrPromise:
        if self.check_obj:
            return self.check_obj.get_description(self)
        return self.name

    def get_fixup(self) -> Iterable[FixupType] | None:
        if self.check_obj:
            return self.check_obj.get_fixup(self.unit)
        return None

    def get_fixup_json(self) -> str | None:
        fixup = self.get_fixup()
        if not fixup:
            return None
        return json.dumps(fixup)

    def get_name(self) -> StrOrPromise:
        if self.check_obj:
            return self.check_obj.name
        return self.name

    def get_doc_url(self, user: User | None = None) -> str:
        if self.check_obj:
            return self.check_obj.get_doc_url(user=user)
        return ""

    def set_dismiss(self, *, state: bool = True, recurse: bool = True) -> None:
        """Set ignore flag."""
        if self.dismissed != state:
            self.dismissed = state
            self.save(update_fields=["dismissed"])
            self.unit.translation.invalidate_cache()
        if recurse:
            for child in Check.objects.filter(
                name=self.name,
                unit__in=self.unit.propagated_units,
                dismissed=not state,
            ).select_for_update():
                child.set_dismiss(state=state, recurse=False)


def get_display_checks(unit: Unit) -> Generator[Check]:
    check_objects = {check.name: check for check in unit.all_checks}
    for check, check_obj in CHECKS.target.items():
        if check_obj.should_display(unit):
            try:
                yield check_objects[check]
            except KeyError:
                yield Check(unit=unit, dismissed=False, name=check)
