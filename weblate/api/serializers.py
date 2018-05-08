# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from rest_framework import serializers

from weblate.trans.models import (
    Project, Component, Translation, Unit, Change, Source,
)
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.utils.site import get_site_url
from weblate.utils.validators import validate_bitmap


class MultiFieldHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def __init__(self, strip_parts=0, **kwargs):
        self.strip_parts = strip_parts
        super(MultiFieldHyperlinkedIdentityField, self).__init__(**kwargs)

    # pylint: disable=redefined-builtin
    def get_url(self, obj, view_name, request, format):
        """
        Given an object, return the URL that hyperlinks to the object.

        May raise a `NoReverseMatch` if the `view_name` and `lookup_field`
        attributes are not configured to correctly match the URL conf.
        """
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        kwargs = {}
        for lookup in self.lookup_field:
            value = obj
            for key in lookup.split('__'):
                # NULL value
                if value is None:
                    return None
                value = getattr(value, key)
            if self.strip_parts:
                lookup = '__'.join(lookup.split('__')[self.strip_parts:])
            kwargs[lookup] = value
        return self.reverse(
            view_name, kwargs=kwargs, request=request, format=format
        )


class AbsoluteURLField(serializers.CharField):
    def get_attribute(self, instance):
        value = super(AbsoluteURLField, self).get_attribute(instance)
        if 'http:/' not in value and 'https:/' not in value:
            return get_site_url(value)
        return value


class RemovableSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        remove_fields = kwargs.pop('remove_fields', None)
        super(RemovableSerializer, self).__init__(*args, **kwargs)

        if remove_fields:
            # for multiple fields in a list
            for field_name in remove_fields:
                self.fields.pop(field_name)


class LanguageSerializer(serializers.ModelSerializer):
    web_url = AbsoluteURLField(source='get_absolute_url', read_only=True)

    class Meta(object):
        model = Language
        fields = (
            'code', 'name', 'direction',
            'web_url', 'url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:language-detail',
                'lookup_field': 'code'
            }
        }


class ProjectSerializer(serializers.ModelSerializer):
    web_url = AbsoluteURLField(source='get_absolute_url', read_only=True)
    source_language = LanguageSerializer(read_only=True)
    components_list_url = serializers.HyperlinkedIdentityField(
        view_name='api:project-components',
        lookup_field='slug',
    )
    changes_list_url = serializers.HyperlinkedIdentityField(
        view_name='api:project-changes',
        lookup_field='slug',
    )
    repository_url = serializers.HyperlinkedIdentityField(
        view_name='api:project-repository',
        lookup_field='slug',
    )
    statistics_url = serializers.HyperlinkedIdentityField(
        view_name='api:project-statistics',
        lookup_field='slug',
    )

    class Meta(object):
        model = Project
        fields = (
            'name', 'slug', 'web', 'source_language', 'web_url', 'url',
            'components_list_url', 'repository_url', 'statistics_url',
            'changes_list_url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:project-detail',
                'lookup_field': 'slug'
            },
        }


class ComponentSerializer(RemovableSerializer):
    web_url = AbsoluteURLField(source='get_absolute_url', read_only=True)
    project = ProjectSerializer(read_only=True)
    repository_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-repository',
        lookup_field=('project__slug', 'slug'),
    )
    translations_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-translations',
        lookup_field=('project__slug', 'slug'),
    )
    statistics_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-statistics',
        lookup_field=('project__slug', 'slug'),
    )
    lock_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-lock',
        lookup_field=('project__slug', 'slug'),
    )
    changes_list_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-changes',
        lookup_field=('project__slug', 'slug'),
    )
    repo = serializers.CharField(source='get_repo_url')

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    class Meta(object):
        model = Component
        fields = (
            'name', 'slug', 'project', 'vcs', 'repo', 'git_export',
            'branch', 'filemask', 'template', 'new_base', 'file_format',
            'license', 'license_url', 'web_url', 'url',
            'repository_url', 'translations_url', 'statistics_url',
            'lock_url', 'changes_list_url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:component-detail',
                'lookup_field': ('project__slug', 'slug'),
            }
        }

    def to_representation(self, instance):
        """Remove VCS properties if user has no permission for that"""
        result = super(ComponentSerializer, self).to_representation(instance)
        user = self.context['request'].user
        if not user.has_perm('vcs.view', instance):
            result['vcs'] = None
            result['repo'] = None
            result['branch'] = None
            result['filemask'] = None
        return result


