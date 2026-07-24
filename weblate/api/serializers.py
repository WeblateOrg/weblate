# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from copy import copy, deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast
from zipfile import BadZipfile

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from django.db.models import Model, TextChoices
from django.utils.translation import gettext_lazy
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.plumbing import build_basic_type, build_object_type
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema_field,
    extend_schema_serializer,
)
from drf_standardized_errors.openapi_serializers import (
    ClientErrorEnum,
    ServerErrorEnum,
    ValidationErrorEnum,
)
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.reverse import reverse

from weblate.accounts.models import Profile, Subscription
from weblate.accounts.utils import get_all_user_mails
from weblate.addons.models import ADDONS, Addon
from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group, Permission, Role, User
from weblate.auth.results import PermissionResult
from weblate.checks.models import CHECKS
from weblate.lang.models import Language, Plural, validate_language_code
from weblate.memory.models import Memory, MemoryScope
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.component_copy import (
    get_inherited_component_fields,
    should_copy_component_field,
)
from weblate.trans.defines import (
    BRANCH_LENGTH,
    LANGUAGE_NAME_LENGTH,
    PROJECT_NAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.exceptions import (
    SuggestionSimilarToTranslationError,
    SuggestionTooLongError,
)
from weblate.trans.inherited_settings import (
    INHERITABLE_COMPONENT_SETTINGS,
    apply_create_inheritance_defaults,
)
from weblate.trans.models import (
    Alert,
    Announcement,
    AutoComponentList,
    Category,
    Change,
    Comment,
    Component,
    ComponentList,
    Label,
    Project,
    Report,
    Suggestion,
    SuggestionAddResult,
    Translation,
    Unit,
)
from weblate.trans.models.translation import NewUnitParams
from weblate.trans.util import check_upload_method_permissions, cleanup_repo_url
from weblate.trans.validators import (
    SUGGESTION_REJECTION_REASON_LENGTH,
    get_translation_text_max_length,
)
from weblate.trans.workspace_move import (
    get_project_move_billing_error,
    get_project_workspace_move_permission_error,
)
from weblate.utils.forms import QueryField
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_READONLY, StringState
from weblate.utils.validators import (
    validate_component_zip_upload_size,
    validate_file_extension,
    validate_plural_formula_range,
    validate_translation_upload_size,
)
from weblate.utils.version import GIT_VERSION
from weblate.utils.version_display import VERSION_DISPLAY_HIDE
from weblate.utils.views import (
    create_component_from_doc,
    create_component_from_zip,
    get_form_errors,
    guess_filemask_from_doc,
)
from weblate.vcs.base import RepositoryError
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from uuid import UUID

NEW_UNIT_STATE_CHOICES = tuple(
    choice for choice in StringState.choices if choice[0] != STATE_READONLY
)


def validate_report_component(value: str, user: User | None = None) -> Component:
    components = Component.objects.all()
    if user is not None:
        components = components.filter_access(user)
    try:
        return components.get_by_path(value)
    except (Component.DoesNotExist, Component.MultipleObjectsReturned) as error:
        raise serializers.ValidationError(
            gettext_lazy("Invalid component path.")
        ) from error


class ReportListQuerySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Report.Kind.choices, required=False)
    workspace = serializers.UUIDField(required=False)
    project = serializers.CharField(required=False)
    category = serializers.IntegerField(required=False, min_value=1)
    component = serializers.CharField(required=False)

    def validate_component(self, value: str) -> Component:
        request = self.context.get("request")
        return validate_report_component(
            value, cast("User | None", getattr(request, "user", None))
        )


