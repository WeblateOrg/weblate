#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from django.conf import settings
from django.core.exceptions import PermissionDenied
from rest_framework import serializers

from weblate.accounts.models import Subscription
from weblate.auth.models import Group, Permission, Role, User
from weblate.lang.models import Language, Plural
from weblate.screenshots.models import Screenshot
from weblate.trans.defines import LANGUAGE_NAME_LENGTH, REPO_LENGTH
from weblate.trans.models import (
    AutoComponentList,
    Change,
    Component,
    ComponentList,
    Project,
    Translation,
    Unit,
)
from weblate.trans.util import check_upload_method_permissions, cleanup_repo_url
from weblate.utils.site import get_site_url
from weblate.utils.validators import validate_bitmap


class MultiFieldHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def __init__(self, strip_parts=0, **kwargs):
        self.strip_parts = strip_parts
        super().__init__(**kwargs)

    # pylint: disable=redefined-builtin
    def get_url(self, obj, view_name, request, format):
        """Given an object, return the URL that hyperlinks to the object.

        May raise a `NoReverseMatch` if the `view_name` and `lookup_field` attributes
        are not configured to correctly match the URL conf.
        """
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, "pk") and obj.pk is None:
            return None

        kwargs = {}
        for lookup in self.lookup_field:
            value = obj
            for key in lookup.split("__"):
                # NULL value
                if value is None:
                    return None
                value = getattr(value, key)
            if self.strip_parts:
                lookup = "__".join(lookup.split("__")[self.strip_parts :])
            kwargs[lookup] = value
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)


class AbsoluteURLField(serializers.CharField):
    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if "http:/" not in value and "https:/" not in value:
            return get_site_url(value)
        return value


class RemovableSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        remove_fields = kwargs.pop("remove_fields", None)
        super().__init__(*args, **kwargs)

        if remove_fields:
            # for multiple fields in a list
            for field_name in remove_fields:
                self.fields.pop(field_name)


class LanguagePluralSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plural
        fields = (
            "id",
            "source",
            "number",
            "formula",
            "type",
        )


class LanguageSerializer(serializers.ModelSerializer):
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
            "code",
            "name",
            "plural",
            "aliases",
            "direction",
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
            isinstance(self.parent, ProjectSerializer)
            and self.field_name == "source_language"
        )

    def validate_code(self, value):
        check_query = Language.objects.filter(code=value)
        if not check_query.exists() and self.is_source_language:
            raise serializers.ValidationError(
                "Language with this language code was not found."
            )
        return value

    def validate_plural(self, value):
        if not value and not self.is_source_language:
            raise serializers.ValidationError("This field is required.")
        return value

    def validate_name(self, value):
        if not value and not self.is_source_language:
            raise serializers.ValidationError("This field is required.")
        return value

    def create(self, validated_data):
        plural_validated = validated_data.pop("plural", None)
        if not plural_validated:
            raise serializers.ValidationError("No valid plural data was provided.")

        check_query = Language.objects.filter(code=validated_data.get("code"))
        if check_query.exists():
            raise serializers.ValidationError(
                "Language with this Language code already exists."
            )
        language = Language.objects.create(**validated_data)
        plural = Plural(language=language, **plural_validated)
        plural.save()
        return language

    def get_value(self, dictionary):
        if self.is_source_language and "source_language" in dictionary:
            value = dictionary["source_language"]
            if isinstance(value, str):
                return {"code": value}
        return super().get_value(dictionary)


class FullUserSerializer(serializers.ModelSerializer):
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
            "email",
            "full_name",
            "username",
            "groups",
            "notifications",
            "is_superuser",
            "is_active",
            "date_joined",
            "url",
            "statistics_url",
        )
        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"}
        }


class BasicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "full_name",
            "username",
        )