class TranslationSerializer(RemovableSerializer):
    web_url = AbsoluteURLField(
        source='get_absolute_url', read_only=True
    )
    share_url = AbsoluteURLField(
        source='get_share_url', read_only=True
    )
    translate_url = AbsoluteURLField(
        source='get_translate_url', read_only=True
    )
    component = ComponentSerializer(
        read_only=True,
    )
    language = LanguageSerializer(
        read_only=True
    )
    is_template = serializers.BooleanField(
        read_only=True
    )
    total = serializers.IntegerField(
        source='stats.all', read_only=True,
    )
    total_words = serializers.IntegerField(
        source='stats.all_words', read_only=True,
    )
    translated = serializers.IntegerField(
        source='stats.translated', read_only=True,
    )
    translated_words = serializers.IntegerField(
        source='stats.translated_words', read_only=True,
    )
    translated_percent = serializers.FloatField(
        source='stats.translated_percent', read_only=True,
    )
    fuzzy = serializers.IntegerField(
        source='stats.fuzzy', read_only=True,
    )
    fuzzy_words = serializers.IntegerField(
        source='stats.fuzzy_words', read_only=True,
    )
    fuzzy_percent = serializers.FloatField(
        source='stats.fuzzy_percent', read_only=True,
    )
    failing_checks = serializers.IntegerField(
        source='stats.allchecks', read_only=True,
    )
    failing_checks_words = serializers.IntegerField(
        source='stats.allchecks_words', read_only=True,
    )
    failing_checks_percent = serializers.FloatField(
        source='stats.allchecks_percent', read_only=True,
    )
    have_suggestion = serializers.IntegerField(
        source='stats.suggestions', read_only=True,
    )
    have_comment = serializers.IntegerField(
        source='stats.comments', read_only=True,
    )
    last_author = serializers.CharField(
        source='get_last_author', read_only=True,
    )
    repository_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-repository',
        lookup_field=(
            'component__project__slug',
            'component__slug',
            'language__code',
        ),
    )
    statistics_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-statistics',
        lookup_field=(
            'component__project__slug',
            'component__slug',
            'language__code',
        ),
    )
    file_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-file',
        lookup_field=(
            'component__project__slug',
            'component__slug',
            'language__code',
        ),
    )
    changes_list_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-changes',
        lookup_field=(
            'component__project__slug',
            'component__slug',
            'language__code',
        ),
    )
    units_list_url = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-units',
        lookup_field=(
            'component__project__slug',
            'component__slug',
            'language__code',
        ),
    )

    serializer_url_field = MultiFieldHyperlinkedIdentityField

    class Meta(object):
        model = Translation
        fields = (
            'language', 'component',
            'language_code', 'filename', 'revision',
            'web_url', 'share_url', 'translate_url', 'url',
            'is_template',
            'total', 'total_words',
            'translated', 'translated_words', 'translated_percent',
            'fuzzy', 'fuzzy_words', 'fuzzy_percent',
            'failing_checks', 'failing_checks_words', 'failing_checks_percent',
            'have_suggestion', 'have_comment',
            'last_change', 'last_author',
            'repository_url', 'file_url', 'statistics_url', 'changes_list_url',
            'units_list_url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:translation-detail',
                'lookup_field': (
                    'component__project__slug',
                    'component__slug',
                    'language__code',
                ),
            }
        }


class ReadOnlySerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        return None

    def create(self, validated_data):
        return None


class LockSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = Component
        fields = ('locked', )


class LockRequestSerializer(ReadOnlySerializer):
    lock = serializers.BooleanField()


class UploadRequestSerializer(ReadOnlySerializer):
    overwrite = serializers.BooleanField()
    file = serializers.FileField()


class RepoRequestSerializer(ReadOnlySerializer):
    operation = serializers.ChoiceField(
        choices=('commit', 'pull', 'push', 'reset')
    )


class StatisticsSerializer(ReadOnlySerializer):
    def to_representation(self, instance):
        return instance.get_stats()


class UnitSerializer(RemovableSerializer):
    web_url = AbsoluteURLField(
        source='get_absolute_url', read_only=True
    )
    translation = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-detail',
        lookup_field=(
            'translation__component__project__slug',
            'translation__component__slug',
            'translation__language__code',
        ),
        strip_parts=1,
    )
    source_info = serializers.HyperlinkedRelatedField(
        read_only=True,
        source='source_info.pk',
        view_name='api:source-detail'
    )

    class Meta(object):
        model = Unit
        fields = (
            'translation', 'source', 'previous_source', 'target', 'id_hash',
            'content_hash', 'location', 'context', 'comment', 'flags', 'fuzzy',
            'translated', 'position', 'has_suggestion', 'has_comment',
            'has_failing_check', 'num_words', 'priority', 'id', 'web_url',
            'url', 'source_info',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:unit-detail',
            },
        }


class SourceSerializer(RemovableSerializer):
    component = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-detail',
        lookup_field=('component__project__slug', 'component__slug'),
        strip_parts=1,
    )
    units = serializers.HyperlinkedRelatedField(
        read_only=True,
        many=True,
        view_name='api:unit-detail'
    )
    screenshots = serializers.HyperlinkedRelatedField(
        read_only=True,
        many=True,
        view_name='api:screenshot-detail'
    )

    class Meta(object):
        model = Source
        fields = (
            'id_hash', 'component', 'timestamp', 'priority', 'check_flags',
            'url', 'units', 'screenshots',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:source-detail',
            },
        }


class ScreenshotSerializer(RemovableSerializer):
    component = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-detail',
        lookup_field=('component__project__slug', 'component__slug'),
        strip_parts=1,
    )
    file_url = serializers.HyperlinkedRelatedField(
        read_only=True,
        source='pk',
        view_name='api:screenshot-file'
    )
    sources = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name='api:source-detail'
    )

    class Meta(object):
        model = Screenshot
        fields = (
            'name', 'component', 'file_url', 'sources', 'url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:screenshot-detail',
            },
        }


class ScreenshotFileSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        validators=[validate_bitmap]
    )

    class Meta(object):
        model = Screenshot
        fields = (
            'image',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:screenshot-file',
            },
        }


class ChangeSerializer(RemovableSerializer):
    action_name = serializers.CharField(
        source='get_action_display', read_only=True
    )
    component = MultiFieldHyperlinkedIdentityField(
        view_name='api:component-detail',
        lookup_field=('component__project__slug', 'component__slug'),
        strip_parts=1,
    )
    translation = MultiFieldHyperlinkedIdentityField(
        view_name='api:translation-detail',
        lookup_field=(
            'translation__component__project__slug',
            'translation__component__slug',
            'translation__language__code'
        ),
        strip_parts=1,
    )
    unit = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='api:unit-detail'
    )

    class Meta(object):
        model = Change
        fields = (
            'unit', 'component', 'translation', 'dictionary', 'user',
            'author', 'timestamp', 'action', 'target', 'id', 'action_name',
            'url',
        )
        extra_kwargs = {
            'url': {
                'view_name': 'api:change-detail',
            },
        }