class ReportCreateSerializer(serializers.Serializer):
    """
    Parameters for generating a report, with at most one optional scope.

    Start and end are required for credits, contributor stats, and translator work.
    Kind-specific optional fields are ignored by other report kinds.
    """

    kind = serializers.ChoiceField(choices=Report.Kind.choices)
    workspace = serializers.UUIDField(required=False)
    project = serializers.SlugField(
        required=False,
        max_length=PROJECT_NAME_LENGTH,
        label=gettext_lazy("URL slug"),
        help_text=gettext_lazy("Name used in URLs and filenames."),
    )
    category = serializers.IntegerField(required=False, min_value=1)
    component = serializers.CharField(required=False)
    start = serializers.DateTimeField(
        required=False,
        help_text=gettext_lazy(
            "Required for credits, contributor stats, and translator work reports."
        ),
    )
    end = serializers.DateTimeField(
        required=False,
        help_text=gettext_lazy(
            "Required for credits, contributor stats, and translator work reports."
        ),
    )
    language = serializers.CharField(required=False, allow_blank=True, default="")
    sort_by = serializers.ChoiceField(
        choices=("count", "date_joined"), required=False, default="count"
    )
    sort_order = serializers.ChoiceField(
        choices=("descending", "ascending"), required=False, default="descending"
    )
    counting_mode = serializers.ChoiceField(
        choices=("unique", "all"), required=False, default="unique"
    )
    q = serializers.CharField(required=False, default="state:<translated")
    base_rate = serializers.DecimalField(
        required=False,
        default=Decimal(1),
        min_value=0,
        max_digits=12,
        decimal_places=4,
    )
    tm_threshold = serializers.IntegerField(
        required=False, default=80, min_value=75, max_value=100
    )
    rate_new = serializers.DecimalField(
        required=False,
        default=Decimal(100),
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_needs_editing = serializers.DecimalField(
        required=False,
        default=Decimal(50),
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_tm_100 = serializers.DecimalField(
        required=False,
        default=Decimal(0),
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_tm_fuzzy = serializers.DecimalField(
        required=False,
        default=Decimal(50),
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_repetition = serializers.DecimalField(
        required=False,
        default=Decimal(0),
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    min_changes = serializers.IntegerField(required=False, default=5, min_value=0)
    max_changes = serializers.IntegerField(required=False, default=1000, min_value=1)
    max_words = serializers.IntegerField(required=False, default=10000, min_value=1)

    @property
    def request_user(self) -> User | None:
        request = self.context.get("request")
        return cast("User | None", getattr(request, "user", None))

    def validate_workspace(self, value: UUID) -> Workspace:
        try:
            workspace = Workspace.objects.get(pk=value)
        except Workspace.DoesNotExist as error:
            raise serializers.ValidationError(
                gettext_lazy("Invalid workspace.")
            ) from error
        if self.request_user is not None and not workspace.can_view(self.request_user):
            raise serializers.ValidationError(gettext_lazy("Invalid workspace."))
        return workspace

    def validate_project(self, value: str) -> Project:
        projects = (
            self.request_user.allowed_projects
            if self.request_user is not None
            else Project.objects.all()
        )
        try:
            return projects.get(slug=value)
        except Project.DoesNotExist as error:
            raise serializers.ValidationError(
                gettext_lazy("Invalid project.")
            ) from error

    def validate_category(self, value: int) -> Category:
        categories = Category.objects.all()
        if self.request_user is not None:
            categories = categories.filter(
                project__in=self.request_user.allowed_projects
            )
        try:
            return categories.get(pk=value)
        except Category.DoesNotExist as error:
            raise serializers.ValidationError(
                gettext_lazy("Invalid category.")
            ) from error

    def validate_component(self, value: str) -> Component:
        return validate_report_component(value, self.request_user)

    def validate(self, attrs):
        forced_scope = self.context.get("scope")
        supplied_scopes = [
            name
            for name in ("workspace", "project", "category", "component")
            if name in attrs
        ]
        if forced_scope is not None and supplied_scopes:
            raise serializers.ValidationError(
                gettext_lazy("Do not specify a scope on a scoped reports endpoint.")
            )
        if len(supplied_scopes) > 1:
            raise serializers.ValidationError(
                gettext_lazy("Choose at most one report scope.")
            )
        scope = forced_scope or (attrs[supplied_scopes[0]] if supplied_scopes else None)
        attrs["scope"] = scope
        kind = attrs["kind"]
        if kind in {
            Report.Kind.CREDITS,
            Report.Kind.CONTRIBUTOR_STATS,
            Report.Kind.TRANSLATOR_WORK,
        }:
            if "start" not in attrs or "end" not in attrs:
                raise serializers.ValidationError(
                    gettext_lazy("Start and end timestamps are required.")
                )
            if attrs["start"] >= attrs["end"]:
                raise serializers.ValidationError(
                    gettext_lazy("The report start must be before its end.")
                )
        if kind == Report.Kind.COST_ESTIMATE:
            try:
                QueryField().clean(attrs["q"])
            except DjangoValidationError as error:
                raise serializers.ValidationError({"q": error.messages}) from error
        if (
            kind == Report.Kind.TRANSLATOR_WORK
            and attrs["min_changes"] > attrs["max_changes"]
        ):
            raise serializers.ValidationError(
                gettext_lazy("Minimum changes can not exceed maximum changes.")
            )
        return attrs

    def get_parameters(self, *, own_data: bool) -> dict[str, Any]:
        data = self.validated_data
        kind = data["kind"]
        common = {"language": data["language"], "own_data": own_data}
        if kind in {Report.Kind.CREDITS, Report.Kind.CONTRIBUTOR_STATS}:
            common.update(
                {
                    "start": data["start"].isoformat(),
                    "end": data["end"].isoformat(),
                    "sort_by": data["sort_by"],
                    "sort_order": data["sort_order"],
                }
            )
            if kind == Report.Kind.CONTRIBUTOR_STATS:
                common["counting_mode"] = data["counting_mode"]
            return common
        if kind == Report.Kind.COST_ESTIMATE:
            common.update(
                {
                    "q": data["q"],
                    "base_rate": str(data["base_rate"]),
                    "tm_threshold": data["tm_threshold"],
                    **{
                        field: str(data[field])
                        for field in (
                            "rate_new",
                            "rate_needs_editing",
                            "rate_tm_100",
                            "rate_tm_fuzzy",
                            "rate_repetition",
                        )
                    },
                }
            )
            return common
        common.update(
            {
                "start": data["start"].isoformat(),
                "end": data["end"].isoformat(),
                "min_changes": data["min_changes"],
                "max_changes": data["max_changes"],
                "max_words": data["max_words"],
            }
        )
        return common


class ScopedReportCreateSerializer(ReportCreateSerializer):
    """
    Parameters for generating a report scoped by the endpoint URL.

    Start and end are required for credits, contributor stats, and translator work.
    Kind-specific optional fields are ignored by other report kinds.
    """

    def get_fields(self):
        fields = super().get_fields()
        for field in ("workspace", "project", "category", "component"):
            fields.pop(field)
        return fields

    def validate(self, attrs):
        if any(
            field in self.initial_data
            for field in ("workspace", "project", "category", "component")
        ):
            raise serializers.ValidationError(
                gettext_lazy("Do not specify a scope on a scoped reports endpoint.")
            )
        return super().validate(attrs)


@extend_schema_field(
    {
        "oneOf": [
            {"type": "object", "additionalProperties": True},
            {"type": "array", "items": {}},
        ]
    }
)
class ReportDataField(serializers.JSONField):
    pass


class ReportListSerializer(serializers.ModelSerializer[Report]):
    kind = serializers.ChoiceField(choices=Report.Kind.choices, read_only=True)
    version = serializers.IntegerField(read_only=True)
    creator = serializers.CharField(source="creator.username", read_only=True)
    scope = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    json_url = serializers.SerializerMethodField()
    html_url = serializers.SerializerMethodField()
    rst_url = serializers.SerializerMethodField()

    def get_scope(self, obj: Report) -> dict[str, str] | None:
        scope = obj.scope
        if scope is None:
            return None
        if isinstance(scope, Workspace):
            scope_type = "workspace"
        elif isinstance(scope, Project):
            scope_type = "project"
        elif isinstance(scope, Category):
            scope_type = "category"
        else:
            scope_type = "component"
        return {scope_type: str(scope.pk), "name": str(scope)}

    @extend_schema_field(serializers.URLField())
    def get_url(self, obj: Report) -> str:
        return reverse(
            "api:report-detail",
            kwargs={"pk": obj.pk},
            request=self.context.get("request"),
        )

    def _format_url(self, obj: Report, style: str) -> str:
        return reverse(
            f"api:report-{style}",
            kwargs={"pk": obj.pk},
            request=self.context.get("request"),
        )

    @extend_schema_field(serializers.URLField())
    def get_json_url(self, obj: Report) -> str:
        return self._format_url(obj, "json")

    @extend_schema_field(serializers.URLField())
    def get_html_url(self, obj: Report) -> str:
        return self._format_url(obj, "html")

    @extend_schema_field(serializers.URLField())
    def get_rst_url(self, obj: Report) -> str:
        return self._format_url(obj, "rst")

    class Meta:
        model = Report
        fields: tuple[str, ...] = (
            "id",
            "kind",
            "version",
            "creator",
            "created",
            "scope",
            "url",
            "json_url",
            "html_url",
            "rst_url",
        )


class ReportSerializer(ReportListSerializer):
    parameters = serializers.DictField(read_only=True)
    data = ReportDataField(read_only=True)

    class Meta(ReportListSerializer.Meta):
        fields = (*ReportListSerializer.Meta.fields, "parameters", "data")


if TYPE_CHECKING:
    from drf_spectacular.openapi import AutoSchema
    from rest_framework.request import Request

_MT = TypeVar("_MT", bound=Model)  # Model Type


@dataclass
class ComponentReference:
    value: str


def resolve_component_reference(
    queryset, value: str | int | ComponentReference
) -> Component:
    """Resolve component reference by numeric ID or full Weblate path."""
    if isinstance(value, Component):
        return value
    if isinstance(value, ComponentReference):
        value = value.value
    if isinstance(value, int):
        return queryset.get(pk=value)

    text = str(value).strip()
    if text.isdigit():
        return queryset.get(pk=int(text))
    return queryset.get_by_path(text)


def resolve_component_reference_with_error(
    queryset, value, field_name: str
) -> Component:
    try:
        return resolve_component_reference(queryset, value)
    except Component.DoesNotExist as error:
        raise serializers.ValidationError(
            {field_name: "Component not found."}
        ) from error


@extend_schema_field(
    {
        "oneOf": [
            build_basic_type(int),
            build_basic_type(str),
        ]
    }
)
class ComponentReferenceField(serializers.CharField):
    def to_internal_value(self, data):
        text = super().to_internal_value(str(data))
        return ComponentReference(text)


class ComponentReferenceListField(serializers.ListField):
    child = ComponentReferenceField()

    def get_value(self, dictionary):
        if hasattr(dictionary, "getlist"):
            values = dictionary.getlist(self.field_name)
            if values:
                return values
        return super().get_value(dictionary)


def get_reverse_kwargs(
    obj, lookup_field: tuple[str, ...], strip_parts: int = 0
) -> dict[str, str] | None:
    kwargs = {}
    was_slug = False
    for lookup in lookup_field:
        value = obj
        for key in lookup.split("__"):
            # NULL value
            if value is None:
                return None
            previous = value
            value = getattr(value, key)
            if key == "slug":
                if was_slug and previous.category:
                    value = "%2F".join((*previous.category.get_url_path()[1:], value))
                was_slug = True
        if strip_parts:
            lookup = "__".join(lookup.split("__")[strip_parts:])
        kwargs[lookup] = value
    return kwargs


class MultiFieldHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    lookup_field: tuple[str, ...]  # type: ignore[assignment]

    def __init__(
        self, lookup_field: tuple[str, ...], strip_parts: int = 0, **kwargs
    ) -> None:
        self.strip_parts = strip_parts
        super().__init__(**kwargs)
        self.lookup_field = lookup_field

    # pylint: disable-next=redefined-builtin
    def get_url(self, obj, view_name, request: Request, format):  # ruff: ignore[builtin-argument-shadowing]
        """
        Given an object, return the URL that hyperlinks to the object.

        May raise a `NoReverseMatch` if the `view_name` and `lookup_field` attributes
        are not configured to correctly match the URL conf.
        """
        # Unsaved objects will not yet have a valid URL.
        if not getattr(obj, "pk", None):
            return None

        kwargs = get_reverse_kwargs(obj, self.lookup_field, self.strip_parts)
        if kwargs is None:
            return None
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)


class AbsoluteURLField(serializers.CharField):
    def get_attribute(self, instance):
        value = cast("str", super().get_attribute(instance))
        if "http:/" not in value and "https:/" not in value:
            return get_site_url(value)
        return value


class RemovableSerializer(serializers.ModelSerializer[_MT]):
    def __init__(self, *args, **kwargs) -> None:
        remove_fields = kwargs.pop("remove_fields", None)
        super().__init__(*args, **kwargs)

        if remove_fields:
            # for multiple fields in a list
            for field_name in remove_fields:
                self.fields.pop(field_name)


class LanguagePluralSerializer(serializers.ModelSerializer[Plural]):
    class Meta:
        model = Plural
        fields = (
            "id",
            "source",
            "number",
            "formula",
            "type",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        number = attrs.get("number", getattr(self.instance, "number", 2))
        formula = attrs.get("formula", getattr(self.instance, "formula", "n != 1"))
        try:
            validate_plural_formula_range(number, formula)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"formula": error.messages}) from error
        return attrs


class LanguageSerializer(serializers.ModelSerializer[Language]):
    name = serializers.CharField(required=False, max_length=LANGUAGE_NAME_LENGTH)
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    plural = LanguagePluralSerializer(required=False)
    aliases = serializers.ListField(source="get_aliases_names", read_only=True)
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:language-statistics", lookup_field="code"
    )

    class Meta:
        model = Language
        fields = (
            "id",
            "code",
            "name",
            "plural",
            "aliases",
            "direction",
            "population",
            "web_url",
            "url",
            "statistics_url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:language-detail", "lookup_field": "code"},
            "code": {"validators": [validate_language_code]},
        }

    @property
    def is_source_language(self):
        return (
            isinstance(self.parent, ComponentSerializer)
            and self.field_name == "source_language"
        )

    def validate_code(self, value):
        try:
            validate_language_code(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

        check_query = Language.objects.filter(code=value)
        if not check_query.exists() and self.is_source_language:
            msg = "Language with this language code was not found."
            raise serializers.ValidationError(msg)
        return value

    def validate_plural(self, value):
        if not value and not self.is_source_language:
            msg = "This field is required."
            raise serializers.ValidationError(msg)
        return value

    def validate_name(self, value):
        if not value and not self.is_source_language:
            msg = "This field is required."
            raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data):
        plural_validated = validated_data.pop("plural", None)
        if not plural_validated:
            msg = "No valid plural data was provided."
            raise serializers.ValidationError(msg)

        check_query = Language.objects.filter(code=validated_data.get("code"))
        if check_query.exists():
            msg = "Language with this Language code already exists."
            raise serializers.ValidationError(msg)
        language = super().create(validated_data)
        plural = Plural(language=language, **plural_validated)
        plural.save()
        return language

    def get_value(self, dictionary):
        if self.is_source_language and "source_language" in dictionary:
            value = dictionary["source_language"]
            if isinstance(value, str):
                return {"code": value}
        return super().get_value(dictionary)


PROFILE_READONLY_FIELDS = (
    "suggested",
    "translated",
    "uploaded",
    "commented",
    "last_2fa",
    # fields below can be edited via custom logic
    "languages",
    "secondary_languages",
    "watched",
    "dashboard_component_list",
)


@extend_schema_field(serializers.EmailField())
class ProfileEmailChoiceField(serializers.ChoiceField):
    """Choice field with runtime choices documented as an email in OpenAPI."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("choices", [])
        super().__init__(**kwargs)


@extend_schema_field(serializers.ChoiceField(choices=Profile.CommitNameChoices.choices))
class ProfileCommitNameChoiceField(serializers.ChoiceField):
    """Choice field with optional runtime choices documented in OpenAPI."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("choices", Profile.CommitNameChoices.choices)
        super().__init__(**kwargs)


PROFILE_M2M_FIELDS: ClassVar[dict[str, tuple[type[Model], str]]] = {
    "languages": (Language, "code"),
    "secondary_languages": (Language, "code"),
    "watched": (Project, "slug"),
}


@extend_schema_field(serializers.ListField(child=serializers.URLField()))
class AllowedProjectsField(serializers.Field):
    """Hyperlinked allowed projects filtered by the viewer's ACL."""

    def to_representation(self, value):
        request = self.context["request"]
        projects = value.all()
        user = request.user
        if hasattr(user, "allowed_projects"):
            projects &= user.allowed_projects
        return [
            reverse(
                "api:project-detail",
                kwargs={"slug": project.slug},
                request=request,
            )
            for project in projects.order()
        ]


class ProfileSerializer(serializers.ModelSerializer[Profile]):
    languages = serializers.HyperlinkedIdentityField(
        view_name="api:language-detail",
        lookup_field="code",
        many=True,
        read_only=True,
    )
    secondary_languages = serializers.HyperlinkedIdentityField(
        view_name="api:language-detail",
        lookup_field="code",
        many=True,
        read_only=True,
    )
    watched = AllowedProjectsField(read_only=True)
    dashboard_component_list = serializers.HyperlinkedRelatedField(
        view_name="api:componentlist-detail",
        lookup_field="slug",
        read_only=True,
        allow_null=True,
    )
    commit_email = ProfileEmailChoiceField()
    public_email = ProfileEmailChoiceField()
    commit_name = ProfileCommitNameChoiceField()

    class Meta:
        model = Profile
        fields = (
            "language",
            "languages",
            "secondary_languages",
            "suggested",
            "translated",
            "uploaded",
            "commented",
            "theme",
            "hide_completed",
            "secondary_in_zen",
            "hide_source_secondary",
            "editor_link",
            "translate_mode",
            "zen_mode",
            "special_chars",
            "nearby_strings",
            "auto_watch",
            "contribute_personal_tm",
            "dashboard_component_list",
            "watched",
            "website",
            "contact",
            "liberapay",
            "fediverse",
            "codesite",
            "github",
            "twitter",
            "linkedin",
            "location",
            "company",
            "public_email",
            "commit_email",
            "commit_name",
            "last_2fa",
        )
        read_only_fields = PROFILE_READONLY_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields[
                "public_email"
            ].choices = self.instance.get_public_email_choices()
            self.fields[
                "commit_email"
            ].choices = self.instance.get_commit_email_choices()
            self.fields["commit_name"].choices = self.instance.get_commit_name_choices()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        initial_data = getattr(self, "initial_data", None)
        if isinstance(initial_data, dict):
            self._validate_m2m_fields()
            if "dashboard_component_list" in initial_data:
                self._validate_dashboard_component_list(
                    initial_data["dashboard_component_list"]
                )
        return attrs

    def _validate_dashboard_component_list(self, value: str | None) -> None:
        if value is None:
            return
        if not isinstance(value, str):
            raise serializers.ValidationError(
                gettext_lazy("Expected a string or null.")
            )
        try:
            component_list = ComponentList.objects.get(slug=value)
            if component_list not in self.instance.allowed_dashboard_component_lists:
                raise serializers.ValidationError(
                    gettext_lazy("Invalid value: %(value)s") % {"value": value}
                )
        except ComponentList.DoesNotExist as e:
            raise serializers.ValidationError(
                gettext_lazy("Invalid value: %(value)s") % {"value": value}
            ) from e

    def _validate_m2m_fields(self) -> None:
        errors: dict[str, Any] = {}
        for field, (model, lookup) in PROFILE_M2M_FIELDS.items():
            if field not in self.initial_data:
                continue
            values = self.initial_data[field]
            if values is None:
                continue
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                errors[field] = gettext_lazy("Expected a list of items.")
                continue
            found = set(
                model.objects.filter(**{f"{lookup}__in": values}).values_list(
                    lookup, flat=True
                )
            )
            missing = sorted(set(values) - found)
            if missing:
                errors[field] = gettext_lazy("Invalid value: %(value)s") % {
                    "value": ", ".join(missing)
                }
                continue

            if field == "watched" and (request := self.context.get("request")):
                allowed = set(
                    request.user.allowed_projects.filter(slug__in=values).values_list(
                        "slug", flat=True
                    )
                )
                disallowed = sorted(set(values) - allowed)
                if disallowed:
                    errors[field] = gettext_lazy("Invalid value: %(value)s") % {
                        "value": ", ".join(disallowed)
                    }
        if errors:
            raise serializers.ValidationError(errors)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if isinstance(self.initial_data, dict):
            for field, (model, lookup) in PROFILE_M2M_FIELDS.items():
                if field not in self.initial_data:
                    continue
                values = self.initial_data[field]
                relation = getattr(instance, field)
                if values is None:
                    relation.clear()
                else:
                    relation.set(model.objects.filter(**{f"{lookup}__in": values}))
            if "dashboard_component_list" in self.initial_data:
                dashboard_cl = self.initial_data["dashboard_component_list"]
                update_fields = ["dashboard_component_list", "dashboard_view"]
                if dashboard_cl is None:
                    instance.dashboard_component_list = None
                    if instance.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST:
                        instance.dashboard_view = Profile.DASHBOARD_WATCHED
                else:
                    instance.dashboard_component_list = ComponentList.objects.get(
                        slug=dashboard_cl
                    )
                    instance.dashboard_view = Profile.DASHBOARD_COMPONENT_LIST
                instance.save(update_fields=update_fields)
        return instance


class ProfileUpdateMixin:
    profile_field = "profile"
    _profile_serializer: ProfileSerializer | None = None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._profile_serializer = None
        initial_data = getattr(self, "initial_data", None)
        if not isinstance(initial_data, dict):
            return attrs
        profile_data = initial_data.get(self.profile_field)
        if profile_data is None:
            return attrs
        if not isinstance(profile_data, dict):
            msg = "Expected an object."
            raise serializers.ValidationError({self.profile_field: msg})

        if self.instance is not None:
            profile_serializer = ProfileSerializer(
                self.instance.profile,
                data=profile_data,
                partial=True,
                context=self.context,
            )
            if not profile_serializer.is_valid():
                raise serializers.ValidationError(
                    {self.profile_field: profile_serializer.errors}
                )
            self._profile_serializer = profile_serializer
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if self._profile_serializer is not None:
                self._profile_serializer.save()
        return instance


class FullUserSerializer(ProfileUpdateMixin, serializers.ModelSerializer[User]):
    privileged_fields = (
        "groups",
        "is_superuser",
        "is_active",
        "is_bot",
        "date_expires",
    )
    groups = serializers.HyperlinkedIdentityField(
        view_name="api:group-detail",
        lookup_field="id",
        many=True,
        read_only=True,
    )
    profile = ProfileSerializer(read_only=True)
    notifications = serializers.HyperlinkedIdentityField(
        view_name="api:user-notifications",
        lookup_field="username",
        source="subscriptions",
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:user-statistics", lookup_field="username"
    )
    contributions_url = serializers.HyperlinkedIdentityField(
        view_name="api:user-contributions", lookup_field="username"
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if self.context.get("view") is not None and getattr(
            self.context["view"], "swagger_fake_view", False
        ):
            return fields
        if request is None or not request.user.has_perm("user.edit"):
            for field_name in self.privileged_fields:
                fields[field_name].read_only = True
        return fields

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "username",
            "groups",
            "profile",
            "notifications",
            "is_superuser",
            "is_active",
            "is_bot",
            "date_joined",
            "date_expires",
            "last_login",
            "url",
            "statistics_url",
            "contributions_url",
        )
        read_only_fields = (
            "id",
            "date_joined",
            "last_login",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"}
        }


class ProfileUpdateRequestSerializer(ProfileSerializer):
    """Schema-only profile serializer for update request bodies."""

    languages = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )
    secondary_languages = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )
    watched = serializers.ListField(
        child=serializers.SlugField(), required=False, allow_null=True
    )
    dashboard_component_list = serializers.SlugField(required=False, allow_null=True)