class PermissionSerializer(serializers.RelatedField):
    class Meta:
        model = Permission

    def to_representation(self, value):
        return value.codename

    def get_queryset(self):
        return Permission.objects.all()

    def to_internal_value(self, data):
        check_query = Permission.objects.filter(codename=data)
        if not check_query.exists():
            raise serializers.ValidationError(
                "Permission with this codename was not found."
            )
        return data


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True)

    class Meta:
        model = Role
        fields = (
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


class GroupSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = Group
        fields = (
            "name",
            "project_selection",
            "language_selection",
            "url",
            "roles",
            "languages",
            "projects",
            "componentlists",
            "components",
        )
        extra_kwargs = {"url": {"view_name": "api:group-detail", "lookup_field": "id"}}


class ProjectSerializer(serializers.ModelSerializer):
    web_url = AbsoluteURLField(source="get_absolute_url", read_only=True)
    source_language = LanguageSerializer(required=False)
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
    languages_url = serializers.HyperlinkedIdentityField(
        view_name="api:project-languages", lookup_field="slug"
    )

    class Meta:
        model = Project
        fields = (
            "name",
            "slug",
            "id",
            "web",
            "source_language",
            "web_url",
            "url",
            "components_list_url",
            "repository_url",
            "statistics_url",
            "changes_list_url",
            "languages_url",
        )
        extra_kwargs = {
            "url": {"view_name": "api:project-detail", "lookup_field": "slug"}
        }

    def create(self, validated_data):
        source_language_validated = validated_data.get("source_language")
        if source_language_validated:
            validated_data["source_language"] = Language.objects.get(
                code=source_language_validated.get("code")
            )
        project = Project.objects.create(**validated_data)
        return project


class RepoField(serializers.CharField):
    def get_attribute(self, instance):
        if instance.linked_component:
            instance = instance.linked_component
        url = getattr(instance, self.source)
        if not settings.HIDE_REPO_CREDENTIALS:
            return url
        return cleanup_repo_url(url)


class ComponentSerializer(RemovableSerializer):
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
    changes_list_url = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-changes", lookup_field=("project__slug", "slug")
    )
    license_url = serializers.CharField(read_only=True)

    repo = RepoField(max_length=REPO_LENGTH)

    push = RepoField(required=False, allow_blank=True, max_length=REPO_LENGTH)

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    class Meta:
        model = Component
        fields = (
            "name",
            "slug",
            "id",
            "project",
            "vcs",
            "repo",
            "git_export",
            "branch",
            "push_branch",
            "filemask",
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
            "changes_list_url",
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
            "allow_translation_propagation",
            "enable_suggestions",
            "suggestion_voting",
            "suggestion_autoaccept",
            "push_on_commit",
            "commit_pending_age",
            "auto_lock_error",
            "language_regex",
            "variant_regex",
        )
        extra_kwargs = {
            "url": {
                "view_name": "api:component-detail",
                "lookup_field": ("project__slug", "slug"),
            }
        }

    def to_representation(self, instance):
        """Remove VCS properties if user has no permission for that."""
        result = super().to_representation(instance)
        user = self.context["request"].user
        if not user.has_perm("vcs.view", instance):
            result["vcs"] = None
            result["repo"] = None
            result["branch"] = None
            result["filemask"] = None
            result["push"] = None
        return result

    def to_internal_value(self, data):
        result = super().to_internal_value(data)
        if "project" in self._context:
            result["project"] = self._context["project"]
        return result

    def validate(self, attrs):
        # Call model validation here, DRF does not do that
        instance = Component(**attrs)
        instance.clean()
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
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


class TranslationSerializer(RemovableSerializer):
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


class MonolingualUnitSerializer(serializers.Serializer):
    key = serializers.CharField()
    value = serializers.CharField()


class ReadOnlySerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        return None

    def create(self, validated_data):
        return None


class LockSerializer(serializers.ModelSerializer):
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
        choices=("translate", "approve", "suggest", "fuzzy", "replace", "source"),
        required=False,
        default="translate",
    )
    fuzzy = serializers.ChoiceField(
        choices=("", "process", "approve"), required=False, default=""
    )
    conflicts = serializers.ChoiceField(
        choices=("", "replace-translated", "replace-approved"),
        required=False,
        default="",
    )

    def check_perms(self, user, obj):
        data = self.validated_data
        if data["conflicts"] and not user.has_perm("upload.overwrite", obj):
            raise PermissionDenied()
        if data["conflicts"] == "replace-approved" and not user.has_perm(
            "unit.review", obj
        ):
            raise PermissionDenied()

        if data["method"] == "source" and not obj.is_source:
            raise serializers.ValidationError(
                "Source upload is supported only on source language."
            )

        if not check_upload_method_permissions(user, obj, data["method"]):
            raise PermissionDenied()


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
            "last_change": stats.last_changed,
            "recent_changes": stats.recent_changes,
            "translated": stats.translated,
            "translated_words": stats.translated_words,
            "translated_percent": stats.translated_percent,
            "translated_words_percent": stats.translated_words_percent,
            "translated_chars": stats.translated_chars,
            "translated_chars_percent": stats.translated_chars_percent,
            "total_chars": stats.all_chars,
            "fuzzy": stats.fuzzy,
            "fuzzy_percent": stats.fuzzy_percent,
            "failing": stats.allchecks,
            "failing_percent": stats.allchecks_percent,
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
        result = {
            "translated": profile.translated,
            "suggested": profile.suggested,
            "uploaded": profile.uploaded,
            "commented": profile.commented,
            "languages": profile.languages.count(),
        }
        return result


class UnitSerializer(RemovableSerializer):
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

    class Meta:
        model = Unit
        fields = (
            "translation",
            "source",
            "previous_source",
            "target",
            "id_hash",
            "content_hash",
            "location",
            "context",
            "note",
            "flags",
            "fuzzy",
            "translated",
            "approved",
            "position",
            "has_suggestion",
            "has_comment",
            "has_failing_check",
            "num_words",
            "priority",
            "id",
            "web_url",
            "url",
        )
        extra_kwargs = {"url": {"view_name": "api:unit-detail"}}


class ScreenshotSerializer(RemovableSerializer):
    component = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("component__project__slug", "component__slug"),
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
        fields = ("name", "component", "file_url", "units", "url")
        extra_kwargs = {"url": {"view_name": "api:screenshot-detail"}}


class ScreenshotFileSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(validators=[validate_bitmap])

    class Meta:
        model = Screenshot
        fields = ("image",)
        extra_kwargs = {"url": {"view_name": "api:screenshot-file"}}


class ChangeSerializer(RemovableSerializer):
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
            "glossary_term",
            "user",
            "author",
            "timestamp",
            "action",
            "target",
            "id",
            "action_name",
            "url",
        )
        extra_kwargs = {"url": {"view_name": "api:change-detail"}}


class AutoComponentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoComponentList
        fields = (
            "project_match",
            "component_match",
        )


class ComponentListSerializer(serializers.ModelSerializer):
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
