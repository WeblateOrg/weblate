# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, TypeVar, cast
from zipfile import BadZipfile

from django.conf import settings
from django.db import models
from django.db.models import Model
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.plumbing import build_basic_type, build_object_type
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema_field,
    extend_schema_serializer,
    inline_serializer,
)
from drf_standardized_errors.openapi_serializers import ServerErrorEnum
from rest_framework import serializers

from weblate.accounts.models import Subscription
from weblate.addons.models import ADDONS, Addon
from weblate.auth.models import AuthenticatedHttpRequest, Group, Permission, Role, User
from weblate.checks.models import CHECKS
from weblate.lang.models import Language, Plural
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.defines import BRANCH_LENGTH, LANGUAGE_NAME_LENGTH, REPO_LENGTH
from weblate.trans.models import (
    AutoComponentList,
    Category,
    Change,
    Component,
    ComponentList,
    Label,
    Project,
    Translation,
    Unit,
)
from weblate.trans.models.translation import NewUnitParams
from weblate.trans.util import check_upload_method_permissions, cleanup_repo_url
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_READONLY, StringState
from weblate.utils.validators import validate_bitmap
from weblate.utils.views import (
    create_component_from_doc,
    create_component_from_zip,
    get_form_errors,
    guess_filemask_from_doc,
)

if TYPE_CHECKING:
    from drf_spectacular.openapi import AutoSchema
    from rest_framework.request import Request

_MT = TypeVar("_MT", bound=Model)  # Model Type


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

    def get_url(self, obj, view_name, request: AuthenticatedHttpRequest, format):  # noqa: A002
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
        extra_kwargs = {
            "url": {"view_name": "api:language-detail", "lookup_field": "code"},
            "code": {"validators": []},
        }

    @property
    def is_source_language(self):
        return (
            isinstance(self.parent, ComponentSerializer)
            and self.field_name == "source_language"
        )

    def validate_code(self, value):
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


class FullUserSerializer(serializers.ModelSerializer[User]):
    groups = serializers.HyperlinkedIdentityField(
        view_name="api:group-detail",
        lookup_field="id",
        many=True,
        read_only=True,
    )
    notifications = serializers.HyperlinkedIdentityField(
        view_name="api:user-notifications",
        lookup_field="username",
        source="subscriptions",
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:user-statistics", lookup_field="username"
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "username",
            "groups",
            "notifications",
            "is_superuser",
            "is_active",
            "is_bot",
            "date_joined",
            "last_login",
            "url",
            "statistics_url",
        )
        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"}
        }


class BasicUserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "username",
        )


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
        extra_kwargs = {"url": {"view_name": "api:role-detail", "lookup_field": "id"}}

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


class GroupSerializer(serializers.ModelSerializer[Group]):
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
    componentlists = serializers.HyperlinkedRelatedField(
        view_name="api:componentlist-detail",
        lookup_field="slug",
        many=True,
        read_only=True,
    )
    components = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("project__slug", "slug"),
        many=True,
        read_only=True,
    )
    defining_project = serializers.HyperlinkedRelatedField(
        view_name="api:project-detail",
        lookup_field="slug",
        queryset=Project.objects.none(),
        required=False,
    )

    class Meta:
        model = Group
        fields = (
            "id",
            "name",
            "defining_project",
            "project_selection",
            "language_selection",
            "url",
            "roles",
            "languages",
            "projects",
            "componentlists",
            "components",
            "enforced_2fa",
        )
        extra_kwargs = {"url": {"view_name": "api:group-detail", "lookup_field": "id"}}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["defining_project"].queryset = user.managed_projects


class ProjectSerializer(serializers.ModelSerializer[Project]):
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
    credits_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-credits", lookup_field="slug"
    )
    machinery_settings = serializers.HyperlinkedIdentityField(
        view_name="api:project-machinery-settings", lookup_field="slug"
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
            "components_list_url",
            "repository_url",
            "statistics_url",
            "categories_url",
            "changes_list_url",
            "languages_url",
            "labels_url",
            "credits_url",
            "translation_review",
            "source_review",
            "set_language_team",
            "instructions",
            "enable_hooks",
            "language_aliases",
            "secondary_language",
            "enforced_2fa",
            "machinery_settings",
        )
        extra_kwargs = {
            "url": {"view_name": "api:project-detail", "lookup_field": "slug"}
        }


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

    def get_url(self, obj, view_name, request: Request, format):  # noqa: A002
        if not obj.in_progress():
            return None
        return super().get_url(obj, view_name, request, format)


