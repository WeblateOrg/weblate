# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import NoReturn

from django.conf import settings
from django.contrib import admin
from django.utils.translation import gettext_lazy

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.trans.models import (
    Announcement,
    AutoComponentList,
    Change,
    Comment,
    Component,
    ComponentList,
    ContributorAgreement,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.util import sort_choices
from weblate.utils.html import format_html_join_comma
from weblate.wladmin.models import WeblateModelAdmin


class RepoAdminMixin:
    @admin.action(description=gettext_lazy("Commit pending changes"))
    def force_commit(self, request: AuthenticatedHttpRequest, queryset) -> None:
        """Commit pending changes for selected components."""
        for obj in queryset:
            obj.commit_pending("admin", request)
        self.message_user(
            request, f"Flushed changes in {queryset.count():d} git repos."
        )

    @admin.action(description=gettext_lazy("Update VCS repository"))
    def update_from_git(self, request: AuthenticatedHttpRequest, queryset) -> None:
        """Update selected components from git."""
        for obj in queryset:
            obj.do_update(request)
        self.message_user(request, f"Updated {queryset.count():d} git repos.")

    def get_qs_units(self, queryset) -> NoReturn:
        raise NotImplementedError

    def get_qs_translations(self, queryset) -> NoReturn:
        raise NotImplementedError

    @admin.action(description=gettext_lazy("Update quality checks"))
    def update_checks(self, request: AuthenticatedHttpRequest, queryset) -> None:
        """Recalculate checks for selected components."""
        units = self.get_qs_units(queryset)
        for unit in units:
            unit.run_checks()

        for translation in self.get_qs_translations(queryset):
            translation.invalidate_cache()

        self.message_user(request, f"Updated checks for {len(units):d} units.")


@admin.register(Project)
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

    @admin.display(description=gettext_lazy("Administrators"))
    def list_admins(self, obj):
        return format_html_join_comma(
            "{}", (User.objects.all_admins(obj).values_list("username"))
        )

    @admin.display(description=gettext_lazy("Source strings"))
    def get_total(self, obj):
        return obj.stats.source_strings

    @admin.display(description=gettext_lazy("Source words"))
    def get_source_words(self, obj):
        return obj.stats.source_words

    @admin.display(description=gettext_lazy("Languages"))
    def get_language_count(self, obj):
        """Return number of languages used in this project."""
        return obj.stats.languages

    @admin.display(description=gettext_lazy("VCS repositories"))
    def num_vcs(self, obj):
        return obj.component_set.with_repo().count()

    def get_qs_units(self, queryset):
        return Unit.objects.filter(translation__component__project__in=queryset)

    def get_qs_translations(self, queryset):
        return Translation.objects.filter(component__project__in=queryset)


@admin.register(Component)
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

    def formfield_for_foreignkey(
        self, db_field, request: AuthenticatedHttpRequest, **kwargs
    ):
        """Sort languages by localized names."""
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


@admin.register(Announcement)
class AnnouncementAdmin(WeblateModelAdmin):
    list_display = ["message", "project", "component", "language"]
    search_fields = ["message"]
    list_filter = ["project", "language"]


class AutoComponentListAdmin(admin.TabularInline):
    model = AutoComponentList
    extra = 0


@admin.register(ComponentList)
class ComponentListAdmin(WeblateModelAdmin):
    list_display = ["name", "show_dashboard"]
    list_filter = ["show_dashboard"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("components",)
    inlines = [AutoComponentListAdmin]
    ordering = ["name"]


@admin.register(ContributorAgreement)
class ContributorAgreementAdmin(WeblateModelAdmin):
    list_display = ["user", "component", "timestamp"]
    date_hierarchy = "timestamp"
    ordering = ("user__username", "component__project__name", "component__name")


# Show some controls only in debug mode
if settings.DEBUG:
    admin.site.register(Translation, TranslationAdmin)
    admin.site.register(Unit, UnitAdmin)
    admin.site.register(Suggestion, SuggestionAdmin)
    admin.site.register(Comment, CommentAdmin)
    admin.site.register(Change, ChangeAdmin)
