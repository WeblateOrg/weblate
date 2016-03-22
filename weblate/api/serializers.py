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

from rest_framework import serializers

from weblate.trans.models import Project, SubProject, Translation


class ProjectSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = Project
        fields = (
            'id', 'name', 'slug', 'web', 'source_language',
        )


class ComponentSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = SubProject
        fields = (
            'id', 'name', 'slug', 'project', 'vcs', 'repo', 'git_export',
            'branch', 'filemask', 'template', 'file_format', 'license',
            'license_url',
        )


class TranslationSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = Translation
        fields = (
            'language', 'subproject', 'translated', 'fuzzy', 'total',
            'translated_words', 'fuzzy_words', 'failing_checks_words',
            'total_words', 'failing_checks', 'have_suggestion', 'have_comment',
            'language_code', 'filename', 'revision',
        )