class ComponentSerializer(RemovableSerializer[Component]):
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
    credits_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-credits", lookup_field=("project__slug", "slug")
    )
    license_url = serializers.CharField(read_only=True)
    source_language = LanguageSerializer(required=False)

    repo = RepoField(max_length=REPO_LENGTH)

    push = RepoField(required=False, allow_blank=True, max_length=REPO_LENGTH)
    branch = LinkedField(required=False, allow_blank=True, max_length=BRANCH_LENGTH)
    push_branch = LinkedField(
        required=False, allow_blank=True, max_length=BRANCH_LENGTH
    )
    locked = serializers.BooleanField(read_only=True)

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    zipfile = serializers.FileField(required=False)
    docfile = serializers.FileField(required=False)
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

    class Meta:
        model = Component
        fields = (
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
            "license",
            "license_url",
            "agreement",
            "web_url",
            "url",
            "repository_url",
            "translations_url",
            "statistics_url",
            "lock_url",
            "links_url",
            "changes_list_url",
            "task_url",
            "credits_url",
            "new_lang",
            "language_code_style",
            "push",
            "check_flags",
            "priority",
            "enforced_checks",
            "restricted",
            "repoweb",
            "report_source_bugs",
            "merge_style",
            "commit_message",
            "add_message",
            "delete_message",
            "merge_message",
            "addon_message",
            "pull_message",
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
            "variant_regex",
            "zipfile",
            "docfile",
            "addons",
            "is_glossary",
            "glossary_color",
            "disable_autoshare",
            "category",
            "linked_component",
            "locked",
        )
        extra_kwargs = {
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
        user = self.context["request"].user
        if not user.has_perm("vcs.view", instance):
            result["vcs"] = None
            result["repo"] = None
            result["branch"] = None
            result["filemask"] = None
            result["screenshot_filemask"] = None
            result["push"] = None
        return result

    def to_internal_value(self, data):
        # Preprocess to inject params based on content
        data = data.copy()

        # Provide a reasonable default
        if "manage_units" not in data and data.get("template"):
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
        if "category" not in result:
            result["category"] = None

        return result

    def validate(self, attrs):
        # Handle non-component args
        disable_autoshare = attrs.pop("disable_autoshare", False)
        docfile = attrs.pop("docfile", None)
        zipfile = attrs.pop("zipfile", None)

        # Restrict create fields on patching
        if self.instance and (docfile is not None or zipfile is not None):
            field = "docfile" if docfile is not None else "zipfile"
            raise serializers.ValidationError(
                {field: "This field is for creation only, use /file/ instead."}
            )

        # Build new or patched Component instance with changed attributes
        if self.instance:
            instance = copy(self.instance)
            for key, value in attrs.items():
                setattr(instance, key, value)
        else:
            instance = Component(**attrs)

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
                except BadZipfile as error:
                    raise serializers.ValidationError(
                        {"zipfile": "Could not parse uploaded ZIP file."}
                    ) from error

        # Call model validation here, DRF does not do that
        instance.clean()

        if not self.instance and not disable_autoshare:
            repo = instance.suggest_repo_link()
            if repo:
                attrs["repo"] = instance.repo = repo
                attrs["branch"] = instance.branch = ""
        return attrs


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

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    class Meta:
        model = Translation
        fields = (
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
        )
        extra_kwargs = {
            "url": {
                "view_name": "api:translation-detail",
                "lookup_field": (
                    "component__project__slug",
                    "component__slug",
                    "language__code",
                ),
            }
        }


class ReadOnlySerializer(serializers.Serializer):
    def update(self, instance, validated_data) -> None:
        return None

    def create(self, validated_data) -> None:
        return None


class LockSerializer(serializers.ModelSerializer[Component]):
    class Meta:
        model = Component
        fields = ("locked",)


class LockRequestSerializer(ReadOnlySerializer):
    lock = serializers.BooleanField()


class UploadRequestSerializer(ReadOnlySerializer):
    file = serializers.FileField()
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

        if data["method"] == "source" and not obj.is_source:
            raise serializers.ValidationError(
                {"method": "Source upload is supported only on source language."}
            )

        if not check_upload_method_permissions(user, obj, data["method"]):
            hint = "Check your permissions or use different translation object."
            if data["method"] == "add" and not obj.is_source:
                hint = "Try adding to the source instead of the translation."
            raise serializers.ValidationError(
                {"method": f"This method is not available here. {hint}"}
            )


class RepoRequestSerializer(ReadOnlySerializer):
    operation = serializers.ChoiceField(
        choices=("commit", "pull", "push", "reset", "cleanup")
    )


class StatisticsSerializer(ReadOnlySerializer):
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
    def __init__(self, child_allow_blank=False, **kwargs) -> None:
        kwargs["child"] = serializers.CharField(
            trim_whitespace=False, allow_blank=child_allow_blank
        )
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return getattr(instance, f"get_{self.field_name}_plurals")()


class MemorySerializer(serializers.ModelSerializer[Memory]):
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


class LabelSerializer(serializers.ModelSerializer[Label]):
    class Meta:
        model = Label
        fields = ("id", "name", "description", "color")
        read_only_fields = ("project",)


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


class UnitFlatLabelsSerializer(UnitLabelsSerializer):
    def to_representation(self, value):
        return value.id


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
    source_unit = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="api:unit-detail"
    )
    source = PluralField()
    target = PluralField()
    timestamp = serializers.DateTimeField(read_only=True)
    last_updated = serializers.DateTimeField(read_only=True)
    pending = serializers.BooleanField(read_only=True)
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
        )
        extra_kwargs = {"url": {"view_name": "api:unit-detail"}}


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
        choices=[
            choice for choice in StringState.choices if choice[0] != STATE_READONLY
        ],
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
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name="api:category-statistics",
        lookup_field="pk",
    )

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
        )
        extra_kwargs = {"url": {"view_name": "api:category-detail"}}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
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

    def to_internal_value(self, data):
        result = super().to_internal_value(data)

        # Add missing project context
        if "project" in self._context:
            result["project"] = self._context["project"]
        elif self.instance:
            result["project"] = self.instance.project

        # Workaround for https://github.com/encode/django-rest-framework/issues/7489
        if "category" not in result:
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
    file_url = serializers.HyperlinkedRelatedField(
        read_only=True, source="pk", view_name="api:screenshot-file"
    )
    units = serializers.HyperlinkedRelatedField(
        many=True, read_only=True, view_name="api:unit-detail"
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
        extra_kwargs = {"url": {"view_name": "api:screenshot-detail"}}


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
        extra_kwargs = {"url": {"view_name": "api:screenshot-detail"}}


class ScreenshotFileSerializer(serializers.ModelSerializer[Screenshot]):
    image = serializers.ImageField(validators=[validate_bitmap])

    class Meta:
        model = Screenshot
        fields = ("image",)
        extra_kwargs = {"url": {"view_name": "api:screenshot-file"}}


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
    unit = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="api:unit-detail"
    )
    user = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="api:user-detail", lookup_field="username"
    )
    author = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="api:user-detail", lookup_field="username"
    )

    class Meta:
        model = Change
        fields = (
            "unit",
            "component",
            "translation",
            "user",
            "author",
            "timestamp",
            "action",
            "target",
            "old",
            "details",
            "id",
            "action_name",
            "url",
        )
        extra_kwargs = {"url": {"view_name": "api:change-detail"}}


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
        extra_kwargs = {
            "url": {"view_name": "api:componentlist-detail", "lookup_field": "slug"}
        }