class UserUpdateRequestSerializer(FullUserSerializer):
    """
    Schema-only serializer for user update requests.

    Writable nested fields are not supported by default in .update()
    'profile' field update logic is handled by ProfileUpdateMixin
    """

    profile = ProfileUpdateRequestSerializer(required=False)


class SelfUserSerializer(ProfileUpdateMixin, serializers.ModelSerializer[User]):
    profile = ProfileSerializer(read_only=True)

    def validate_email(self, value: str | None) -> str | None:
        if self.instance is not None:
            if value is None and self.instance.email is None:
                return value
            if value is not None and any(
                value.casefold() == email.casefold()
                for email in get_all_user_mails(self.instance)
            ):
                return value
        raise serializers.ValidationError(
            gettext_lazy("This e-mail address has not been verified.")
        )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "username",
            "profile",
        )
        read_only_fields = (
            "id",
            "username",
        )
        # Self-service PUT must accept the fields returned by the basic self view.
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "email": {"required": False},
        }


class BasicUserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "username",
        )
        read_only_fields = ("id",)


@extend_schema_field(str)
class PermissionSerializer(serializers.RelatedField[Permission, str, str]):
    class Meta:
        model = Permission

    def to_representation(self, value):
        return value.codename

    def get_queryset(self):
        return Permission.objects.all()

    def to_internal_value(self, data):
        check_query = Permission.objects.filter(codename=data)
        if not check_query.exists():
            msg = "Permission with this codename was not found."
            raise serializers.ValidationError(msg)
        return data


class DefiningProjectField(serializers.HyperlinkedRelatedField):
    def get_queryset(self):
        request = self.context.get("request")
        if request is None:
            return Project.objects.none()
        if request.user.has_perm("group.edit"):
            return Project.objects.all()
        return request.user.projects_with_perm("project.permissions")

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            request = self.context.get("request")
            if request is not None and not request.user.has_perm("group.edit"):
                raise PermissionDenied from None
            raise


class DefiningWorkspaceField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        request = self.context.get("request")
        if request is None:
            return Workspace.objects.none()
        if request.user.has_perm("group.edit"):
            return Workspace.objects.all()
        return request.user.workspaces_with_perm("workspace.edit_members")

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            request = self.context.get("request")
            if request is not None and not request.user.has_perm("group.edit"):
                raise PermissionDenied from None
            raise


class RoleSerializer(serializers.ModelSerializer[Role]):
    permissions = PermissionSerializer(many=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "name",
            "permissions",
            "url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:role-detail", "lookup_field": "id"},
        }

    def create(self, validated_data):
        permissions_validated = validated_data.pop("permissions", [])
        role = Role.objects.create(**validated_data)
        role.permissions.add(
            *Permission.objects.filter(codename__in=permissions_validated)
        )
        return role

    def update(self, instance, validated_data):
        permissions_validated = validated_data.pop("permissions", [])
        instance.name = validated_data.get("name", instance.name)
        instance.save()
        if self.partial:
            instance.permissions.add(
                *Permission.objects.filter(codename__in=permissions_validated)
            )
        else:
            instance.permissions.set(
                Permission.objects.filter(codename__in=permissions_validated)
            )
        return instance


class CommentSerializer(serializers.Serializer[Comment]):
    scope = serializers.ChoiceField(
        choices=["report", "global", "translation"],
        label=gettext_lazy("Scope"),
        help_text=gettext_lazy(
            "Is your comment specific to this translation, or generic for all of them?"
        ),
        write_only=True,
    )
    comment = serializers.CharField(
        max_length=1000,
        label=gettext_lazy("Comment text"),
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
    )
    timestamp = serializers.DateTimeField(
        required=False,
        label=gettext_lazy("Creation timestamp"),
        help_text=gettext_lazy(
            "If you’re an admin, you can set the explicit timestamp at which the comment was created."
        ),
    )
    user_email = serializers.EmailField(
        required=False,
        label=gettext_lazy("Commenter’s email"),
        help_text=gettext_lazy(
            "If you’re an admin, you can attribute this comment to another user by their email."
        ),
        write_only=True,
    )

    id = serializers.IntegerField(read_only=True)
    user: serializers.HyperlinkedRelatedField[User] = (
        serializers.HyperlinkedRelatedField(
            read_only=True, view_name="api:user-detail", lookup_field="username"
        )
    )

    class Meta:
        model = Comment
        fields = ("scope", "comment", "timestamp", "user_email", "id", "user")

    def validate_scope(self, value):
        unit: Unit | None = self.context.get("unit", None)
        if unit is None:
            return value

        # Remove bug-report in case source review is not enabled
        if value == "report" and not unit.translation.component.project.source_review:
            msg = f'"{value}" is not a valid choice as source review is disabled.'
            raise serializers.ValidationError(msg)

        # Remove translation comment when commenting on source
        if value == "translation" and unit.translation.is_source:
            msg = f'"{value}" is not a valid choice for source units.'
            raise serializers.ValidationError(msg)

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        unit: Unit | None = self.context.get("unit")
        if (
            attrs.get("timestamp") is not None or attrs.get("user_email") is not None
        ) and (
            request is None
            or unit is None
            or not request.user.has_perm(
                "project.edit", unit.translation.component.project
            )
        ):
            raise PermissionDenied

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        unit = self.context["unit"]

        text = validated_data.pop("comment")
        scope = validated_data.pop("scope")
        timestamp = validated_data.pop("timestamp", None)
        user_email = validated_data.pop("user_email", None)

        user = request.user
        if user_email:
            override = User.objects.filter(email=user_email).first()
            if override:
                user = override

        return Comment.objects.add(
            request=request,
            unit=unit,
            text=text,
            scope=scope,
            user=user,
            timestamp=timestamp,
        )


class GroupSerializer(serializers.ModelSerializer[Group]):
    internal_fields = (
        "name",
        "project_selection",
        "language_selection",
        "defining_project",
        "defining_workspace",
    )
    roles = serializers.HyperlinkedIdentityField(
        view_name="api:role-detail",
        lookup_field="id",
        many=True,
        read_only=True,
    )
    languages = serializers.HyperlinkedIdentityField(
        view_name="api:language-detail",
        lookup_field="code",
        many=True,
        read_only=True,
    )
    projects = serializers.HyperlinkedIdentityField(
        view_name="api:project-detail",
        lookup_field="slug",
        many=True,
        read_only=True,
    )
    componentlists: serializers.HyperlinkedRelatedField[ComponentList] = (
        serializers.HyperlinkedRelatedField(
            view_name="api:componentlist-detail",
            lookup_field="slug",
            many=True,
            read_only=True,
        )
    )
    components = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("project__slug", "slug"),
        many=True,
        read_only=True,
    )
    defining_project = DefiningProjectField(
        view_name="api:project-detail",
        lookup_field="slug",
        required=False,
    )
    defining_workspace = DefiningWorkspaceField(required=False, allow_null=True)
    admins: serializers.HyperlinkedRelatedField[User] = (
        serializers.HyperlinkedRelatedField(
            view_name="api:user-detail",
            lookup_field="username",
            many=True,
            read_only=True,
        )
    )

    class Meta:
        model = Group
        fields = (
            "id",
            "name",
            "defining_project",
            "defining_workspace",
            "project_selection",
            "language_selection",
            "url",
            "roles",
            "languages",
            "projects",
            "componentlists",
            "components",
            "enforced_2fa",
            "admins",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:group-detail", "lookup_field": "id"},
        }
        validators = ()

    def validate(self, attrs):
        defining_workspace = attrs.get(
            "defining_workspace",
            self.instance.defining_workspace if self.instance is not None else None,
        )
        if defining_workspace is not None:
            attrs["language_selection"] = SELECTION_ALL
        if self.instance is not None and self.instance.internal:
            errors = {}
            for field in self.internal_fields:
                if field not in attrs:
                    continue
                value = attrs[field]
                instance_value = getattr(self.instance, field)
                if (
                    field == "language_selection"
                    and self.instance.defining_workspace_id
                ):
                    instance_value = SELECTION_ALL
                if value != instance_value:
                    errors[field] = gettext_lazy(
                        "Cannot change this on a built-in team."
                    )
            if errors:
                raise serializers.ValidationError(errors)
        if (
            self.instance is not None
            and "defining_project" in attrs
            and attrs["defining_project"] != self.instance.defining_project
        ):
            raise serializers.ValidationError(
                {
                    "defining_project": gettext_lazy(
                        "Cannot change this on an existing team."
                    )
                }
            )
        if (
            self.instance is not None
            and "defining_workspace" in attrs
            and attrs["defining_workspace"] != self.instance.defining_workspace
        ):
            raise serializers.ValidationError(
                {
                    "defining_workspace": gettext_lazy(
                        "Cannot change this on an existing team."
                    )
                }
            )
        if attrs.get("defining_project") and attrs.get("defining_workspace"):
            raise serializers.ValidationError(
                {
                    "defining_workspace": gettext_lazy(
                        "Choose either a project or a workspace."
                    )
                }
            )
        name = attrs.get(
            "name", self.instance.name if self.instance is not None else None
        )
        if (
            defining_workspace is not None
            and name is not None
            and Group.objects.filter(defining_workspace=defining_workspace, name=name)
            .exclude(pk=self.instance.pk if self.instance is not None else None)
            .exists()
        ):
            raise serializers.ValidationError(
                {
                    "name": gettext_lazy(
                        "A team with this name already exists in this workspace."
                    )
                }
            )
        if (
            self.instance is not None
            and (
                self.instance.defining_project is not None
                or self.instance.defining_workspace is not None
            )
            and (
                "project_selection" in attrs
                and attrs["project_selection"] != self.instance.project_selection
            )
        ):
            raise serializers.ValidationError(
                {
                    "project_selection": gettext_lazy(
                        "Cannot change this on a scoped team."
                    )
                }
            )
        return attrs

    def create(self, validated_data):
        defining_project = validated_data.get("defining_project")
        defining_workspace = validated_data.get("defining_workspace")
        if defining_project is not None or defining_workspace is not None:
            validated_data["project_selection"] = SELECTION_MANUAL
        if defining_workspace is not None:
            validated_data["language_selection"] = SELECTION_ALL

        group = super().create(validated_data)
        if defining_project is not None:
            group.projects.add(defining_project)
        return group


class ProjectSerializer(serializers.ModelSerializer[Project]):
    workspace = serializers.PrimaryKeyRelatedField(
        queryset=Workspace.objects.all(), required=False, allow_null=True
    )
    effective_license = serializers.SerializerMethodField()
    effective_agreement = serializers.SerializerMethodField()
    effective_new_lang = serializers.SerializerMethodField()
    effective_language_code_style = serializers.SerializerMethodField()
    effective_secondary_language = serializers.SerializerMethodField()
    effective_commit_message = serializers.SerializerMethodField()
    effective_add_message = serializers.SerializerMethodField()
    effective_delete_message = serializers.SerializerMethodField()
    effective_merge_message = serializers.SerializerMethodField()
    effective_addon_message = serializers.SerializerMethodField()
    effective_pull_message = serializers.SerializerMethodField()
    effective_check_flags = serializers.SerializerMethodField()
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    components_list_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-components", lookup_field="slug"
    )
    changes_list_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-changes", lookup_field="slug"
    )
    repository_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-repository", lookup_field="slug"
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-statistics", lookup_field="slug"
    )
    categories_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-categories", lookup_field="slug"
    )
    languages_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-languages", lookup_field="slug"
    )
    labels_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-labels", lookup_field="slug"
    )
    reports_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-reports", lookup_field="slug"
    )
    lock_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-lock", lookup_field="slug"
    )
    machinery_settings = serializers.HyperlinkedIdentityField(
        view_name="api:project-machinery-settings", lookup_field="slug"
    )
    locked = serializers.BooleanField(read_only=True)
    announcements_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-announcements", lookup_field="slug"
    )

    class Meta:
        model = Project
        fields = (
            "name",
            "slug",
            "id",
            "web",
            "web_url",
            "url",
            "check_flags",
            "effective_check_flags",
            "components_list_url",
            "repository_url",
            "statistics_url",
            "categories_url",
            "changes_list_url",
            "languages_url",
            "labels_url",
            "reports_url",
            "lock_url",
            "translation_review",
            "source_review",
            "commit_policy",
            "workspace",
            "instructions",
            "enable_hooks",
            "language_aliases",
            "license",
            "inherit_license",
            "effective_license",
            "agreement",
            "inherit_agreement",
            "effective_agreement",
            "new_lang",
            "inherit_new_lang",
            "effective_new_lang",
            "language_code_style",
            "inherit_language_code_style",
            "effective_language_code_style",
            "secondary_language",
            "inherit_secondary_language",
            "effective_secondary_language",
            "commit_message",
            "inherit_commit_message",
            "effective_commit_message",
            "add_message",
            "inherit_add_message",
            "effective_add_message",
            "delete_message",
            "inherit_delete_message",
            "effective_delete_message",
            "merge_message",
            "inherit_merge_message",
            "effective_merge_message",
            "addon_message",
            "inherit_addon_message",
            "effective_addon_message",
            "pull_message",
            "inherit_pull_message",
            "effective_pull_message",
            "enforced_2fa",
            "machinery_settings",
            "locked",
            "announcements_url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:project-detail", "lookup_field": "slug"}
        }

    def get_effective_license(self, obj: Project) -> str:
        return obj.get_effective_setting("license")

    def get_effective_agreement(self, obj: Project) -> str:
        return obj.get_effective_setting("agreement")

    def get_effective_new_lang(self, obj: Project) -> str:
        return obj.get_effective_setting("new_lang")

    def get_effective_language_code_style(self, obj: Project) -> str:
        return obj.get_effective_setting("language_code_style")

    def get_effective_secondary_language(self, obj: Project) -> int | None:
        language = obj.get_effective_setting("secondary_language")
        return language.pk if language else None

    def get_effective_commit_message(self, obj: Project) -> str:
        return obj.get_effective_setting("commit_message")

    def get_effective_add_message(self, obj: Project) -> str:
        return obj.get_effective_setting("add_message")

    def get_effective_delete_message(self, obj: Project) -> str:
        return obj.get_effective_setting("delete_message")

    def get_effective_merge_message(self, obj: Project) -> str:
        return obj.get_effective_setting("merge_message")

    def get_effective_addon_message(self, obj: Project) -> str:
        return obj.get_effective_setting("addon_message")

    def get_effective_pull_message(self, obj: Project) -> str:
        return obj.get_effective_setting("pull_message")

    def get_effective_check_flags(self, obj: Project) -> str:
        return obj.effective_check_flags.format()

    def create(self, validated_data):
        has_workspace = validated_data.get("workspace") is not None
        initial_data = getattr(self, "initial_data", {})
        for field in INHERITABLE_COMPONENT_SETTINGS:
            inherit_field = f"inherit_{field}"
            if inherit_field in initial_data:
                continue
            validated_data[inherit_field] = has_workspace and field not in initial_data
        return super().create(validated_data)

    def validate(self, attrs):
        if self.instance is not None and "workspace" in attrs:
            workspace = attrs["workspace"]
            workspace_id = workspace.pk if workspace else None
            if workspace_id != self.instance.workspace_id:
                request = self.context.get("request")
                if request is None:
                    raise PermissionDenied
                if error := get_project_workspace_move_permission_error(
                    request.user, self.instance, workspace
                ):
                    raise PermissionDenied(error)
                if error := get_project_move_billing_error(workspace):
                    raise serializers.ValidationError({"workspace": error})
        # Call model validation here, DRF does not do that
        if self.instance:
            instance = copy(self.instance)
            for key, value in attrs.items():
                setattr(instance, key, value)
        else:
            instance = Project(**attrs)
        instance.clean()
        return attrs


