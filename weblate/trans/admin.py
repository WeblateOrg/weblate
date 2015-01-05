# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.contrib import admin
from django.conf import settings
from weblate.trans.models import (
    Project, SubProject, Translation, Advertisement,
    Unit, Suggestion, Comment, Check, Dictionary, Change,
    Source, WhiteboardMessage
)


class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'web', 'enable_acl', 'enable_hooks']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'web']
    actions = ['update_from_git', 'update_checks', 'force_commit']

    def update_from_git(self, request, queryset):
        """
        Updates selected components from git.
        """
        for project in queryset:
            project.do_update(request)
        self.message_user(request, "Updated %d git repos." % queryset.count())

    def update_checks(self, request, queryset):
        """
        Recalculates checks for selected components.
        """
        cnt = 0
        units = Unit.objects.filter(
            translation__subproject__project__in=queryset
        )
        for unit in units.iterator():
            unit.run_checks()
            cnt += 1
        self.message_user(request, "Updated checks for %d units." % cnt)

    def force_commit(self, request, queryset):
        """
        Commits pending changes for selected components.
        """
        for project in queryset:
            project.commit_pending(request)
        self.message_user(
            request,
            "Flushed changes in %d git repos." % queryset.count()
        )


class SubProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'project', 'repo', 'branch']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'repo', 'branch']
    list_filter = ['project']
    actions = ['update_from_git', 'update_checks', 'force_commit']

    def update_from_git(self, request, queryset):
        """
        Updates selected components from git.
        """
        for project in queryset:
            project.do_update(request)
        self.message_user(request, "Updated %d git repos." % queryset.count())

    def update_checks(self, request, queryset):
        """
        Recalculates checks for selected components.
        """
        cnt = 0
        units = Unit.objects.filter(
            translation__subproject__in=queryset
        )
        for unit in units.iterator():
            unit.run_checks()
            cnt += 1
        self.message_user(
            request,
            "Updated checks for %d units." % cnt
        )

    def force_commit(self, request, queryset):
        """
        Commits pending changes for selected components.
        """
        for project in queryset:
            project.commit_pending(request)
        self.message_user(
            request,
            "Flushed changes in %d git repos." % queryset.count()
        )


class TranslationAdmin(admin.ModelAdmin):
    list_display = [
        'subproject', 'language', 'translated', 'total',
        'fuzzy', 'revision', 'filename', 'enabled'
    ]
    search_fields = [
        'subproject__slug', 'language__code', 'revision', 'filename'
    ]
    list_filter = ['enabled', 'subproject__project', 'subproject', 'language']
    actions = ['enable_translation', 'disable_translation']

    def enable_translation(self, request, queryset):
        """
        Mass enabling of translations.
        """
        queryset.update(enabled=True)
        self.message_user(
            request,
            "Enabled %d translations." % queryset.count()
        )

    def disable_translation(self, request, queryset):
        """
        Mass disabling of translations.
        """
        queryset.update(enabled=False)
        self.message_user(
            request,
            "Disabled %d translations." % queryset.count()
        )


class UnitAdmin(admin.ModelAdmin):
    list_display = ['source', 'target', 'position', 'fuzzy', 'translated']
    search_fields = ['source', 'target', 'checksum']
    list_filter = [
        'translation__subproject',
        'translation__language',
        'fuzzy',
        'translated'
    ]


class SuggestionAdmin(admin.ModelAdmin):
    list_display = ['contentsum', 'target', 'project', 'language', 'user']
    list_filter = ['project', 'language']
    search_fields = ['contentsum', 'target']


class CommentAdmin(admin.ModelAdmin):
    list_display = [
        'contentsum', 'comment', 'user', 'project', 'language', 'user'
    ]
    list_filter = ['project', 'language']
    search_fields = ['contentsum', 'comment']


class CheckAdmin(admin.ModelAdmin):
    list_display = ['contentsum', 'check', 'project', 'language', 'ignore']
    search_fields = ['contentsum', 'check']
    list_filter = ['check', 'project', 'ignore']


class DictionaryAdmin(admin.ModelAdmin):
    list_display = ['source', 'target', 'project', 'language']
    search_fields = ['source', 'target']
    list_filter = ['project', 'language']


class ChangeAdmin(admin.ModelAdmin):
    list_display = ['unit', 'user', 'timestamp']
    date_hierarchy = 'timestamp'
    list_filter = [
        'unit__translation__subproject',
        'unit__translation__subproject__project',
        'unit__translation__language'
    ]
    raw_id_fields = ('unit',)


class WhiteboardAdmin(admin.ModelAdmin):
    list_display = ['message']
    prepopulated_fields = {}
    search_fields = ['message']


class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ['placement', 'date_start', 'date_end', 'text']
    search_fields = ['text', 'note']
    date_hierarchy = 'date_end'


class SourceAdmin(admin.ModelAdmin):
    list_display = ['checksum', 'priority', 'timestamp']
    date_hierarchy = 'timestamp'


# Register in admin interface
admin.site.register(Project, ProjectAdmin)
admin.site.register(SubProject, SubProjectAdmin)
admin.site.register(Advertisement, AdvertisementAdmin)
admin.site.register(WhiteboardMessage, WhiteboardAdmin)

# Show some controls only in debug mode
if settings.DEBUG:
    admin.site.register(Translation, TranslationAdmin)
    admin.site.register(Unit, UnitAdmin)
    admin.site.register(Suggestion, SuggestionAdmin)
    admin.site.register(Comment, CommentAdmin)
    admin.site.register(Check, CheckAdmin)
    admin.site.register(Dictionary, DictionaryAdmin)
    admin.site.register(Change, ChangeAdmin)
    admin.site.register(Source, SourceAdmin)
