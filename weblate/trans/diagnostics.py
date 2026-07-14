# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django import forms
from django.db.models import Count, F, Max, OuterRef, Q, Subquery, Window
from django.db.models.functions import Lower, RowNumber
from django.utils.translation import gettext_lazy

from weblate.trans.alerts.base import AlertCategory, AlertSeverity
from weblate.trans.alerts.registry import ALERTS, get_alert_class, load_alerts
from weblate.trans.models import Alert, Component

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import QueryDict
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models import Project


ALERT_CATEGORY_CHOICES = (
    (AlertCategory.ADDONS, gettext_lazy("Add-ons")),
    (AlertCategory.COMMUNITY, gettext_lazy("Community")),
    (AlertCategory.CONFIGURATION, gettext_lazy("Configuration")),
    (AlertCategory.FILES, gettext_lazy("Files")),
    (AlertCategory.VCS, gettext_lazy("Version control")),
)
ALERT_CATEGORY_LABELS = dict(ALERT_CATEGORY_CHOICES)
ALERT_SEVERITY_CLASSES: dict[int, str] = {
    AlertSeverity.INFO: "text-bg-info",
    AlertSeverity.WARNING: "text-bg-warning",
    AlertSeverity.ERROR: "text-bg-danger",
}

DIAGNOSTICS_STATE_ACTIVE = "active"
DIAGNOSTICS_STATE_DISMISSED = "dismissed"
DIAGNOSTICS_STATE_ALL = "all"
DIAGNOSTICS_LINK_LIMIT = 20


class DiagnosticsFilterForm(forms.Form):
    diagnostic_state = forms.ChoiceField(
        label=gettext_lazy("State"),
        choices=(
            (DIAGNOSTICS_STATE_ACTIVE, gettext_lazy("Active")),
            (DIAGNOSTICS_STATE_DISMISSED, gettext_lazy("Dismissed")),
            (DIAGNOSTICS_STATE_ALL, gettext_lazy("All")),
        ),
        initial=DIAGNOSTICS_STATE_ACTIVE,
        required=False,
    )
    diagnostic_severity = forms.TypedChoiceField(
        label=gettext_lazy("Severity"),
        choices=(("", gettext_lazy("All")), *AlertSeverity.choices),
        coerce=int,
        empty_value=None,
        required=False,
    )
    diagnostic_category = forms.ChoiceField(
        label=gettext_lazy("Category"),
        choices=(("", gettext_lazy("All")), *ALERT_CATEGORY_CHOICES),
        required=False,
    )
    diagnostic_actionable = forms.BooleanField(
        label=gettext_lazy("Actionable by me"), required=False
    )


@dataclass
class DiagnosticsGroup:
    name: str
    title: StrOrPromise
    severity: int
    severity_label: StrOrPromise
    severity_class: str
    category: str
    category_label: StrOrPromise
    project_wide: bool
    active_count: int = 0
    dismissed_count: int = 0
    affected_count: int = 0
    hidden_count: int = 0
    projects: list[Project] = field(default_factory=list)
    project_components: list[tuple[Project, Component]] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    _projects: dict[int, Project] = field(default_factory=dict, repr=False)
    _project_components: dict[int, Component] = field(default_factory=dict, repr=False)
    _components: dict[int, Component] = field(default_factory=dict, repr=False)

    def add_counts(self, active: int, dismissed: int) -> None:
        self.active_count += active
        self.dismissed_count += dismissed

    def add_component(self, component: Component) -> None:
        self._components[component.pk] = component

    def add_project_component(self, component: Component) -> None:
        project = component.project
        self._projects[project.pk] = project
        self._project_components[project.pk] = component

    def finalize(self) -> None:
        if self.project_wide:
            projects = sorted(
                self._projects.values(), key=lambda project: project.name.casefold()
            )
            if not self.affected_count:
                self.affected_count = len(projects)
            self.projects = projects[:DIAGNOSTICS_LINK_LIMIT]
            self.project_components = [
                (project, self._project_components[project.pk])
                for project in self.projects
            ]
            displayed_count = len(self.projects)
        else:
            components = sorted(
                self._components.values(),
                key=lambda component: (
                    component.project.name.casefold(),
                    component.name.casefold(),
                ),
            )
            if not self.affected_count:
                self.affected_count = len(components)
            self.components = components[:DIAGNOSTICS_LINK_LIMIT]
            displayed_count = len(self.components)
        self.hidden_count = max(0, self.affected_count - displayed_count)


