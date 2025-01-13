# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import ListView

from weblate.auth.models import AuthenticatedHttpRequest
from weblate.checks.models import CHECKS, Check
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.utils.random import get_random_identifier
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import PathViewMixin

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class CheckWrapper:
    def __init__(
        self,
        name: str,
        check_count: int,
        dismissed_check_count: int,
        active_check_count: int,
        translated_check_count: int,
        path_object,
    ) -> None:
        self.pk = get_random_identifier()
        self.name = name
        try:
            self.check_obj = CHECKS[name]
        except KeyError:
            self.check_obj = None
        self.check_count = check_count
        self.dismissed_check_count = dismissed_check_count
        self.active_check_count = active_check_count
        self.translated_check_count = translated_check_count
        self.row_title = self.check_obj.name if self.check_obj else self.name
        kwargs = {"name": self.name}
        if path_object is not None:
            kwargs["path"] = path_object.get_url_path()
        self.row_url = reverse("checks", kwargs=kwargs)


class CheckList(PathViewMixin, ListView):
    supported_path_types = (
        None,
        Project,
        Component,
        Translation,
        Language,
        ProjectLanguage,
    )
    template_name = "check_list.html"
    request: AuthenticatedHttpRequest

    def annotate(self, queryset, prefix: str):
        id_field = f"{prefix}unit__check"
        return queryset.annotate(
            check_count=Count(id_field),
            dismissed_check_count=Count(
                id_field, filter=Q(**{f"{prefix}unit__check__dismissed": True})
            ),
            active_check_count=Count(
                id_field, filter=Q(**{f"{prefix}unit__check__dismissed": False})
            ),
            translated_check_count=Count(
                id_field,
                filter=Q(
                    **{
                        f"{prefix}unit__check__dismissed": False,
                        f"{prefix}unit__state__gte": STATE_TRANSLATED,
                    },
                ),
            ),
        )

    def postprocess_queryset(self, result):
        # Annotate with progress indicator and attributes
        max_value = max((item.check_count for item in result), default=0)
        for item in result:
            item.check_progress = item.check_count * 100 // max_value
            if not hasattr(item, "check_obj"):
                item.check_obj = self.check_obj
            if not hasattr(item, "row_title"):
                if isinstance(item, Translation):
                    if isinstance(self.path_object, ProjectLanguage):
                        item.row_title = item.component.name
                    else:
                        item.row_title = item.language.name
                elif isinstance(item, ProjectLanguage):
                    item.row_title = item.project.name
                else:
                    item.row_title = item.name
            if not hasattr(item, "row_url"):
                item.row_url = reverse(
                    "checks",
                    kwargs={
                        "name": self.check_obj.check_id if self.check_obj else "-",
                        "path": item.get_url_path(),
                    },
                )
        return result

    def get_queryset(self):
        if self.check_obj is None:
            if self.path_object is None:
                all_checks = Check.objects.filter_access(self.request.user)
            elif isinstance(self.path_object, Project):
                all_checks = Check.objects.filter(
                    unit__translation__component__project=self.path_object
                )
            elif isinstance(self.path_object, Component):
                all_checks = Check.objects.filter(
                    unit__translation__component=self.path_object
                )
            elif isinstance(self.path_object, Translation):
                all_checks = Check.objects.filter(unit__translation=self.path_object)
            elif isinstance(self.path_object, Language):
                all_checks = Check.objects.filter(
                    unit__translation__language=self.path_object
                )
            elif isinstance(self.path_object, ProjectLanguage):
                all_checks = Check.objects.filter(
                    unit__translation__language=self.path_object.language,
                    unit__translation__component__project=self.path_object.project,
                )
            else:
                msg = f"Unsupported {self.path_object}"
                raise TypeError(msg)
            result = [
                CheckWrapper(**item, path_object=self.path_object)
                for item in all_checks.values("name").annotate(
                    check_count=Count("id"),
                    dismissed_check_count=Count("id", filter=Q(dismissed=True)),
                    active_check_count=Count("id", filter=Q(dismissed=False)),
                    translated_check_count=Count(
                        "id",
                        filter=Q(dismissed=False, unit__state__gte=STATE_TRANSLATED),
                    ),
                )
            ]
        elif self.path_object is None:
            result = self.annotate(
                self.request.user.allowed_projects.filter(
                    component__translation__unit__check__name=self.check_obj.check_id
                ),
                "component__translation__",
            ).order()
        elif isinstance(self.path_object, Project):
            result = self.annotate(
                Component.objects.filter_access(self.request.user)
                .filter(
                    translation__unit__check__name=self.check_obj.check_id,
                    project=self.path_object,
                )
                .prefetch_related("project"),
                "translation__",
            ).order()
        elif isinstance(self.path_object, Component):
            result = self.annotate(
                Translation.objects.filter(
                    component=self.path_object,
                    unit__check__name=self.check_obj.check_id,
                )
                .select_related("language")
                .prefetch_related("component__project"),
                "",
            ).order_by("language__code")
        elif isinstance(self.path_object, Language):
            result = [
                ProjectLanguage(project=obj, language=self.path_object)
                for obj in self.annotate(
                    self.request.user.allowed_projects.filter(
                        component__translation__language=self.path_object,
                        component__translation__unit__check__name=self.check_obj.check_id,
                    ),
                    "component__translation__",
                ).order()
            ]
            # Mirror counts
            for item in result:
                item.check_count = item.project.check_count
                item.dismissed_check_count = item.project.dismissed_check_count
                item.active_check_count = item.project.active_check_count
                item.translated_check_count = item.project.translated_check_count
        elif isinstance(self.path_object, ProjectLanguage):
            result = self.annotate(
                Translation.objects.filter(
                    component__project=self.path_object.project,
                    language=self.path_object.language,
                    unit__check__name=self.check_obj.check_id,
                )
                .select_related("language")
                .prefetch_related("component__project"),
                "",
            ).order_by("language__code")
        else:
            # Translation should never reach this, it is handled in get()
            msg = f"Unsupported {self.path_object}"
            raise TypeError(msg)

        return self.postprocess_queryset(result)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["check"] = self.check_obj
        context["path_object"] = self.path_object
        if self.check_obj is None and self.path_object is None:
            context["title"] = gettext("Failing checks")
        elif self.check_obj is not None and self.path_object is None:
            context["title"] = self.check_obj.name
        elif self.check_obj is None and self.path_object is not None:
            context["title"] = f"{gettext('Failing checks')} / {self.path_object}"
        else:
            context["title"] = f"{self.check_obj.name} / {self.path_object}"
        if self.check_obj is None:
            context["column_title"] = gettext("Check")
        elif self.path_object is None:
            context["column_title"] = gettext("Project")
        elif isinstance(self.path_object, Project):
            context["column_title"] = gettext("Component")
        elif isinstance(self.path_object, Component):
            context["column_title"] = gettext("Translation")
            context["translate_links"] = True
        elif isinstance(self.path_object, Language):
            context["column_title"] = gettext("Project")
        elif isinstance(self.path_object, ProjectLanguage):
            context["column_title"] = gettext("Component")
            context["translate_links"] = True
        else:
            msg = f"Type not supported: {self.path_object}"
            raise TypeError(msg)
        return context

    def setup(self, request: AuthenticatedHttpRequest, **kwargs) -> None:
        super().setup(request, **kwargs)
        self.check_obj = None
        name = kwargs.get("name")
        if name and name != "-":
            try:
                self.check_obj = CHECKS[name]
            except KeyError as error:
                msg = "No check matches the given query."
                raise Http404(msg) from error

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        if isinstance(self.path_object, Translation) and self.check_obj:
            return redirect(
                f"{self.path_object.get_translate_url()}?q={self.check_obj.url_id} OR dismissed_{self.check_obj.url_id}"
            )
        return super().get(request, *args, **kwargs)


def render_check(request: AuthenticatedHttpRequest, unit_id, check_id):
    """Render endpoint for checks."""
    try:
        obj = Check.objects.get(unit_id=unit_id, name=check_id)
    except Check.DoesNotExist:
        unit = get_object_or_404(Unit, pk=int(unit_id))
        obj = Check(unit=unit, dismissed=False, name=check_id)
    request.user.check_access_component(obj.unit.translation.component)

    if obj.check_obj is None:
        msg = "No check object found."
        raise Http404(msg)

    return obj.check_obj.render(request, obj.unit)
