# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models

from weblate.trans.fields import RegexField


class Variant(models.Model):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    variant_regex = RegexField(max_length=190, blank=True)
    # This really should be a TextField, but it does not work with unique
    # index and MySQL
    key = models.CharField(max_length=576)
    defining_units = models.ManyToManyField("Unit", related_name="defined_variants")

    class Meta:
        unique_together = (("key", "component", "variant_regex"),)
        verbose_name = "variant definition"
        verbose_name_plural = "variant definitions"

    def __str__(self):
        return f"{self.component}: {self.key}"