def _get_filter_form(data: QueryDict) -> DiagnosticsFilterForm:
    query_data = data.copy()
    query_data.setdefault("diagnostic_state", DIAGNOSTICS_STATE_ACTIVE)
    form = DiagnosticsFilterForm(query_data)
    if form.is_valid():
        return form
    return DiagnosticsFilterForm({"diagnostic_state": DIAGNOSTICS_STATE_ACTIVE})


def _get_group(
    groups: dict[str, DiagnosticsGroup], name: str, severity: int
) -> DiagnosticsGroup:
    group = groups.get(name)
    if group is not None:
        return group
    alert_class = get_alert_class(name)
    group = DiagnosticsGroup(
        name=name,
        title=alert_class.verbose,
        severity=severity,
        severity_label=AlertSeverity(severity).label,
        severity_class=ALERT_SEVERITY_CLASSES.get(severity, "text-bg-secondary"),
        category=alert_class.category,
        category_label=ALERT_CATEGORY_LABELS.get(
            alert_class.category, alert_class.category
        ),
        project_wide=alert_class.project_wide,
    )
    groups[name] = group
    return group


def _fetch_components(component_ids: set[int]) -> dict[int, Component]:
    if not component_ids:
        return {}
    return {
        component.pk: component
        for component in Component.objects.filter(pk__in=component_ids).prefetch(
            alerts=False
        )
    }


def _get_project_rows(alerts, project_wide_names: set[str], *, counts: bool):
    if not project_wide_names:
        return []
    representative = (
        alerts.filter(
            name=OuterRef("name"),
            component__project_id=OuterRef("component__project_id"),
        )
        .order_by(Lower("component__name"), "component_id")
        .values("component_id")[:1]
    )
    annotations = {
        "component_id": Subquery(representative),
        "alert_count": Count("pk"),
    }
    if counts:
        annotations.update(
            {
                "severity": Max("severity"),
                "active_count": Count("pk", filter=Q(dismissed_at__isnull=True)),
                "dismissed_count": Count("pk", filter=Q(dismissed_at__isnull=False)),
            }
        )
    return (
        alerts.filter(name__in=project_wide_names)
        .values("name", "component__project_id", "component__project__name")
        .annotate(**annotations)
        .order_by("name", Lower("component__project__name"), "component__project_id")
    )


def _get_aggregated_groups(alerts) -> dict[str, DiagnosticsGroup]:
    groups: dict[str, DiagnosticsGroup] = {}
    for row in alerts.values("name").annotate(
        severity=Max("severity"),
        active_count=Count("pk", filter=Q(dismissed_at__isnull=True)),
        dismissed_count=Count("pk", filter=Q(dismissed_at__isnull=False)),
        affected_components=Count("component_id", distinct=True),
        affected_projects=Count("component__project_id", distinct=True),
    ):
        group = _get_group(groups, row["name"], row["severity"])
        group.add_counts(row["active_count"], row["dismissed_count"])
        group.affected_count = (
            row["affected_projects"]
            if group.project_wide
            else row["affected_components"]
        )
    return groups


