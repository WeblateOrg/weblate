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

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from weblate.auth.models import User
from weblate.trans.models import AutoComponentList, Translation, Unit
from weblate.trans.util import sort_choices
from weblate.wladmin.models import WeblateModelAdmin


class RepoAdminMixin:
    def force_commit(self, request, queryset):
        """Commit pending changes for selected components."""
        for obj in queryset:
            obj.commit_pending("admin", request)
        self.message_user(
            request, f"Flushed changes in {queryset.count():d} git repos."
        )

    force_commit.short_description = _("Commit pending changes")

    def update_from_git(self, request, queryset):
        """Update selected components from git."""
        for obj in queryset:
            obj.do_update(request)
        self.message_user(request, f"Updated {queryset.count():d} git repos.")

    update_from_git.short_description = _("Update VCS repository")

    def get_qs_units(self, queryset):
        raise NotImplementedError()

    def get_qs_translations(self, queryset):
        raise NotImplementedError()

    def update_checks(self, request, queryset):
        """Recalculate checks for selected components."""
        units = self.get_qs_units(queryset)
        for unit in units:
            unit.run_checks()

        for translation in self.get_qs_translations(queryset):
            translation.invalidate_cache()

        self.message_user(request, "Updated checks for {:d} units.".format(len(units)))

    update_checks.short_description = _("Update quality checks")


class ProjectAdmin(WeblateModelAdmin, RepoAdminMixin):
    list_display = (
        "name",
        "slug",
        "web",
        "list_admins",
        "access_control",
        "enable_hooks",
        "num_vcs",
        "get_total",
        "get_source_words",
        "get_language_count",
    )
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "slug", "web"]
    actions = ["update_from_git", "update_checks", "force_commit"]

    def list_admins(self, obj):
        return ", ".join(
            User.objects.all_admins(obj).values_list("username", flat=True)
        )

    list_admins.short_description = _("Administrators")

    def get_total(self, obj):
        return obj.stats.source_strings

    get_total.short_description = _("Source strings")

    def get_source_words(self, obj):
        return obj.stats.source_words

    get_source_words.short_description = _("Source words")

    def get_language_count(self, obj):
        """Return number of languages used in this project."""
        return obj.stats.languages

    get_language_count.short_description = _("Languages")

    def num_vcs(self, obj):
        return obj.component_set.with_repo().count()

    num_vcs.short_description = _("VCS repositories")

    def get_qs_units(self, queryset):
        return Unit.objects.filter(translation__component__project__in=queryset)

    def get_qs_translations(self, queryset):
        return Translation.objects.filter(component__project__in=queryset)


class ComponentAdmin(WeblateModelAdmin, RepoAdminMixin):
    list_display = ["name", "slug", "project", "repo", "branch", "vcs", "file_format"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "slug", "repo", "branch", "project__name", "project__slug"]
    list_filter = ["project", "vcs", "file_format"]
    actions = ["update_from_git", "update_checks", "force_commit"]
    ordering = ["project__name", "name"]

    def get_qs_units(self, queryset):
        return Unit.objects.filter(translation__component__in=queryset)

    def get_qs_translations(self, queryset):
        return Translation.objects.filter(component__in=queryset)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Wrapper to sort languages by localized names."""
        result = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "source_language":
            result.choices = sort_choices(result.choices)
        return result


class TranslationAdmin(WeblateModelAdmin):
    list_display = ["component", "language", "revision", "filename"]
    search_fields = ["component__name", "language__code", "revision", "filename"]
    list_filter = ["component__project", "component", "language"]


class UnitAdmin(WeblateModelAdmin):
    list_display = ["source", "target", "position", "state"]
    search_fields = ["source", "target"]
    list_filter = ["translation__component", "translation__language", "state"]


class SuggestionAdmin(WeblateModelAdmin):
    list_display = ["target", "unit", "user"]
    search_fields = ["unit__source", "target"]


class CommentAdmin(WeblateModelAdmin):
    list_display = ["comment", "unit", "user"]
    search_fields = ["unit__source", "comment"]


class ChangeAdmin(WeblateModelAdmin):
    list_display = ["unit", "user", "timestamp"]
    date_hierarchy = "timestamp"
    list_filter = ["component", "project", "language"]
    raw_id_fields = ("unit",)


class AnnouncementAdmin(WeblateModelAdmin):
    list_display = ["message", "project", "component", "language"]
    search_fields = ["message"]
    list_filter = ["project", "language"]


class AutoComponentListAdmin(admin.TabularInline):
    model = AutoComponentList
    extra = 0


class ComponentListAdmin(WeblateModelAdmin):
    list_display = ["name", "show_dashboard"]
    list_filter = ["show_dashboard"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("components",)
    inlines = [AutoComponentListAdmin]
    ordering = ["name"]


class ContributorAgreementAdmin(WeblateModelAdmin):
    list_display = ["user", "component", "timestamp"]
    date_hierarchy = "timestamp"
    ordering = ("user__username", "component__project__name", "component__name")