class AddonSerializer(serializers.ModelSerializer[Addon]):
    component = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("component__project__slug", "component__slug"),
        read_only=True,
        strip_parts=1,
    )
    project = serializers.HyperlinkedRelatedField(
        view_name="api:project-detail",
        lookup_field="slug",
        read_only=True,
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
        extra_kwargs = {"url": {"view_name": "api:addon-detail"}}

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
        addon = addon_class(Addon())
        if not component and addon_class.needs_component:
            raise serializers.ValidationError(
                {"component": "This add-on can only be installed on the component."}
            )
        if not instance:
            if component:
                self.check_addon(name, Addon.objects.filter_component(component))
                if not addon.can_install(component, None):
                    raise serializers.ValidationError(
                        {"name": f"could not enable add-on {name}, not compatible"}
                    )
            if project:
                self.check_addon(name, Addon.objects.filter_project(project))

        if addon.has_settings() and "configuration" in attrs:
            form = addon.get_add_form(
                None,
                component=component,
                project=project,
                data=attrs["configuration"],
            )
            form.is_valid()
            if not form.is_valid():
                raise serializers.ValidationError(
                    {"configuration": list(get_form_errors(form))}
                )
        return attrs

    def save(self, **kwargs):
        result = super().save(**kwargs)
        self.instance.addon.post_configure()
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


def edit_service_settings_response_serializer(
    method: str, *codes
) -> dict[int, serializers.Serializer]:
    serializers_ = {
        200: inline_serializer(
            f"{method}_200_Message_response_serializer",
            fields={
                "message": serializers.CharField(),
            },
        ),
        201: inline_serializer(
            f"{method}_201_Message_response_serializer",
            fields={
                "message": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            f"{method}_400_Error_message_serializer",
            fields={"errors": serializers.CharField()},
        ),
    }
    return {code: serializers_[code] for code in codes}


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
