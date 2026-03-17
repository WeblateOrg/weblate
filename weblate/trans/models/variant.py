# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models
from django.db.models.functions import MD5

from weblate.trans.defines import VARIANT_REGEX_LENGTH
from weblate.trans.fields import RegexField


class Variant(models.Model):
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, db_index=False
    )
    variant_regex = RegexField(max_length=VARIANT_REGEX_LENGTH, blank=True)
    key = models.TextField()
    defining_units = models.ManyToManyField(
        "trans.Unit", related_name="defined_variants"
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                MD5("key"),
                "component",
                "variant_regex",
                name="trans_variant_unique_key_md5",
            ),
        ]
        verbose_name = "variant definition"
        verbose_name_plural = "variant definitions"

    def __str__(self) -> str:
        return f"{self.component}: {self.key}"