class LinkedField(serializers.CharField):
    def get_attribute(self, instance):
        if instance.linked_component:
            instance = instance.linked_component
        return getattr(instance, self.source)


class RepoField(LinkedField):
    def get_attribute(self, instance):
        url = super().get_attribute(instance)
        if not settings.HIDE_REPO_CREDENTIALS:
            return url
        return cleanup_repo_url(url)


class RelatedTaskField(serializers.HyperlinkedRelatedField):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            "api:task-detail",
            read_only=True,
            allow_null=True,
            lookup_url_kwarg="pk",
            **kwargs,
        )

    def get_attribute(self, instance):
        return instance

    # pylint: disable-next=redefined-builtin
    def get_url(self, obj, view_name, request: Request, format):  # ruff: ignore[builtin-argument-shadowing]
        if not obj.in_progress():
            return None
        return super().get_url(obj, view_name, request, format)


class ComponentSerializer(RemovableSerializer[Component]):
    forbidden_from_component_override_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "source_language",
            "filemask",
            "template",
            "edit_template",
            "intermediate",
            "new_base",
            "file_format",
            "file_format_params",
            "language_code_style",
            "language_regex",
            "key_filter",
            "variant_regex",
            "manage_units",
        }
    )
    linked_repository_setting_fields: ClassVar[frozenset[str]] = frozenset(
        Component.LINKED_REPOSITORY_SETTINGS
    )
    linked_repository_setting_error = Component.LINKED_REPOSITORY_SETTING_MESSAGE
    duplicated_component_fields = get_inherited_component_fields(
        "repo",
        "branch",
        "push",
        "push_branch",
        "filemask",
        "screenshot_filemask",
        "template",
        "intermediate",
        "new_base",
        "file_format",
        "repoweb",
        "merge_style",
        "auto_lock_error",
        "language_regex",
        "is_glossary",
        "glossary_color",
    )
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    project = ProjectSerializer(read_only=True)
    repository_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-repository", lookup_field=("project__slug", "slug")
    )
    translations_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-translations", lookup_field=("project__slug", "slug")
    )
    statistics_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-statistics", lookup_field=("project__slug", "slug")
    )
    lock_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-lock", lookup_field=("project__slug", "slug")
    )
    links_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-links", lookup_field=("project__slug", "slug")
    )
    changes_list_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-changes", lookup_field=("project__slug", "slug")
    )
    reports_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-reports", lookup_field=("project__slug", "slug")
    )
    license_url = serializers.CharField(read_only=True)
    effective_license = serializers.SerializerMethodField()
    effective_agreement = serializers.SerializerMethodField()
    effective_new_lang = serializers.SerializerMethodField()
    effective_language_code_style = serializers.SerializerMethodField()
    effective_secondary_language = serializers.SerializerMethodField()
    effective_commit_message = serializers.SerializerMethodField()
    effective_add_message = serializers.SerializerMethodField()
    effective_delete_message = serializers.SerializerMethodField()
    effective_merge_message = serializers.SerializerMethodField()
    effective_addon_message = serializers.SerializerMethodField()
    effective_pull_message = serializers.SerializerMethodField()
    effective_check_flags = serializers.SerializerMethodField()
    announcements_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-announcements", lookup_field=("project__slug", "slug")
    )
    source_language = LanguageSerializer(required=False)

    repo = RepoField(max_length=REPO_LENGTH)

    push = RepoField(required=False, allow_blank=True, max_length=REPO_LENGTH)
    branch = LinkedField(required=False, allow_blank=True, max_length=BRANCH_LENGTH)
    push_branch = LinkedField(
        required=False, allow_blank=True, max_length=BRANCH_LENGTH
    )
    locked = serializers.BooleanField(read_only=True)

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    zipfile = serializers.FileField(
        required=False, validators=[validate_component_zip_upload_size]
    )
    docfile = serializers.FileField(
        required=False,
        validators=[validate_translation_upload_size, validate_file_extension],
    )
    from_component = ComponentReferenceField(required=False, write_only=True)
    disable_autoshare = serializers.BooleanField(required=False)

    enforced_checks = serializers.JSONField(required=False)

    category = serializers.HyperlinkedRelatedField(
        view_name="api:category-detail",
        queryset=Category.objects.none(),
        required=False,
        allow_null=True,
    )
    linked_component = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("linked_component__project__slug", "linked_component__slug"),
        strip_parts=1,
        read_only=True,
    )

    task_url = RelatedTaskField(lookup_field="background_task_id")

    addons = serializers.HyperlinkedIdentityField(
        view_name="api:addon-detail",
        source="addon_set",
        many=True,
        read_only=True,
    )

    def get_effective_license(self, obj: Component) -> str:
        return obj.effective_license

    def get_effective_agreement(self, obj: Component) -> str:
        return obj.effective_agreement

    def get_effective_new_lang(self, obj: Component) -> str:
        return obj.effective_new_lang

    def get_effective_language_code_style(self, obj: Component) -> str:
        return obj.effective_language_code_style

    def get_effective_secondary_language(self, obj: Component) -> int | None:
        language = obj.effective_secondary_language
        return language.pk if language else None

    def get_effective_commit_message(self, obj: Component) -> str:
        return obj.effective_commit_message

    def get_effective_add_message(self, obj: Component) -> str:
        return obj.effective_add_message

    def get_effective_delete_message(self, obj: Component) -> str:
        return obj.effective_delete_message

    def get_effective_merge_message(self, obj: Component) -> str:
        return obj.effective_merge_message

    def get_effective_addon_message(self, obj: Component) -> str:
        return obj.effective_addon_message

    def get_effective_pull_message(self, obj: Component) -> str:
        return obj.effective_pull_message

    def get_effective_check_flags(self, obj: Component) -> str:
        return obj.all_flags.format()

    class Meta:
        model = Component
        fields: tuple[str, ...] = (
            "name",
            "slug",
            "id",
            "source_language",
            "project",
            "vcs",
            "repo",
            "git_export",
            "branch",
            "push_branch",
            "filemask",
            "screenshot_filemask",
            "template",
            "edit_template",
            "intermediate",
            "new_base",
            "file_format",
            "file_format_params",
            "license",
            "inherit_license",
            "effective_license",
            "license_url",
            "announcements_url",
            "agreement",
            "inherit_agreement",
            "effective_agreement",
            "web_url",
            "url",
            "repository_url",
            "translations_url",
            "statistics_url",
            "lock_url",
            "links_url",
            "changes_list_url",
            "task_url",
            "reports_url",
            "new_lang",
            "inherit_new_lang",
            "effective_new_lang",
            "language_code_style",
            "inherit_language_code_style",
            "effective_language_code_style",
            "push",
            "check_flags",
            "effective_check_flags",
            "priority",
            "enforced_checks",
            "restricted",
            "repoweb",
            "report_source_bugs",
            "merge_style",
            "commit_message",
            "inherit_commit_message",
            "effective_commit_message",
            "add_message",
            "inherit_add_message",
            "effective_add_message",
            "delete_message",
            "inherit_delete_message",
            "effective_delete_message",
            "merge_message",
            "inherit_merge_message",
            "effective_merge_message",
            "addon_message",
            "inherit_addon_message",
            "effective_addon_message",
            "pull_message",
            "inherit_pull_message",
            "effective_pull_message",
            "allow_translation_propagation",
            "manage_units",
            "enable_suggestions",
            "suggestion_voting",
            "suggestion_autoaccept",
            "push_on_commit",
            "commit_pending_age",
            "auto_lock_error",
            "language_regex",
            "key_filter",
            "secondary_language",
            "inherit_secondary_language",
            "effective_secondary_language",
            "variant_regex",
            "zipfile",
            "docfile",
            "from_component",
            "addons",
            "is_glossary",
            "glossary_color",
            "disable_autoshare",
            "category",
            "linked_component",
            "locked",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {
                "view_name": "api:component-detail",
                "lookup_field": ("project__slug", "slug"),
            }
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        project = None
        if isinstance(self.instance, Component):
            project = self.instance.project
        elif "context" in kwargs and "project" in kwargs["context"]:
            project = kwargs["context"]["project"]

        if project is not None:
            self.fields["category"].queryset = project.category_set.all()

    def validate_enforced_checks(self, value):
        if not isinstance(value, list):
            msg = "Enforced checks has to be a list."
            raise serializers.ValidationError(msg)
        for item in value:
            if item not in CHECKS:
                msg = f"Unsupported enforced check: {item}"
                raise serializers.ValidationError(msg)
        return value

    def to_representation(self, instance):
        """Remove VCS properties if user has no permission for that."""
        result = super().to_representation(instance)
        if instance.linked_component_id is not None:
            linked_component = instance.linked_component
            for field in self.linked_repository_setting_fields:
                result[field] = getattr(linked_component, field)
        user = self.context["request"].user
        if not user.has_perm("vcs.view", instance):
            result["vcs"] = None
            result["repo"] = None
            result["branch"] = None
            result["filemask"] = None
            result["screenshot_filemask"] = None
            result["push"] = None
            result["git_export"] = None
            result["push_branch"] = None
            result["repoweb"] = None
            result["linked_component"] = None
        return result

    def to_internal_value(self, data):
        # Preprocess to inject params based on content
        # QueryDict.copy() deep-copies values, which breaks multipart uploads
        # backed by TemporaryUploadedFile on Python 3.13.
        data = copy(data)

        source_component = None
        if "from_component" in data and "docfile" not in data and "zipfile" not in data:
            source_component = resolve_component_reference_with_error(
                Component.objects.filter_access(self.context["request"].user),
                data["from_component"],
                "from_component",
            )
            self.populate_from_component_input_defaults(data, source_component)
        # Provide a reasonable default
        if "manage_units" not in data and data.get("template") and not self.partial:
            data["manage_units"] = "1"

        # File uploads indicate usage of a local repo
        if "docfile" in data or "zipfile" in data:
            data["repo"] = "local:"
            data["vcs"] = "local"
            data["branch"] = "main"

            # Provide a filemask so that it is not listed as an
            # error. The validation of docfile will fail later
            if "docfile" in data and "filemask" not in data:
                guess_filemask_from_doc(data)

        # DRF processing
        result = super().to_internal_value(data)

        # Handle source language attribute
        if "source_language" in result:
            language = result["source_language"]
            result["source_language"] = Language.objects.get(
                code=language if isinstance(language, str) else language["code"]
            )

        # Add missing project context
        if "project" in self._context:
            result["project"] = self._context["project"]
        elif self.instance:
            result["project"] = self.instance.project

        # Workaround for https://github.com/encode/django-rest-framework/issues/7489
        if "category" not in result and not self.partial:
            result["category"] = None

        if source_component is not None:
            result["from_component"] = source_component

        return result

    @staticmethod
    def get_linked_component_or_none(repo: str | None) -> Component | None:
        if repo is None:
            return None
        try:
            return Component.objects.get_linked(repo)
        except Component.DoesNotExist:
            return None

    def get_linked_repository_component(self, instance: Component) -> Component | None:
        return self.get_linked_component_or_none(instance.repo)

    def validate_linked_repository_setting_overrides(
        self, attrs, instance: Component
    ) -> None:
        linked_component = self.get_linked_repository_component(instance)
        if linked_component is None:
            return

        changed_linked_settings = {
            field
            for field in self.linked_repository_setting_fields
            if field in self.initial_data
            and attrs.get(field, getattr(instance, field))
            != getattr(linked_component, field)
        }
        requires_link_access = (
            self.instance is None
            or instance.repo != self.instance.repo
            or bool(changed_linked_settings)
        )
        if not requires_link_access:
            for field in self.linked_repository_setting_fields:
                if field in self.initial_data:
                    attrs.pop(field, None)
            return

        if not self.context["request"].user.has_perm(
            "component.edit", linked_component
        ):
            raise serializers.ValidationError(
                {
                    "repo": gettext_lazy(
                        "You do not have permission to access this component."
                    )
                }
            )

        if self.instance is None or not self.instance.is_repo_link:
            for field in self.linked_repository_setting_fields:
                if field in self.initial_data:
                    attrs.pop(field, None)
            return

        errors: dict[str, Any] = {}
        for field in self.linked_repository_setting_fields:
            if field not in self.initial_data:
                continue
            if field in changed_linked_settings:
                errors[field] = self.linked_repository_setting_error
            else:
                attrs.pop(field, None)

        if errors:
            raise serializers.ValidationError(errors)

    def populate_from_component_input_defaults(self, data, source_component: Component):
        defaults = {
            "filemask": source_component.filemask,
            "file_format": source_component.file_format,
        }
        if "repo" in data:
            defaults["vcs"] = source_component.vcs
        else:
            defaults["repo"] = "local:"
            defaults["vcs"] = "local"
        for field, value in defaults.items():
            if field not in data:
                data[field] = value

    def apply_from_component_defaults(self, attrs, source_component: Component):
        project = attrs.get("project") or self.context.get("project")

        for field in self.duplicated_component_fields:
            if field in attrs:
                continue
            if not should_copy_component_field(field, self.initial_data):
                continue
            if "repo" not in self.initial_data and field in {
                "vcs",
                "repo",
                "branch",
                "push",
                "push_branch",
            }:
                continue
            if "repo" in self.initial_data and field in {
                "branch",
                "push",
                "push_branch",
            }:
                continue
            value = getattr(source_component, field)
            if isinstance(value, list | dict):
                value = deepcopy(value)
            attrs[field] = value

        if (
            attrs.get("category") is None
            and "category" not in self.initial_data
            and project is not None
        ):
            attrs["category"] = (
                source_component.category
                if source_component.project_id == project.pk
                else None
            )

        return attrs

    def validate_from_component_overrides(self, attrs, source_component: Component):
        forbidden_fields = sorted(
            self.forbidden_from_component_override_fields.intersection(
                self.initial_data
            )
        )
        if forbidden_fields:
            raise serializers.ValidationError(
                dict.fromkeys(
                    forbidden_fields,
                    "This field can not be overridden when using from_component.",
                )
            )

        incompatible_fields = sorted(
            {"repo", "vcs", "branch", "push", "push_branch"}.intersection(
                self.initial_data
            )
        )
        if incompatible_fields:
            raise serializers.ValidationError(
                dict.fromkeys(
                    incompatible_fields,
                    "This field can not be used when using from_component.",
                )
            )

    @staticmethod
    def validate_local_from_component_instance(
        instance: Component, source_component: Component
    ) -> None:
        instance.clean_model_settings()
        validation_instance = copy(instance)
        validation_instance.linked_component = source_component
        validation_instance.clean_new_lang()

    def set_create_inheritance_defaults(
        self, attrs, *, preserve_existing: bool = False
    ):
        if self.instance:
            return
        apply_create_inheritance_defaults(
            attrs,
            getattr(self, "initial_data", {}),
            preserve_existing=preserve_existing,
        )

    def check_restricted_permission(self, attrs) -> None:
        if self.instance:
            if (
                "restricted" not in attrs
                or attrs["restricted"] == self.instance.restricted
            ):
                return
            component = self.instance
        else:
            restricted = attrs.get("restricted", False) or (
                "restricted" not in self.initial_data
                and settings.DEFAULT_RESTRICTED_COMPONENT
            )
            if not restricted:
                return
            attrs["restricted"] = True
            component = Component(**attrs)
        permission = self.context["request"].user.has_perm(
            "billing:component.permissions", component
        )
        if not permission:
            reason = (
                permission.reason
                if isinstance(permission, PermissionResult)
                else gettext_lazy(
                    "You do not have permission to change restricted access."
                )
            )
            raise serializers.ValidationError({"restricted": reason})

    def validate(self, attrs):
        # Handle non-component args
        disable_autoshare = attrs.pop("disable_autoshare", False)
        docfile = attrs.pop("docfile", None)
        zipfile = attrs.pop("zipfile", None)
        from_component = attrs.pop("from_component", None)

        # Restrict create fields on patching
        if self.instance and (
            docfile is not None or zipfile is not None or from_component is not None
        ):
            field = (
                "docfile"
                if docfile is not None
                else "zipfile"
                if zipfile is not None
                else "from_component"
            )
            raise serializers.ValidationError(
                {field: "This field is for creation only, use /file/ instead."}
            )

        source_component = None
        if from_component is not None:
            source_component = resolve_component_reference_with_error(
                Component.objects.filter_access(self.context["request"].user),
                from_component,
                "from_component",
            )
            if not self.context["request"].user.has_perm(
                "component.edit", source_component
            ):
                raise serializers.ValidationError(
                    {
                        "from_component": "You do not have permission to use this component."
                    }
                )
            if docfile is not None or zipfile is not None:
                raise serializers.ValidationError(
                    {
                        "from_component": "This field can not be combined with zipfile or docfile.",
                    }
                )
            self.validate_from_component_overrides(attrs, source_component)
            attrs = self.apply_from_component_defaults(attrs, source_component)
            if "repo" not in self.initial_data and not os.path.isdir(
                source_component.full_path
            ):
                raise serializers.ValidationError(
                    {
                        "from_component": (
                            "Source component repository is not available."
                        )
                    }
                )

        self.set_create_inheritance_defaults(
            attrs, preserve_existing=source_component is not None
        )
        self.check_restricted_permission(attrs)

        # Build new or patched Component instance with changed attributes
        if self.instance:
            instance = copy(self.instance)
            for key, value in attrs.items():
                setattr(instance, key, value)
        else:
            instance = Component(**attrs)

        self.validate_linked_repository_setting_overrides(attrs, instance)

        if docfile is not None or zipfile is not None:
            # Validate name/slug uniqueness, this has to be done prior docfile/zipfile
            # extracting
            instance.clean_unique_together()

            # Handle uploaded files
            if docfile is not None:
                fake = create_component_from_doc(attrs, docfile)
                instance.template = attrs["template"] = fake.template
                instance.new_base = attrs["new_base"] = fake.template
                instance.filemask = attrs["filemask"] = fake.filemask
            if zipfile is not None:
                try:
                    create_component_from_zip(attrs, zipfile)
                except (BadZipfile, OSError, RepositoryError) as error:
                    raise serializers.ValidationError(
                        {"zipfile": "Could not parse uploaded ZIP file."}
                    ) from error

        # Call model validation here, DRF does not do that
        if source_component is not None and "repo" not in self.initial_data:
            self.validate_local_from_component_instance(instance, source_component)
        else:
            instance.clean()

        if not self.instance and not disable_autoshare and source_component is None:
            repo = instance.suggest_repo_link()
            linked_component = self.get_linked_component_or_none(repo)
            if linked_component is not None and self.context["request"].user.has_perm(
                "component.edit", linked_component
            ):
                attrs["repo"] = instance.repo = repo
                attrs["branch"] = instance.branch = ""
        if source_component is not None:
            attrs["from_component"] = source_component
        return attrs

    def create(self, validated_data):
        source_component = validated_data.pop("from_component", None)
        if source_component is None:
            return super().create(validated_data)

        component = Component(**validated_data)
        component.prepare_seed_from_component(
            source_component.pk,
            copy_addons=True,
            seed_author=self.context["request"].user.get_author_name(),
        )
        component.save(force_insert=True)
        return component


class NotificationSerializer(serializers.ModelSerializer[Subscription]):
    project = ProjectSerializer(read_only=True)
    component = ComponentSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "notification",
            "id",
            "scope",
            "frequency",
            "project",
            "component",
        )


