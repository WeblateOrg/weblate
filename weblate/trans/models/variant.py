# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models

from weblate.trans.defines import VARIANT_KEY_LENGTH, VARIANT_REGEX_LENGTH
from weblate.trans.fields import RegexField


class Variant(models.Model):
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, db_index=False
    )
    variant_regex = RegexField(max_length=VARIANT_REGEX_LENGTH, blank=True)
    # This really should be a TextField, but it does not work with unique
    # index and MySQL
    key = models.CharField(max_length=VARIANT_KEY_LENGTH)
    defining_units = models.ManyToManyField(
        "trans.Unit", related_name="defined_variants"
    )

    class Meta:
        unique_together = (("component", "key", "variant_regex"),)
        verbose_name = "variant definition"
        verbose_name_plural = "variant definitions"

    def __str__(self) -> str:
        return f"{self.component}: {self.key}"
