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

from django.apps import apps
from django.db import models
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.checks import CHECKS
from weblate.checks.models import Check
from weblate.trans.validators import validate_check_flags


@python_2_unicode_compatible
class Source(models.Model):
    id_hash = models.BigIntegerField()
    component = models.ForeignKey('Component', on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    check_flags = models.TextField(
        default='', validators=[validate_check_flags], blank=True
    )
    context = models.TextField(default='', blank=True)

    class Meta(object):
        app_label = 'trans'
        unique_together = ('id_hash', 'component')

    @cached_property
    def units_model(self):
        # Can't cache this property until all the models are loaded.
        apps.check_models_ready()
        return apps.get_model('trans', 'Unit')

    def __init__(self, *args, **kwargs):
        super(Source, self).__init__(*args, **kwargs)
        self.check_flags_modified = False

    def __str__(self):
        return 'src:{0}'.format(self.id_hash)

    def save(self, force_insert=False, **kwargs):
        """
        Wrapper around save to indicate whether flags has been
        modified.
        """
        if force_insert:
            self.check_flags_modified = self.check_flags != ''
        else:
            old = Source.objects.get(pk=self.pk)
            self.check_flags_modified = old.check_flags != self.check_flags
        super(Source, self).save(force_insert, **kwargs)

    @cached_property
    def unit(self):
        try:
            return self.units[0]
        except IndexError:
            return None

    @cached_property
    def units(self):
        return self.units_model.objects.filter(
            id_hash=self.id_hash, translation__component=self.component
        ).prefetch_related('translation', 'translation__component')

    def get_absolute_url(self):
        return reverse(
            'review_source',
            kwargs={
                'project': self.component.project.slug,
                'component': self.component.slug,
            },
        )

    def run_checks(self, unit=None, project=None, batch=False):
        """Update checks for this unit."""
        if unit is None:
            try:
                unit = self.units[0]
            except IndexError:
                return

        content_hash = unit.content_hash
        src = unit.get_source_plurals()
        if project is None:
            project = self.component.project

        # Fetch old checks
        if self.component.checks_cache is not None:
            old_checks = self.component.checks_cache.get((content_hash, None), [])
        else:
            old_checks = set(
                Check.objects.filter(
                    content_hash=content_hash, project=project, language=None
                ).values_list('check', flat=True)
            )
        create = []

        # Run all source checks
        for check, check_obj in CHECKS.items():
            if batch and check_obj.batch_update:
                if check in old_checks:
                    # Do not remove batch checks in batch processing
                    old_checks.remove(check)
                continue
            if check_obj.source and check_obj.check_source(src, unit):
                if check in old_checks:
                    # We already have this check
                    old_checks.remove(check)
                else:
                    # Create new check
                    create.append(
                        Check(
                            content_hash=content_hash,
                            project=project,
                            language=None,
                            ignore=False,
                            check=check,
                        )
                    )

        if create:
            Check.objects.bulk_create_ignore(create)

        # Remove stale checks
        if old_checks:
            Check.objects.filter(
                content_hash=content_hash,
                project=project,
                language=None,
                check__in=old_checks,
            ).delete()