class TranslationSerializer(RemovableSerializer[Translation]):
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    share_url = AbsoluteURLField(source="get_share_url", read_only=True)
    translate_url = AbsoluteURLField(source="get_translate_url", read_only=True)
    component = ComponentSerializer(read_only=True)
    language = LanguageSerializer(read_only=True)
    is_template = serializers.BooleanField(read_only=True)
    is_source = serializers.BooleanField(read_only=True)
    total = serializers.IntegerField(source="stats.all", read_only=True)
    total_words = serializers.IntegerField(source="stats.all_words", read_only=True)
    translated = serializers.IntegerField(source="stats.translated", read_only=True)
    translated_words = serializers.IntegerField(
        source="stats.translated_words", read_only=True
    )
    translated_percent = serializers.FloatField(
        source="stats.translated_percent", read_only=True
    )
    fuzzy = serializers.IntegerField(source="stats.fuzzy", read_only=True)
    fuzzy_words = serializers.IntegerField(source="stats.fuzzy_words", read_only=True)
    fuzzy_percent = serializers.FloatField(source="stats.fuzzy_percent", read_only=True)
    failing_checks = serializers.IntegerField(source="stats.allchecks", read_only=True)
    failing_checks_words = serializers.IntegerField(
        source="stats.allchecks_words", read_only=True
    )
    failing_checks_percent = serializers.FloatField(
        source="stats.allchecks_percent", read_only=True
    )
    have_suggestion = serializers.IntegerField(
        source="stats.suggestions", read_only=True
    )
    have_comment = serializers.IntegerField(source="stats.comments", read_only=True)
    last_change = serializers.DateTimeField(source="stats.last_changed", read_only=True)
    last_author = serializers.CharField(source="get_last_author", read_only=True)
    repository_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-repository",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )
    statistics_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-statistics",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )
    file_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-file",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )
    changes_list_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-changes",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )
    units_list_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-units",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )
    announcements_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-announcements",
        lookup_field=("component__project__slug", "component__slug", "language__code"),
    )

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    class Meta:
        model = Translation
        fields: tuple[str, ...] = (
            "language",
            "component",
            "language_code",
            "id",
            "filename",
            "revision",
            "web_url",
            "share_url",
            "translate_url",
            "url",
            "is_template",
            "is_source",
            "total",
            "total_words",
            "translated",
            "translated_words",
            "translated_percent",
            "fuzzy",
            "fuzzy_words",
            "fuzzy_percent",
            "failing_checks",
            "failing_checks_words",
            "failing_checks_percent",
            "have_suggestion",
            "have_comment",
            "last_change",
            "last_author",
            "repository_url",
            "file_url",
            "statistics_url",
            "changes_list_url",
            "units_list_url",
            "announcements_url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {
                "view_name": "api:translation-detail",
                "lookup_field": (
                    "component__project__slug",
                    "component__slug",
                    "language__code",
                ),
            }
        }


class ComponentTranslationSerializer(TranslationSerializer):
    class Meta(TranslationSerializer.Meta):
        fields = tuple(
            field for field in TranslationSerializer.Meta.fields if field != "component"
        )


class ReadOnlySerializer(serializers.Serializer):
    def update(self, instance, validated_data) -> None:
        return None

    def create(self, validated_data) -> None:
        return None


class LockSerializer(serializers.ModelSerializer[Component]):
    class Meta:
        model = Component
        fields = ("locked",)


class ProjectLockSerializer(serializers.ModelSerializer[Project]):
    class Meta:
        model = Project
        fields = ("locked",)


class LockRequestSerializer(ReadOnlySerializer):
    lock = serializers.BooleanField()


class BooleanResultSerializer(ReadOnlySerializer):
    result = serializers.BooleanField()


class RepositoryOperationSerializer(BooleanResultSerializer):
    detail = serializers.CharField(required=False)


class UploadResultSerializer(BooleanResultSerializer):
    not_found = serializers.IntegerField()
    skipped = serializers.IntegerField()
    accepted = serializers.IntegerField()
    total = serializers.IntegerField()
    count = serializers.IntegerField()


class TranslationCreateSerializer(ReadOnlySerializer):
    language_code = serializers.CharField()
    from_component = ComponentReferenceListField(required=False)

    def validate(self, attrs):
        component = self.context["component"]
        request = self.context["request"]
        source_components = []
        source_queryset = Component.objects.filter(
            models.Q(project_id=component.project_id)
            | models.Q(project__contribute_shared_tm=True)
        )
        for reference in attrs.get("from_component", []):
            source_component = resolve_component_reference_with_error(
                source_queryset,
                reference,
                "from_component",
            )
            if not request.user.has_perm("component.edit", source_component) and (
                source_component.project_id == component.project_id
                or not source_component.project.contribute_shared_tm
            ):
                raise serializers.ValidationError(
                    {
                        "from_component": "You do not have permission to use this component."
                    }
                )
            if source_component.source_language_id != component.source_language_id:
                raise serializers.ValidationError(
                    {
                        "from_component": (
                            "Source component needs to have same source language as target one."
                        )
                    }
                )
            if (
                source_component.project_id != component.project_id
                and not source_component.project.contribute_shared_tm
            ):
                raise serializers.ValidationError(
                    {
                        "from_component": (
                            "Project has disabled contribution to shared translation memory."
                        )
                    }
                )
            source_components.append(source_component)

        if source_components:
            eligible_component_ids = set(
                Translation.objects.filter(
                    component_id__in=[
                        source_component.pk for source_component in source_components
                    ],
                    language__code=attrs["language_code"],
                ).values_list("component_id", flat=True)
            )
            source_components = [
                source_component
                for source_component in source_components
                if source_component.pk in eligible_component_ids
            ]
            if not source_components:
                raise serializers.ValidationError(
                    {
                        "from_component": (
                            "None of the referenced components contain the requested language."
                        )
                    }
                )

        attrs["from_component"] = source_components
        return attrs


