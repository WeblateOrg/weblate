# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.contrib import admin
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from weblate.trans.models import (
    Project, SubProject, Translation, Advertisement,
    Unit, Suggestion, Comment, Check, Dictionary, Change,
    Source, WhiteboardMessage, GroupACL, ComponentList,
)
from weblate.trans.util import WeblateAdmin


class ProjectAdmin(WeblateAdmin):
    list_display = (
        'name', 'slug', 'web', 'list_owners', 'enable_acl', 'enable_hooks',
        'num_vcs', 'num_strings', 'num_words', 'num_langs',
    )
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'web']
    actions = ['update_from_git', 'update_checks', 'force_commit']

    def list_owners(self, obj):
        return ', '.join(obj.owners.values_list('username', flat=True))
    list_owners.short_description = _('Owners')

    def num_vcs(self, obj):
        return obj.subproject_set.exclude(repo__startswith='weblate:/').count()
    num_vcs.short_description = _('VCS repositories')

    def num_strings(self, obj):
        return obj.get_total()
    num_strings.short_description = _('Source strings')

    def num_words(self, obj):
        return obj.get_total_words()
    num_words.short_description = _('Source words')

    def num_langs(self, obj):
        return obj.get_language_count()
    num_langs.short_description = _('Languages')

    def update_from_git(self, request, queryset):
        """
        Updates selected components from git.
        """
        for project in queryset:
            project.do_update(request)
        self.message_user(request, "Updated %d git repos." % queryset.count())
    update_from_git.short_description = _('Update VCS repository')

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
    update_checks.short_description = _('Update quality checks')

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
    force_commit.short_description = _('Commit pending changes')


class SubProjectAdmin(WeblateAdmin):
    list_display = [
        'name', 'slug', 'project', 'repo', 'branch', 'vcs', 'file_format'
    ]
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'repo', 'branch']
    list_filter = ['project', 'vcs', 'file_format']
    actions = ['update_from_git', 'update_checks', 'force_commit']

    def update_from_git(self, request, queryset):
        """
        Updates selected components from git.
        """
        for project in queryset:
            project.do_update(request)
        self.message_user(request, "Updated %d git repos." % queryset.count())
    update_from_git.short_description = _('Update VCS repository')

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
    update_checks.short_description = _('Update quality checks')

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
    force_commit.short_description = _('Commit pending changes')


class TranslationAdmin(WeblateAdmin):
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
    list_display = ['message', 'project', 'subproject', 'language']
    prepopulated_fields = {}
    search_fields = ['message']
    list_filter = ['project', 'language']


class ComponentListAdmin(admin.ModelAdmin):
    list_display = ['name']


class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ['placement', 'date_start', 'date_end', 'text']
    search_fields = ['text', 'note']
    date_hierarchy = 'date_end'


class SourceAdmin(admin.ModelAdmin):
    list_display = ['checksum', 'priority', 'timestamp']
    date_hierarchy = 'timestamp'


class GroupACLAdmin(admin.ModelAdmin):
    list_display = ['language', 'project_subproject', 'group_list']

    def group_list(self, obj):
        groups = obj.groups.values_list('name', flat=True)
        ret = ', '.join(groups[:5])
        if len(groups) > 5:
            ret += ', ...'
        return ret

    def project_subproject(self, obj):
        if obj.subproject:
            return obj.subproject
        else:
            return obj.project
    project_subproject.short_description = _('Project / Component')


# Register in admin interface
admin.site.register(Project, ProjectAdmin)
admin.site.register(SubProject, SubProjectAdmin)
admin.site.register(Advertisement, AdvertisementAdmin)
admin.site.register(WhiteboardMessage, WhiteboardAdmin)
admin.site.register(GroupACL, GroupACLAdmin)
admin.site.register(ComponentList, ComponentListAdmin)

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
