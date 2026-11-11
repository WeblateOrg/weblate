# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.utils.translation import gettext_lazy

from weblate.accounts.utils import (
    has_recent_sensitive_verification,
    sensitive_verification_redirect,
)
from weblate.auth.models import User
from weblate.trans.component_creation import changes_component_sensitive_access
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

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from weblate.auth.models import AuthenticatedHttpRequest


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

    def get_qs_units(self, queryset) -> QuerySet[Unit]:
        raise NotImplementedError

    def get_qs_translations(self, queryset) -> QuerySet[Translation]:
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


class SensitiveFieldsAdmin(WeblateModelAdmin):
    """Require recent credential verification for changing listed fields."""

    sensitive_fields: frozenset[str] = frozenset()

    def changes_sensitive_fields(self, request, object_id: str | None) -> bool:
        # Django treats Save as new as an addition, including on change URLs.
        if "_saveasnew" in request.POST:
            object_id = None
        obj = self.get_object(request, unquote(object_id)) if object_id else None
        if object_id is not None:
            if obj is None or not self.has_change_permission(request, obj):
                return False
        elif not self.has_add_permission(request):
            return False
        form_class = self.get_form(request, obj, change=obj is not None)
        # changed_data compares raw input only, without running model
        # validation, which can touch the repository.
        form = form_class(request.POST, request.FILES, instance=obj)
        return self.form_changes_sensitive_fields(request, form)

    def form_changes_sensitive_fields(self, request, form) -> bool:
        return bool(form.instance.pk and self.sensitive_fields & set(form.changed_data))

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if (
            request.method == "POST"
            and self.changes_sensitive_fields(request, object_id)
            and not has_recent_sensitive_verification(request)
        ):
            return sensitive_verification_redirect(request, request.path)
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(Project)
class ProjectAdmin(SensitiveFieldsAdmin, RepoAdminMixin):
    sensitive_fields = frozenset({"access_control", "public_sharing", "enforced_2fa"})
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
    # ruff: ignore[mutable-class-default]
    prepopulated_fields = {
        "slug": ("name",),
    }
    search_fields = ("name", "slug", "web")
    actions = ("update_from_git", "update_checks", "force_commit")

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

    def get_qs_units(self, queryset) -> QuerySet[Unit]:
        return Unit.objects.filter(translation__component__project__in=queryset)

    def get_qs_translations(self, queryset) -> QuerySet[Translation]:
        return Translation.objects.filter(component__project__in=queryset)


@admin.register(Component)
class ComponentAdmin(SensitiveFieldsAdmin, RepoAdminMixin):
    list_display = ("name", "slug", "project", "repo", "branch", "vcs", "file_format")
    # ruff: ignore[mutable-class-default]
    prepopulated_fields = {
        "slug": ("name",),
    }
    search_fields = ("name", "slug", "repo", "branch", "project__name", "project__slug")
    list_filter = ("vcs", "file_format")
    autocomplete_fields = ("project",)

    def form_changes_sensitive_fields(self, request, form) -> bool:
        return changes_component_sensitive_access(form, request.user)

    def get_queryset(self, request):
        # Component labels include their category ancestry and project.
        return (
            super()
            .get_queryset(request)
            .select_related(
                "project",
                "category__project",
                "category__category__project",
                "category__category__category__project",
            )
        )

    actions = ("update_from_git", "update_checks", "force_commit")
    ordering = ("project__name", "name")

    def get_qs_units(self, queryset) -> QuerySet[Unit]:
        return Unit.objects.filter(translation__component__in=queryset)

    def get_qs_translations(self, queryset) -> QuerySet[Translation]:
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
    list_display = ("component", "language", "revision", "filename")
    search_fields = (
        "component__name",
        "component__slug",
        "component__project__name",
        "component__project__slug",
        "language__code",
        "revision",
        "filename",
    )
    list_filter = ("language",)


class UnitAdmin(WeblateModelAdmin):
    list_display = ("source", "target", "position", "state")
    search_fields = (
        "source",
        "target",
        "translation__component__name",
        "translation__component__slug",
        "translation__component__project__name",
        "translation__component__project__slug",
    )
    list_filter = ("translation__language", "state")


class SuggestionAdmin(WeblateModelAdmin):
    list_display = ("target", "unit", "user")
    search_fields = ("unit__source", "target")


class CommentAdmin(WeblateModelAdmin):
    list_display = ("comment", "unit", "user")
    search_fields = ("unit__source", "comment")


class ChangeAdmin(WeblateModelAdmin):
    list_display = ("unit", "user", "timestamp")
    date_hierarchy = "timestamp"
    list_filter = ("language",)
    search_fields = (
        "component__name",
        "component__slug",
        "project__name",
        "project__slug",
    )
    raw_id_fields = ("unit",)


@admin.register(Announcement)
class AnnouncementAdmin(WeblateModelAdmin):
    list_display = ("message", "project", "component", "language")
    search_fields = ("message", "project__name", "project__slug")
    list_filter = ("language",)


class AutoComponentListAdmin(admin.TabularInline):
    model = AutoComponentList
    extra = 0


@admin.register(ComponentList)
class ComponentListAdmin(WeblateModelAdmin):
    search_fields = ("name", "slug")
    list_display = ("name", "show_dashboard")
    list_filter = ("show_dashboard",)
    # ruff: ignore[mutable-class-default]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("components",)
    inlines = (AutoComponentListAdmin,)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "components" and field is not None:
            field.queryset = field.queryset.select_related(
                "project",
                "category__project",
                "category__category__project",
                "category__category__category__project",
            )
        return field

    ordering = ("name",)


@admin.register(ContributorAgreement)
class ContributorAgreementAdmin(WeblateModelAdmin):
    list_display = (
        "user",
        "component",
        "project",
        "category",
        "workspace",
        "timestamp",
    )
    date_hierarchy = "timestamp"
    ordering = (
        "user__username",
        "workspace__name",
        "project__name",
        "category__project__name",
        "category__name",
        "component__project__name",
        "component__name",
    )


# Show some controls only in debug mode
if settings.DEBUG:
    admin.site.register(Translation, TranslationAdmin)
    admin.site.register(Unit, UnitAdmin)
    admin.site.register(Suggestion, SuggestionAdmin)
    admin.site.register(Comment, CommentAdmin)
    admin.site.register(Change, ChangeAdmin)