class UploadRequestSerializer(ReadOnlySerializer):
    file = serializers.FileField(validators=[validate_translation_upload_size])
    author_email = serializers.EmailField(required=False)
    author_name = serializers.CharField(max_length=200, required=False)
    method = serializers.ChoiceField(
        choices=(
            "translate",
            "approve",
            "suggest",
            "fuzzy",
            "replace",
            "source",
            "add",
        ),
        required=False,
        default="translate",
    )
    fuzzy = serializers.ChoiceField(
        choices=("", "process", "approve"), required=False, default=""
    )
    conflicts = serializers.ChoiceField(
        choices=("", "ignore", "replace-translated", "replace-approved"),
        required=False,
        default="",
    )

    def validate_conflicts(self, value):
        # These are handled same
        if value == "ignore":
            return ""
        return value

    def check_perms(self, user: User, obj) -> None:
        data = self.validated_data
        if data["conflicts"] and not user.has_perm("upload.overwrite", obj):
            raise serializers.ValidationError(
                {"conflicts": "You can not overwrite existing translations."}
            )
        if data["conflicts"] == "replace-approved" and not (
            denied := user.has_perm("unit.review", obj)
        ):
            raise serializers.ValidationError({"conflicts": denied.reason})

        if not (denied := check_upload_method_permissions(user, obj, data["method"])):
            hint = "Check your permissions or use different translation object."
            if isinstance(denied, PermissionResult):
                hint = denied.reason
            raise serializers.ValidationError(
                {"method": f"This method is not available here. {hint}"}
            )


class RepoOperations(TextChoices):
    COMMIT = "commit", gettext_lazy("Commit")
    PULL = "pull", gettext_lazy("Update")
    PULL_REBASE = "pull-rebase", gettext_lazy("Update with rebase")
    PULL_MERGE = "pull-merge", gettext_lazy("Update with merge")
    PULL_MERGE_NOFF = (
        "pull-merge-noff",
        gettext_lazy("Update with merge without fast-forward"),
    )
    PUSH = "push", gettext_lazy("Push")
    RESET = "reset", gettext_lazy("Reset all changes in the Weblate repository")
    RESET_KEEP = (
        "reset-keep",
        gettext_lazy("Reset the Weblate repository and reapply translations"),
    )
    CLEANUP = (
        "cleanup",
        gettext_lazy("Cleanup all untracked files in the Weblate repository"),
    )
    FILE_SYNC = (
        "file-sync",
        gettext_lazy("Force writing all translations to the Weblate repository"),
    )
    FILE_SCAN = (
        "file-scan",
        gettext_lazy("Rescan all translation files in the Weblate repository"),
    )


class ComponentLinkRequestSerializer(ReadOnlySerializer):
    project_slug = serializers.SlugField(required=True)
    category_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context["request"]
        component = self.context["component"]

        project_slug = attrs["project_slug"]
        try:
            project = (
                request.user.managed_projects.filter(
                    pk__in=request.user.allowed_projects
                )
                .exclude(pk=component.project_id)
                .get(slug=project_slug)
            )
        except Project.DoesNotExist as error:
            msg = f"No project slug {project_slug!r} found!"
            raise serializers.ValidationError({"project_slug": msg}) from error
        if not request.user.has_perm("project.edit", project):
            msg = f"No project slug {project_slug!r} found!"
            raise serializers.ValidationError({"project_slug": msg})
        attrs["project"] = project

        category_id = attrs.get("category_id")
        if category_id is not None:
            try:
                category = project.category_set.get(pk=category_id)
            except Category.DoesNotExist as error:
                msg = "Category not found."
                raise serializers.ValidationError({"category_id": msg}) from error
            attrs["category"] = category
        else:
            attrs["category"] = None

        return attrs


class RepoRequestSerializer(ReadOnlySerializer):
    operation = serializers.ChoiceField(
        choices=RepoOperations.choices,
    )


class CommitInfoSerializer(ReadOnlySerializer):
    """Detailed information about a Git commit."""

    revision = serializers.CharField(
        required=False, allow_null=True, help_text="Full commit hash."
    )
    shortrevision = serializers.CharField(
        required=False, allow_null=True, help_text="Abbreviated commit hash."
    )
    author = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Commit author with email (e.g., 'Name <email@example.com>').",
    )
    author_name = serializers.CharField(
        required=False, allow_null=True, help_text="Author name."
    )
    author_email = serializers.CharField(
        required=False, allow_null=True, help_text="Author email address."
    )
    authordate = serializers.DateTimeField(
        required=False, allow_null=True, help_text="Date when the commit was authored."
    )
    commit = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Committer with email (e.g., 'Name <email@example.com>').",
    )
    commit_name = serializers.CharField(
        required=False, allow_null=True, help_text="Committer name."
    )
    commit_email = serializers.CharField(
        required=False, allow_null=True, help_text="Committer email address."
    )
    commitdate = serializers.DateTimeField(
        required=False, allow_null=True, help_text="Date when the commit was committed."
    )
    message = serializers.CharField(
        required=False, allow_null=True, help_text="Full commit message."
    )
    summary = serializers.CharField(
        required=False, allow_null=True, help_text="First line of the commit message."
    )


class PendingUnitsSerializer(ReadOnlySerializer):
    """Detailed breakdown of pending translation units."""

    total = serializers.IntegerField(
        help_text="Total number of translation units with pending changes."
    )
    errors_skipped = serializers.IntegerField(
        help_text="Number of units skipped due to commit errors (blocked by retry policy)."
    )
    commit_policy_skipped = serializers.IntegerField(
        help_text="Number of units skipped by the commit policy (e.g., needs editing, not approved)."
    )
    eligible_for_commit = serializers.IntegerField(
        help_text="Number of units eligible to be committed based on the current policy."
    )


class RepositorySerializer(ReadOnlySerializer):
    """Serializer for repository status information."""

    needs_commit = serializers.BooleanField(
        help_text="Whether the repository has pending changes that need to be committed."
    )
    needs_merge = serializers.BooleanField(
        help_text="Whether the repository needs to pull changes from upstream."
    )
    needs_push = serializers.BooleanField(
        help_text="Whether the repository has commits that need to be pushed."
    )
    url = serializers.CharField(help_text="URL to the repository API endpoint.")
    remote_commit = CommitInfoSerializer(
        required=False,
        allow_null=True,
        help_text="Detailed information about the last commit in the remote repository (component/translation only).",
    )
    weblate_commit = CommitInfoSerializer(
        required=False,
        allow_null=True,
        help_text="Detailed information about the last commit in the Weblate repository (component/translation only).",
    )
    status = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Full repository status text (component/translation only).",
    )
    merge_failure = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Details about merge failure if any (component/translation only).",
    )
    pending_units = PendingUnitsSerializer(
        required=False,
        allow_null=True,
        help_text="Detailed breakdown of translation units with pending changes.",
    )
    outgoing_commits = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Number of commits ready to be pushed to the remote repository (component/translation only).",
    )
    missing_commits = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Number of commits in the remote repository that need to be pulled (component/translation only).",
    )


class StatisticsSerializer(ReadOnlySerializer):
    total = serializers.IntegerField()
    total_words = serializers.IntegerField()
    total_chars = serializers.IntegerField()
    last_change = serializers.DateTimeField(allow_null=True)
    recent_changes = serializers.IntegerField()
    translated = serializers.IntegerField()
    translated_words = serializers.IntegerField()
    translated_percent = serializers.FloatField()
    translated_words_percent = serializers.FloatField()
    translated_chars = serializers.IntegerField()
    translated_chars_percent = serializers.FloatField()
    fuzzy = serializers.IntegerField()
    fuzzy_percent = serializers.FloatField()
    fuzzy_words = serializers.IntegerField()
    fuzzy_words_percent = serializers.FloatField()
    fuzzy_chars = serializers.IntegerField()
    fuzzy_chars_percent = serializers.FloatField()
    failing = serializers.IntegerField()
    failing_percent = serializers.FloatField()
    approved = serializers.IntegerField()
    approved_percent = serializers.FloatField()
    approved_words = serializers.IntegerField()
    approved_words_percent = serializers.FloatField()
    approved_chars = serializers.IntegerField()
    approved_chars_percent = serializers.FloatField()
    readonly = serializers.IntegerField()
    readonly_percent = serializers.FloatField()
    readonly_words = serializers.IntegerField()
    readonly_words_percent = serializers.FloatField()
    readonly_chars = serializers.IntegerField()
    readonly_chars_percent = serializers.FloatField()
    suggestions = serializers.IntegerField()
    comments = serializers.IntegerField()
    code = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    url = serializers.URLField(required=False)
    translate_url = serializers.URLField(required=False)

    def to_representation(self, instance):
        stats = instance.stats
        result = {
            "total": stats.all,
            "total_words": stats.all_words,
            "total_chars": stats.all_chars,
            "last_change": stats.last_changed,
            "recent_changes": stats.recent_changes,
            "translated": stats.translated,
            "translated_words": stats.translated_words,
            "translated_percent": stats.translated_percent,
            "translated_words_percent": stats.translated_words_percent,
            "translated_chars": stats.translated_chars,
            "translated_chars_percent": stats.translated_chars_percent,
            "fuzzy": stats.fuzzy,
            "fuzzy_percent": stats.fuzzy_percent,
            "fuzzy_words": stats.fuzzy_words,
            "fuzzy_words_percent": stats.fuzzy_words_percent,
            "fuzzy_chars": stats.fuzzy_chars,
            "fuzzy_chars_percent": stats.fuzzy_chars_percent,
            "failing": stats.allchecks,
            "failing_percent": stats.allchecks_percent,
            "approved": stats.approved,
            "approved_percent": stats.approved_percent,
            "approved_words": stats.approved_words,
            "approved_words_percent": stats.approved_words_percent,
            "approved_chars": stats.approved_chars,
            "approved_chars_percent": stats.approved_chars_percent,
            "readonly": stats.readonly,
            "readonly_percent": stats.readonly_percent,
            "readonly_words": stats.readonly_words,
            "readonly_words_percent": stats.readonly_words_percent,
            "readonly_chars": stats.readonly_chars,
            "readonly_chars_percent": stats.readonly_chars_percent,
            "suggestions": stats.suggestions,
            "comments": stats.comments,
        }
        if hasattr(instance, "language"):
            result["code"] = instance.language.code
            result["name"] = instance.language.name
        elif hasattr(instance, "name"):
            result["name"] = instance.name
        if hasattr(instance, "get_absolute_url"):
            result["url"] = get_site_url(instance.get_absolute_url())
        if hasattr(instance, "get_translate_url"):
            result["translate_url"] = get_site_url(instance.get_translate_url())
        return result


class UserStatisticsSerializer(ReadOnlySerializer):
    translated = serializers.IntegerField()
    suggested = serializers.IntegerField()
    uploaded = serializers.IntegerField()
    commented = serializers.IntegerField()
    languages = serializers.IntegerField()

    def to_representation(self, instance):
        profile = instance.profile
        return {
            "translated": profile.translated,
            "suggested": profile.suggested,
            "uploaded": profile.uploaded,
            "commented": profile.commented,
            "languages": profile.languages.count(),
        }


class PluralField(serializers.ListField):
    def __init__(
        self,
        child_allow_blank: bool = False,
        child_error_messages: dict | None = None,
        **kwargs,
    ) -> None:
        child_kwargs: dict[str, Any] = {
            "trim_whitespace": False,
            "allow_blank": child_allow_blank,
        }
        if child_error_messages:
            child_kwargs["error_messages"] = child_error_messages

        kwargs["child"] = serializers.CharField(**child_kwargs)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return getattr(instance, f"get_{self.field_name}_plurals")()


class SuggestionSerializer(serializers.Serializer[Suggestion]):
    add_result: SuggestionAddResult | None = None

    id = serializers.IntegerField(read_only=True)
    unit = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="api:unit-detail"
    )
    target = PluralField(
        allow_empty=False,
        child_error_messages={
            "blank": gettext_lazy("Please provide a suggestion"),
        },
    )

    user = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="api:user-detail",
        lookup_field="username",
        allow_null=True,
    )
    timestamp = serializers.DateTimeField(read_only=True)
    votes = serializers.IntegerField(source="get_num_votes", read_only=True)

    class Meta:
        model = Suggestion
        fields = ("id", "unit", "target", "user", "timestamp", "votes")

    def validate_target(self, value: list[str]) -> list[str]:
        unit = self.context.get("unit")
        if unit is None:
            return value

        max_length = get_translation_text_max_length(unit)
        for text in value:
            if len(text) > max_length:
                msg = gettext_lazy("Translation text too long!")
                raise serializers.ValidationError(msg)

        if unit.translation.component.is_multivalue:
            return value

        target_copy = value.copy()
        if target_copy != unit.adjust_plurals(value.copy()):
            msg = gettext_lazy("Number of plurals does not match")
            raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data):
        request = self.context["request"]
        unit = self.context["unit"]
        target = validated_data["target"]
        try:
            suggestion, result = Suggestion.objects.add(
                unit,
                target,
                request,
                request.user.has_perm("suggestion.vote", unit),
                raise_exception=True,
            )
        except SuggestionSimilarToTranslationError as error:
            msg = gettext_lazy("Your suggestion is similar to the current translation!")
            raise serializers.ValidationError({"target": msg}) from error
        except SuggestionTooLongError as error:
            msg = gettext_lazy("Translation text too long!")
            raise serializers.ValidationError({"target": msg}) from error
        self.add_result = result
        if result == SuggestionAddResult.DUPLICATE:
            msg = gettext_lazy("Your suggestion already exists!")
            raise serializers.ValidationError({"target": msg})
        return suggestion


class SuggestionDeleteRequestSerializer(ReadOnlySerializer):
    rejection_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=SUGGESTION_REJECTION_REASON_LENGTH
    )
    is_spam = serializers.BooleanField(required=False, default=False)