def _populate_aggregated_links(alerts, groups: dict[str, DiagnosticsGroup]) -> None:
    component_names = {name for name, group in groups.items() if not group.project_wide}
    project_wide_names = {name for name, group in groups.items() if group.project_wide}
    component_rows = []
    if component_names:
        component_rows = list(
            alerts.filter(name__in=component_names)
            .annotate(
                diagnostic_rank=Window(
                    expression=RowNumber(),
                    partition_by=(F("name"),),
                    order_by=(
                        Lower("component__project__name").asc(),
                        Lower("component__name").asc(),
                        F("component_id").asc(),
                    ),
                )
            )
            .filter(diagnostic_rank__lte=DIAGNOSTICS_LINK_LIMIT)
            .values("name", "component_id")
        )

    project_rows = []
    if project_wide_names:
        project_rows = list(
            _get_project_rows(alerts, project_wide_names, counts=False)
            .annotate(
                diagnostic_rank=Window(
                    expression=RowNumber(),
                    partition_by=(F("name"),),
                    order_by=(
                        Lower("component__project__name").asc(),
                        F("component__project_id").asc(),
                    ),
                )
            )
            .filter(diagnostic_rank__lte=DIAGNOSTICS_LINK_LIMIT)
        )

    component_ids = {row["component_id"] for row in [*component_rows, *project_rows]}
    components = _fetch_components(component_ids)
    for row in component_rows:
        groups[row["name"]].add_component(components[row["component_id"]])
    for row in project_rows:
        groups[row["name"]].add_project_component(components[row["component_id"]])


def _get_actionable_groups(
    alerts, user: User, component_names: set[str], project_wide_names: set[str]
) -> dict[str, DiagnosticsGroup]:
    component_rows = list(
        alerts.filter(name__in=component_names).values(
            "name", "severity", "dismissed_at", "component_id", "details"
        )
    )
    project_rows = list(_get_project_rows(alerts, project_wide_names, counts=True))
    component_ids = {row["component_id"] for row in [*component_rows, *project_rows]}
    components = _fetch_components(component_ids)

    addon_components = {
        row["component_id"]: components[row["component_id"]]
        for row in component_rows
        if ALERTS[row["name"]].actionability_uses_addons
    }
    if addon_components:
        # ruff: ignore[import-outside-top-level]
        from weblate.addons.models import Addon

        Addon.objects.prefetch_for_components(list(addon_components.values()))

    groups: dict[str, DiagnosticsGroup] = {}
    for row in component_rows:
        alert_class = ALERTS[row["name"]]
        component = components[row["component_id"]]
        if not alert_class.can_user_act_for(user, component, row["details"]):
            continue
        group = _get_group(groups, row["name"], row["severity"])
        group.add_counts(
            active=int(row["dismissed_at"] is None),
            dismissed=int(row["dismissed_at"] is not None),
        )
        group.add_component(component)

    for row in project_rows:
        alert_class = ALERTS[row["name"]]
        component = components[row["component_id"]]
        if not alert_class.can_user_act_for(user, component, {}):
            continue
        group = _get_group(groups, row["name"], row["severity"])
        group.add_counts(row["active_count"], row["dismissed_count"])
        group.add_project_component(component)
    return groups


def get_diagnostics_context(
    data: QueryDict, user: User, components: QuerySet[Component]
) -> dict[str, object]:
    form = _get_filter_form(data)
    form.is_valid()
    state = form.cleaned_data["diagnostic_state"] or DIAGNOSTICS_STATE_ACTIVE
    severity = form.cleaned_data["diagnostic_severity"]
    category = form.cleaned_data["diagnostic_category"]
    actionable = form.cleaned_data["diagnostic_actionable"]

    load_alerts()
    allowed_names = {
        name
        for name, alert_class in ALERTS.items()
        if not category or alert_class.category == category
    }
    project_wide_names = {name for name in allowed_names if ALERTS[name].project_wide}
    component_names = allowed_names - project_wide_names

    alerts = Alert.objects.filter(
        component__in=components.order_by(), name__in=allowed_names
    )
    if state == DIAGNOSTICS_STATE_ACTIVE:
        alerts = alerts.filter(dismissed_at__isnull=True)
    elif state == DIAGNOSTICS_STATE_DISMISSED:
        alerts = alerts.filter(dismissed_at__isnull=False)
    if severity is not None:
        alerts = alerts.filter(severity=severity)
    if actionable:
        groups = _get_actionable_groups(
            alerts, user, component_names, project_wide_names
        )
    else:
        groups = _get_aggregated_groups(alerts)
        _populate_aggregated_links(alerts, groups)

    result = list(groups.values())
    for group in result:
        group.finalize()
    result.sort(key=lambda group: (-group.severity, str(group.title).casefold()))
    return {"diagnostics": result, "diagnostics_filter": form}