class SuggestionAcceptRequestSerializer(ReadOnlySerializer):
    approve = serializers.BooleanField(required=False, default=False)


class SuggestionVoteRequestSerializer(ReadOnlySerializer):
    value = serializers.ChoiceField(choices=[(1, "Positive"), (-1, "Negative")])


class SuggestionVoteResultSerializer(ReadOnlySerializer):
    result = serializers.ChoiceField(choices=["voted", "accepted"])
    suggestion = SuggestionSerializer(allow_null=True)


class MemorySerializer(serializers.ModelSerializer[Memory]):
    visible_project_ids_loaded = False
    visible_project_ids: set[int] | None = None

    project = serializers.SerializerMethodField()
    from_file = serializers.SerializerMethodField()
    shared = serializers.SerializerMethodField()

    class Meta:
        model = Memory
        fields = (
            "id",
            "source",
            "target",
            "source_language",
            "target_language",
            "origin",
            "project",
            "from_file",
            "shared",
        )

    def get_project(self, obj: Memory) -> int | None:
        project_scopes = [
            scope
            for scope in self.get_scopes(obj)
            if scope.scope
            in {
                MemoryScope.SCOPE_PROJECT,
                MemoryScope.SCOPE_PROJECT_FILE,
            }
            and scope.project_id is not None
        ]
        request = self.context.get("request")
        if request is not None:
            project_slug = request.query_params.get("project")
            visible_project_ids = self.get_visible_project_ids()
            if project_slug:
                for scope in project_scopes:
                    if (
                        scope.project is not None
                        and scope.project.slug == project_slug
                        and (
                            visible_project_ids is None
                            or scope.project_id in visible_project_ids
                        )
                    ):
                        return scope.project_id
                return None
            if visible_project_ids is not None:
                project_scopes = [
                    scope
                    for scope in project_scopes
                    if scope.project_id in visible_project_ids
                ]

        project_ids = {scope.project_id for scope in project_scopes}
        if len(project_ids) == 1:
            return project_scopes[0].project_id
        return None

    def get_visible_project_ids(self) -> set[int] | None:
        if not self.visible_project_ids_loaded:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if (
                user is None
                or not user.is_authenticated
                or user.is_superuser
                or user.has_perm("memory.manage")
            ):
                self.visible_project_ids = None
            else:
                self.visible_project_ids = set(
                    user.allowed_projects.values_list("id", flat=True)
                )
            self.visible_project_ids_loaded = True
        return self.visible_project_ids

    def get_from_file(self, obj: Memory) -> bool:
        return bool(
            any(
                scope.scope
                in {
                    MemoryScope.SCOPE_GLOBAL_FILE,
                    MemoryScope.SCOPE_PROJECT_FILE,
                    MemoryScope.SCOPE_USER_FILE,
                }
                for scope in self.get_scopes(obj)
            )
        )

    def get_shared(self, obj: Memory) -> bool:
        return any(
            scope.scope == MemoryScope.SCOPE_SHARED for scope in self.get_scopes(obj)
        )

    def get_scopes(self, obj: Memory) -> list[MemoryScope]:
        return obj.get_scope_list()


class MemoryLookupRequestSerializer(serializers.Serializer):
    strings = serializers.ListField(
        child=serializers.CharField(
            allow_blank=False,
            trim_whitespace=False,
            max_length=2000,
        ),
        allow_empty=False,
        max_length=100,
    )


class MemoryLookupQuerySerializer(serializers.Serializer):
    exact = serializers.BooleanField(required=False, default=False)


class MemoryLookupMatchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    source = serializers.CharField()
    target = serializers.CharField()
    origin = serializers.CharField()
    exact = serializers.BooleanField()
    quality = serializers.IntegerField()


class MemoryLookupResultSerializer(serializers.Serializer):
    query = serializers.CharField()
    match = MemoryLookupMatchSerializer(allow_null=True)


class LabelSerializer(serializers.ModelSerializer[Label]):
    class Meta:
        model = Label
        fields = ("id", "name", "description", "color")
        read_only_fields = ("project",)


class AnnouncementSerializer(serializers.ModelSerializer[Announcement]):
    class Meta:
        model = Announcement
        fields = ("id", "message", "severity", "expiry", "notify")
        read_only_fields = ("id",)


@extend_schema_field(LabelSerializer)
class UnitLabelsSerializer(serializers.RelatedField, LabelSerializer):
    def get_queryset(self):
        """
        List of available labels for an unit.

        The queryset argument is only ever required for writable relationship field,
        in which case it is used for performing the model instance lookup, that maps
        from the primitive user input, into a model instance.
        """
        unit = self.parent.parent.instance
        if unit is None:
            # HTTP 404 Not Found on HTML page still shows the form
            # but it has no unit attached
            return Label.objects.none()
        project = unit.translation.component.project
        return project.label_set.all()

    def to_internal_value(self, data):
        try:
            pk = int(data)
        except ValueError as err:
            msg = "Invalid label ID."
            raise serializers.ValidationError(msg) from err
        try:
            label = self.get_queryset().get(id=pk)
        except Label.DoesNotExist as err:
            msg = "Label with this ID was not found in this project."
            raise serializers.ValidationError(msg) from err
        return label


@extend_schema_field({"type": "integer"})
class UnitFlatLabelsSerializer(UnitLabelsSerializer):
    def to_representation(self, instance):
        return instance.id


class UnitSerializer(serializers.ModelSerializer[Unit]):
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    translation = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-detail",
        lookup_field=(
            "translation__component__project__slug",
            "translation__component__slug",
            "translation__language__code",
        ),
        strip_parts=1,
    )
    language_code = serializers.CharField(
        source="translation.language.code", read_only=True
    )
    source_unit: serializers.HyperlinkedRelatedField[Unit] = (
        serializers.HyperlinkedRelatedField(read_only=True, view_name="api:unit-detail")
    )
    source = PluralField()
    target = PluralField()
    timestamp = serializers.DateTimeField(read_only=True)
    last_updated = serializers.DateTimeField(read_only=True)
    pending = serializers.BooleanField(source="has_pending_changes", read_only=True)
    labels = UnitLabelsSerializer(many=True)

    class Meta:
        model = Unit
        fields = (
            "translation",
            "language_code",
            "source",
            "previous_source",
            "target",
            "id_hash",
            "content_hash",
            "location",
            "context",
            "note",
            "flags",
            "labels",
            "state",
            "fuzzy",
            "translated",
            "approved",
            "position",
            "has_suggestion",
            "has_comment",
            "has_failing_check",
            "num_words",
            "source_unit",
            "priority",
            "id",
            "web_url",
            "url",
            "explanation",
            "extra_flags",
            "pending",
            "timestamp",
            "last_updated",
            "automatically_translated",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:unit-detail"},
        }


class UnitWriteSerializer(serializers.ModelSerializer[Unit]):
    """Serializer for updating source unit."""

    target = PluralField()
    labels = UnitFlatLabelsSerializer(many=True)

    class Meta:
        model = Unit
        fields = (
            "target",
            "state",
            "explanation",
            "extra_flags",
            "labels",
        )

    def to_internal_value(self, data):
        # Allow blank target for untranslated strings
        if isinstance(data, dict) and data.get("state") in {0, "0"}:
            self.fields["target"].child.allow_blank = True
        return super().to_internal_value(data)


class NewUnitSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=NEW_UNIT_STATE_CHOICES,
        required=False,
    )

    def as_kwargs(self, data: dict | None = None) -> NewUnitParams:
        raise NotImplementedError

    def validate(self, attrs):
        try:
            data = self.as_kwargs(attrs)
        except KeyError:
            # Probably some fields validation has failed
            return attrs
        self._context["translation"].validate_new_unit_data(**data)
        return attrs


class MonolingualUnitSerializer(NewUnitSerializer):
    key = serializers.CharField()
    value = PluralField()

    def as_kwargs(self, data: dict | None = None) -> NewUnitParams:
        if data is None:
            data = self.validated_data
        return NewUnitParams(
            context=data["key"],
            source=data["value"],
            target=None,
            state=data.get("state", None),
        )


class BilingualUnitSerializer(NewUnitSerializer):
    context = serializers.CharField(required=False)
    source = PluralField()
    target = PluralField()

    def as_kwargs(self, data: dict | None = None) -> NewUnitParams:
        if data is None:
            data = self.validated_data
        return NewUnitParams(
            context=data.get("context", ""),
            source=data["source"],
            target=data.get("target", ""),
            state=data.get("state", None),
        )


class BilingualSourceUnitSerializer(BilingualUnitSerializer):
    target = PluralField(required=False, child_allow_blank=True)


class CategorySerializer(RemovableSerializer[Category]):
    project = serializers.HyperlinkedRelatedField(
        view_name="api:project-detail",
        lookup_field="slug",
        queryset=Project.objects.none(),
        required=True,
    )
    category = serializers.HyperlinkedRelatedField(
        view_name="api:category-detail",
        queryset=Category.objects.none(),
        required=False,
        allow_null=True,
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:category-statistics",
        lookup_field="pk",
    )
    announcements_url = serializers.HyperlinkedIdentityField(
        view_name="api:category-announcements",
        lookup_field="pk",
    )
    reports_url = serializers.HyperlinkedIdentityField(
        view_name="api:category-reports", lookup_field="pk"
    )
    effective_license = serializers.SerializerMethodField()
    effective_agreement = serializers.SerializerMethodField()
    effective_new_lang = serializers.SerializerMethodField()
    effective_language_code_style = serializers.SerializerMethodField()
    effective_secondary_language = serializers.SerializerMethodField()
    effective_commit_message = serializers.SerializerMethodField()
    effective_add_message = serializers.SerializerMethodField()
    effective_delete_message = serializers.SerializerMethodField()
    effective_merge_message = serializers.SerializerMethodField()
    effective_addon_message = serializers.SerializerMethodField()
    effective_pull_message = serializers.SerializerMethodField()
    effective_check_flags = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "project",
            "category",
            "url",
            "statistics_url",
            "announcements_url",
            "reports_url",
            "check_flags",
            "effective_check_flags",
            "license",
            "inherit_license",
            "effective_license",
            "agreement",
            "inherit_agreement",
            "effective_agreement",
            "new_lang",
            "inherit_new_lang",
            "effective_new_lang",
            "language_code_style",
            "inherit_language_code_style",
            "effective_language_code_style",
            "secondary_language",
            "inherit_secondary_language",
            "effective_secondary_language",
            "commit_message",
            "inherit_commit_message",
            "effective_commit_message",
            "add_message",
            "inherit_add_message",
            "effective_add_message",
            "delete_message",
            "inherit_delete_message",
            "effective_delete_message",
            "merge_message",
            "inherit_merge_message",
            "effective_merge_message",
            "addon_message",
            "inherit_addon_message",
            "effective_addon_message",
            "pull_message",
            "inherit_pull_message",
            "effective_pull_message",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:category-detail"},
        }

    def get_effective_license(self, obj: Category) -> str:
        return obj.get_effective_setting("license")

    def get_effective_agreement(self, obj: Category) -> str:
        return obj.get_effective_setting("agreement")

    def get_effective_new_lang(self, obj: Category) -> str:
        return obj.get_effective_setting("new_lang")

    def get_effective_language_code_style(self, obj: Category) -> str:
        return obj.get_effective_setting("language_code_style")

    def get_effective_secondary_language(self, obj: Category) -> int | None:
        language = obj.get_effective_setting("secondary_language")
        return language.pk if language else None

    def get_effective_commit_message(self, obj: Category) -> str:
        return obj.get_effective_setting("commit_message")

    def get_effective_add_message(self, obj: Category) -> str:
        return obj.get_effective_setting("add_message")

    def get_effective_delete_message(self, obj: Category) -> str:
        return obj.get_effective_setting("delete_message")

    def get_effective_merge_message(self, obj: Category) -> str:
        return obj.get_effective_setting("merge_message")

    def get_effective_addon_message(self, obj: Category) -> str:
        return obj.get_effective_setting("addon_message")

    def get_effective_pull_message(self, obj: Category) -> str:
        return obj.get_effective_setting("pull_message")

    def get_effective_check_flags(self, obj: Category) -> str:
        return obj.effective_check_flags.format()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None or getattr(
            self.context.get("view"), "swagger_fake_view", False
        ):
            return
        user = request.user
        self.fields["project"].queryset = user.managed_projects
        self.fields["category"].queryset = Category.objects.filter(
            project__in=user.managed_projects
        )

    def validate(self, attrs):
        # Call model validation here, DRF does not do that
        if self.instance:
            instance = copy(self.instance)
            for key, value in attrs.items():
                setattr(instance, key, value)
        else:
            instance = Category(**attrs)
        instance.clean()
        return attrs

    def create(self, validated_data):
        initial_data = getattr(self, "initial_data", {})
        for field in INHERITABLE_COMPONENT_SETTINGS:
            inherit_field = f"inherit_{field}"
            if inherit_field in initial_data:
                continue
            validated_data[inherit_field] = field not in initial_data
        return super().create(validated_data)

    def to_internal_value(self, data):
        result = super().to_internal_value(data)

        # Add missing project context
        if "project" in self._context:
            result["project"] = self._context["project"]
        elif self.instance:
            result["project"] = self.instance.project

        # Workaround for https://github.com/encode/django-rest-framework/issues/7489
        if "category" not in result and not self.partial:
            result["category"] = None
        return result


class ScreenshotSerializer(RemovableSerializer[Screenshot]):
    translation = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-detail",
        lookup_field=(
            "translation__component__project__slug",
            "translation__component__slug",
            "translation__language__code",
        ),
        strip_parts=1,
    )
    file_url: serializers.HyperlinkedRelatedField[Screenshot] = (
        serializers.HyperlinkedRelatedField(
            read_only=True, source="pk", view_name="api:screenshot-file"
        )
    )
    units: serializers.HyperlinkedRelatedField[Unit] = (
        serializers.HyperlinkedRelatedField(
            many=True, read_only=True, view_name="api:unit-detail"
        )
    )

    class Meta:
        model = Screenshot
        fields = (
            "id",
            "name",
            "repository_filename",
            "translation",
            "file_url",
            "units",
            "url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:screenshot-detail"}
        }


class ScreenshotCreateSerializer(ScreenshotSerializer):
    class Meta:
        model = Screenshot
        fields = (
            "name",
            "repository_filename",
            "translation",
            "file_url",
            "units",
            "url",
            "image",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:screenshot-detail"}
        }


class ScreenshotFileSerializer(serializers.ModelSerializer[Screenshot]):
    image = serializers.ImageField(validators=[Screenshot.validate_image_file])

    class Meta:
        model = Screenshot
        fields = ("image",)
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:screenshot-file"}
        }


class AlertSerializer(serializers.ModelSerializer[Alert]):
    category = serializers.ChoiceField(
        choices=("addons", "community", "configuration", "files", "vcs"),
        read_only=True,
    )
    dismissed_by: serializers.HyperlinkedRelatedField = (
        serializers.HyperlinkedRelatedField(
            read_only=True,
            allow_null=True,
            view_name="api:user-detail",
            lookup_field="username",
        )
    )

    class Meta:
        model = Alert
        fields = (
            "name",
            "timestamp",
            "updated",
            "severity",
            "details",
            "category",
            "dismissed_at",
            "dismissed_by",
            "dismissal_reason",
        )
        read_only_fields = fields


class ChangeSerializer(RemovableSerializer[Change]):
    action_name = serializers.CharField(source="get_action_display", read_only=True)
    component = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("component__project__slug", "component__slug"),
        strip_parts=1,
    )
    translation = MultiFieldHyperlinkedIdentityField(
        view_name="api:translation-detail",
        lookup_field=(
            "translation__component__project__slug",
            "translation__component__slug",
            "translation__language__code",
        ),
        strip_parts=1,
    )
    unit: serializers.HyperlinkedRelatedField[Unit] = (
        serializers.HyperlinkedRelatedField(read_only=True, view_name="api:unit-detail")
    )
    user: serializers.HyperlinkedRelatedField[User] = (
        serializers.HyperlinkedRelatedField(
            read_only=True, view_name="api:user-detail", lookup_field="username"
        )
    )
    author: serializers.HyperlinkedRelatedField[User] = (
        serializers.HyperlinkedRelatedField(
            read_only=True, view_name="api:user-detail", lookup_field="username"
        )
    )
    alert = serializers.SerializerMethodField()

    def can_view_alert_details(self) -> bool:
        request = self.context.get("request")
        return request is not None and bool(request.user.is_authenticated)

    @extend_schema_field(AlertSerializer(allow_null=True))
    def get_alert(self, change: Change) -> dict[str, Any] | None:
        serializer = AlertSerializer(context=self.context)
        if change.alert_id is not None:
            data = dict(AlertSerializer(change.alert, context=self.context).data)
        elif change.action == ActionEvents.ALERT_DISMISSED and isinstance(
            change.details.get("alert_snapshot"), dict
        ):
            data = {"name": change.details.get("alert", "")}
        else:
            return None

        if change.action == ActionEvents.ALERT_DISMISSED:
            snapshot = change.details.get("alert_snapshot")
            if isinstance(snapshot, dict):
                for field in (
                    "timestamp",
                    "updated",
                    "severity",
                    "details",
                    "category",
                ):
                    if field in snapshot:
                        data[field] = snapshot[field]
            data["dismissed_at"] = serializer.fields["dismissed_at"].to_representation(
                change.timestamp
            )
            data["dismissed_by"] = (
                serializer.fields["dismissed_by"].to_representation(change.user)
                if change.user is not None
                else None
            )
            data["dismissal_reason"] = change.details.get("reason", "")
        if not self.can_view_alert_details():
            data["details"] = {}
            data["dismissal_reason"] = ""
        return data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.can_view_alert_details():
            return data
        details = data.get("details")
        if isinstance(details, dict):
            details = deepcopy(details)
            data["details"] = details
            if instance.action == ActionEvents.ALERT_DISMISSED:
                details.pop("reason", None)
            snapshot = details.get("alert_snapshot")
            if isinstance(snapshot, dict):
                snapshot["details"] = {}
        return data

    class Meta:
        model = Change
        fields = (
            "unit",
            "component",
            "translation",
            "user",
            "author",
            "alert",
            "timestamp",
            "action",
            "target",
            "old",
            "details",
            "id",
            "action_name",
            "url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:change-detail"}
        }


class AutoComponentListSerializer(serializers.ModelSerializer[AutoComponentList]):
    class Meta:
        model = AutoComponentList
        fields = (
            "project_match",
            "component_match",
        )


class ComponentListSerializer(serializers.ModelSerializer[ComponentList]):
    components = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("project__slug", "slug"),
        many=True,
        read_only=True,
    )
    auto_assign = AutoComponentListSerializer(
        many=True, source="autocomponentlist_set", read_only=True
    )

    class Meta:
        model = ComponentList
        fields = (
            "name",
            "slug",
            "id",
            "show_dashboard",
            "components",
            "auto_assign",
            "url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:componentlist-detail", "lookup_field": "slug"}
        }


class ProjectComponentSerializer(ComponentSerializer):
    class Meta(ComponentSerializer.Meta):
        fields = tuple(
            field for field in ComponentSerializer.Meta.fields if field != "project"
        )


class AddonSerializer(serializers.ModelSerializer[Addon]):
    component = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("component__project__slug", "component__slug"),
        read_only=True,
        strip_parts=1,
    )
    project: serializers.HyperlinkedRelatedField[Project] = (
        serializers.HyperlinkedRelatedField(
            view_name="api:project-detail",
            lookup_field="slug",
            read_only=True,
        )
    )
    configuration = serializers.JSONField(required=False)

    class Meta:
        model = Addon
        fields = (
            "component",
            "project",
            "name",
            "id",
            "configuration",
            "url",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "url": {"view_name": "api:addon-detail"}
        }

    @staticmethod
    def check_addon(name, queryset) -> None:
        installed = set(queryset.values_list("name", flat=True))
        available = {
            x.name for x in ADDONS.values() if x.multiple or x.name not in installed
        }
        if name not in available:
            raise serializers.ValidationError(
                {"name": f"Add-on already installed: {name}"}
            )

    @staticmethod
    def serialize_submitted_configuration(form, configuration):
        submitted = set(configuration) if isinstance(configuration, dict) else set()
        fields = set(form.fields)
        return {
            key: value
            for key, value in form.serialize_form().items()
            if key in submitted or key not in fields
        }

    def validate(self, attrs):
        instance = self.instance
        try:
            name = attrs["name"]
        except KeyError as error:
            if self.partial and instance:
                name = instance.name
            else:
                raise serializers.ValidationError(
                    {"name": "Can not change add-on name"}
                ) from error
        # Update or create
        component = instance.component if instance else self._context.get("component")
        project = instance.project if instance else self._context.get("project")

        # This could probably work, but it safer not to allow it
        if instance and instance.name != name:
            raise serializers.ValidationError({"name": "Can not change add-on name"})
        try:
            addon_class = ADDONS[name]
        except KeyError as error:
            raise serializers.ValidationError(
                {"name": f"Add-on not found: {name}"}
            ) from error

        # Don't allow duplicate add-ons
        addon = instance.addon if instance else addon_class(Addon())
        if not component and addon_class.needs_component:
            raise serializers.ValidationError(
                {"component": "This add-on can only be installed on the component."}
            )
        if not instance:
            if component:
                self.check_addon(name, Addon.objects.filter_component(component))
                if not addon.can_install(component=component):
                    raise serializers.ValidationError(
                        {"name": f"could not enable add-on {name}, not compatible"}
                    )
            if project:
                self.check_addon(name, Addon.objects.filter_project(project))

        if addon.has_settings() and (not instance or "configuration" in attrs):
            if instance:
                form = addon.get_settings_form(
                    None, data=attrs.get("configuration", {})
                )
            else:
                form = addon.get_add_form(
                    None,
                    component=component,
                    project=project,
                    data=attrs.get("configuration", {}),
                )
            if form is None:
                raise serializers.ValidationError(
                    {"configuration": "Can not configure add-on"}
                )
            if not form.is_valid():
                raise serializers.ValidationError(
                    {"configuration": list(get_form_errors(form))}
                )
            attrs["configuration"] = self.serialize_submitted_configuration(
                form, attrs.get("configuration", {})
            )
        return attrs

    def create(self, validated_data):
        validated_data["acting_user"] = self.context["request"].user
        return super().create(validated_data)

    def save(self, **kwargs):
        result = super().save(**kwargs)
        instance = self.instance
        if instance is None:
            msg = "Add-on serializer did not produce an instance"
            raise RuntimeError(msg)
        instance.addon.post_configure()
        return result


class MetricsSerializer(ReadOnlySerializer):
    units = serializers.IntegerField(source="all")
    units_translated = serializers.IntegerField(source="translated")
    users = serializers.IntegerField(source="get_users")
    changes = serializers.IntegerField(source="total_changes")
    projects = serializers.IntegerField(source="get_projects")
    components = serializers.IntegerField(source="get_components")
    translations = serializers.IntegerField(source="get_translations")

    languages = serializers.IntegerField(source="get_languages")
    checks = serializers.IntegerField(source="get_checks")
    configuration_errors = serializers.IntegerField(source="get_configuration_errors")
    suggestions = serializers.IntegerField(source="get_suggestions")
    celery_queues = serializers.DictField(
        child=serializers.IntegerField(), source="get_celery_queues"
    )
    name = serializers.CharField(source="get_name")
    version = serializers.CharField(required=False)

    def to_representation(self, instance):
        result = super().to_representation(instance)
        if settings.VERSION_DISPLAY == VERSION_DISPLAY_HIDE:
            result.pop("version", None)
        else:
            result["version"] = GIT_VERSION
        return result


class SearchResultSerializer(ReadOnlySerializer):
    url = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()


TASK_RESULT_SCHEMA = {
    "oneOf": [
        {"type": "object", "additionalProperties": True},
        {"type": "array", "items": {}},
        {"type": "string"},
        {"type": "number"},
        {"type": "integer"},
        {"type": "boolean"},
        {"type": "null"},
    ]
}


@extend_schema_field(TASK_RESULT_SCHEMA)
class TaskResultField(serializers.JSONField):
    pass


class TaskSerializer(ReadOnlySerializer):
    completed = serializers.BooleanField()
    progress = serializers.IntegerField(min_value=0, max_value=100)
    result = TaskResultField()
    log = serializers.CharField(allow_blank=True)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Service settings example",
            value={
                "service": "service_name",
                "configuration": {"key": "xxxxx", "url": "https://api.service.com/"},
            },
        )
    ]
)
class SingleServiceConfigSerializer(serializers.Serializer):
    service = serializers.CharField()
    configuration = serializers.DictField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Service settings example",
            value={
                "service1": {"key": "XXXXXXX", "url": "https://api.service.com/"},
                "service2": {"secret": "SECRET_KEY", "credentials": "XXXXXXX"},
            },
            request_only=False,
            response_only=True,
        )
    ]
)
class ProjectMachinerySettingsSerializer(serializers.Serializer):
    def to_representation(self, instance: Project):
        return dict(instance.machinery_settings)


class ProjectMachinerySettingsSerializerExtension(OpenApiSerializerExtension):
    target_class = ProjectMachinerySettingsSerializer

    def map_serializer(self, auto_schema: AutoSchema, direction):
        return build_object_type(properties={"service_name": build_basic_type(dict)})


class BackupSerializer(serializers.Serializer):
    name = serializers.CharField()
    timestamp = serializers.DateTimeField()
    size = serializers.IntegerField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


def edit_service_settings_response_serializer(
    _method: str, *codes
) -> dict[int, serializers.Serializer]:
    serializers_ = {
        200: MessageResponseSerializer,
        201: MessageResponseSerializer,
        400: ErrorResponse400Serializer,
    }
    return {code: serializers_[code] for code in codes}


class ErrorResponse400TypeEnum(models.TextChoices):
    VALIDATION_ERROR = ValidationErrorEnum.VALIDATION_ERROR.value
    CLIENT_ERROR = ClientErrorEnum.CLIENT_ERROR.value


ERROR_CODE_400_EXAMPLES = (
    "blank",
    "date",
    "datetime",
    "does_not_exist",
    "empty",
    "incorrect_match",
    "incorrect_type",
    "invalid",
    "invalid_choice",
    "invalid_image",
    "invalid_list",
    "make_aware",
    "max_length",
    "max_string_length",
    "max_value",
    "min_value",
    "no_match",
    "no_name",
    "not_a_list",
    "null",
    "null_characters_not_allowed",
    "overflow",
    "parse_error",
    "required",
    "surrogate_characters_not_allowed",
    "unique",
)


@extend_schema_field(
    {
        "type": "string",
        "description": "Error code. The examples list common validation and parse error codes.",
        "examples": list(ERROR_CODE_400_EXAMPLES),
    }
)
class ErrorCode400Field(serializers.CharField):
    pass


class Error400Serializer(serializers.Serializer):
    code = ErrorCode400Field()
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class ErrorResponse400Serializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=ErrorResponse400TypeEnum.choices)
    errors = Error400Serializer(many=True)


class ErrorCode423Enum(models.TextChoices):
    REPOSITORY_LOCKED = "repository-locked"
    COMPONENT_LOCKED = "component-locked"
    UNKNOWN_LOCKED = "unknown-locked"


class Error423Serializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=ErrorCode423Enum.choices)
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class ErrorResponse423Serializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=ServerErrorEnum.choices)
    errors = Error423Serializer(many=True)
