# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf import settings
from django.views.generic import RedirectView

from trans.feeds import (
    TranslationChangesFeed, SubProjectChangesFeed,
    ProjectChangesFeed, ChangesFeed, LanguageChangesFeed
)
from trans.views.changes import ChangesView
from weblate.sitemaps import sitemaps
import accounts.urls

# URL regexp for language code
LANGUAGE = r'(?P<lang>[^/-]{2,3}([_-][A-Za-z]{2})?(@[a-z]+)?)'

# URL regexp for project
PROJECT = r'(?P<project>[^/]+)/'

# URL regexp for subproject
SUBPROJECT = PROJECT + r'(?P<subproject>[^/]+)/'

# URL regexp for translations
TRANSLATION = SUBPROJECT + LANGUAGE + '/'

# URL regexp for project langauge pages
PROJECT_LANG = PROJECT + LANGUAGE + '/'

# URL regexp used as base for widgets
WIDGET = r'(?P<project>[^/]+)-(?P<widget>[^/-]+)-(?P<color>[^/-]+)'

admin.autodiscover()

handler404 = 'trans.views.basic.not_found'

admin.site.index_template = 'admin/custom-index.html'

urlpatterns = patterns(
    '',
    url(
        r'^$',
        'trans.views.basic.home',
        name='home',
    ),
    url(
        r'^projects/$',
        RedirectView.as_view(url='/')
    ),
    url(
        r'^projects/' + PROJECT + '$',
        'trans.views.basic.show_project',
        name='project',
    ),

    # Engagement pages
    url(
        r'^engage/' + PROJECT + '$',
        'trans.views.basic.show_engage',
        name='engage',
    ),
    url(
        r'^engage/' + PROJECT_LANG + '$',
        'trans.views.basic.show_engage',
        name='engage-lang',
    ),

    # Glossary/Dictionary pages
    url(
        r'^dictionaries/' + PROJECT + '$',
        'trans.views.dictionary.show_dictionaries',
        name='show_dictionaries',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + '$',
        'trans.views.dictionary.show_dictionary',
        name='show_dictionary',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'upload/$',
        'trans.views.dictionary.upload_dictionary',
        name='upload_dictionary',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'delete/$',
        'trans.views.dictionary.delete_dictionary',
        name='delete_dictionary',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'edit/$',
        'trans.views.dictionary.edit_dictionary',
        name='edit_dictionary',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'download/$',
        'trans.views.dictionary.download_dictionary',
        name='download_dictionary',
    ),

    # Subroject pages
    url(
        r'^projects/' + SUBPROJECT + '$',
        'trans.views.basic.show_subproject',
        name='subproject',
    ),
    url(
        r'^projects/' + SUBPROJECT + 'source/$',
        'trans.views.basic.show_source',
        name='show_source',
    ),
    url(
        r'^projects/' + SUBPROJECT + 'source/review/$',
        'trans.views.basic.review_source',
        name='review_source',
    ),

    # Translation pages
    url(
        r'^projects/' + TRANSLATION + '$',
        'trans.views.basic.show_translation',
        name='translation',
    ),
    url(
        r'^projects/' + TRANSLATION + 'translate/$',
        'trans.views.edit.translate',
        name='translate',
    ),
    url(
        r'^projects/' + TRANSLATION + 'download/$',
        'trans.views.files.download_translation',
        name='download_translation',
    ),
    url(
        r'^projects/' + TRANSLATION + 'language_pack/$',
        'trans.views.files.download_language_pack',
        name='download_language_pack',
    ),
    url(
        r'^projects/' + TRANSLATION + 'upload/$',
        'trans.views.files.upload_translation',
        name='upload_translation',
    ),
    url(
        r'^projects/' + TRANSLATION + 'auto/$',
        'trans.views.edit.auto_translation',
        name='auto_translation',
    ),
    url(
        r'^new-lang/' + SUBPROJECT + '$',
        'trans.views.basic.new_language',
        name='new-language',
    ),

    # Activity HTML
    url(
        r'^activity/html/$',
        'trans.views.charts.view_activity',
        name='view_activity',
    ),
    url(
        r'^activity/html/' + PROJECT + '$',
        'trans.views.charts.view_activity',
        name='view_activity_project',
    ),
    url(
        r'^activity/html/' + SUBPROJECT + '$',
        'trans.views.charts.view_activity',
        name='view_activity_subproject',
    ),
    url(
        r'^activity/html/' + TRANSLATION + '$',
        'trans.views.charts.view_activity',
        name='view_activity_translation',
    ),

    # Monthly activity
    url(
        r'^activity/month/$',
        'trans.views.charts.monthly_activity',
        name='monthly_activity',
    ),
    url(
        r'^activity/month/' + PROJECT + '$',
        'trans.views.charts.monthly_activity',
        name='monthly_activity_project',
    ),
    url(
        r'^activity/month/' + SUBPROJECT + '$',
        'trans.views.charts.monthly_activity',
        name='monthly_activity_subproject',
    ),
    url(
        r'^activity/month/' + TRANSLATION + '$',
        'trans.views.charts.monthly_activity',
        name='monthly_activity_translation',
    ),

    # Yearly activity
    url(
        r'^activity/year/$',
        'trans.views.charts.yearly_activity',
        name='yearly_activity',
    ),
    url(
        r'^activity/year/' + PROJECT + '$',
        'trans.views.charts.yearly_activity',
        name='yearly_activity_project',
    ),
    url(
        r'^activity/year/' + SUBPROJECT + '$',
        'trans.views.charts.yearly_activity',
        name='yearly_activity_subproject',
    ),
    url(
        r'^activity/year/' + TRANSLATION + '$',
        'trans.views.charts.yearly_activity',
        name='yearly_activity_translation',
    ),

    # Per language activity
    url(
        r'^activity/language/html/' + LANGUAGE + '/$',
        'trans.views.charts.view_language_activity',
        name='view_language_activity',
    ),
    url(
        r'^activity/language/month/' + LANGUAGE + '/$',
        'trans.views.charts.monthly_language_activity',
        name='monthly_language_activity',
    ),
    url(
        r'^activity/language/year/' + LANGUAGE + '/$',
        'trans.views.charts.yearly_language_activity',
        name='yearly_language_activity',
    ),

    # Per user activity
    url(
        r'^activity/user/month/(?P<user>[^/]+)/$',
        'trans.views.charts.monthly_user_activity',
        name='monthly_user_activity',
    ),
    url(
        r'^activity/user/year/(?P<user>[^/]+)/$',
        'trans.views.charts.yearly_user_activity',
        name='yearly_user_activity',
    ),

    # Comments
    url(
        r'^comment/(?P<pk>[0-9]+)/$',
        'trans.views.edit.comment',
        name='comment',
    ),

    # Git manipulation - commit
    url(
        r'^commit/' + PROJECT + '$',
        'trans.views.git.commit_project',
        name='commit_project',
    ),
    url(
        r'^commit/' + SUBPROJECT + '$',
        'trans.views.git.commit_subproject',
        name='commit_subproject',
    ),
    url(
        r'^commit/' + TRANSLATION + '$',
        'trans.views.git.commit_translation',
        name='commit_translation',
    ),

    # Git manipulation - update
    url(
        r'^update/' + PROJECT + '$',
        'trans.views.git.update_project',
        name='update_project',
    ),
    url(
        r'^update/' + SUBPROJECT + '$',
        'trans.views.git.update_subproject',
        name='update_subproject',
    ),
    url(
        r'^update/' + TRANSLATION + '$',
        'trans.views.git.update_translation',
        name='update_translation',
    ),

    # Git manipulation - push
    url(
        r'^push/' + PROJECT + '$',
        'trans.views.git.push_project',
        name='push_project',
    ),
    url(
        r'^push/' + SUBPROJECT + '$',
        'trans.views.git.push_subproject',
        name='push_subproject',
    ),
    url(
        r'^push/' + TRANSLATION + '$',
        'trans.views.git.push_translation',
        name='push_translation',
    ),

    # Git manipulation - reset
    url(
        r'^reset/' + PROJECT + '$',
        'trans.views.git.reset_project',
        name='reset_project',
    ),
    url(
        r'^reset/' + SUBPROJECT + '$',
        'trans.views.git.reset_subproject',
        name='reset_subproject',
    ),
    url(
        r'^reset/' + TRANSLATION + '$',
        'trans.views.git.reset_translation',
        name='reset_translation',
    ),

    # Locking
    url(
        r'^lock/' + PROJECT + '$',
        'trans.views.lock.lock_project',
        name='lock_project',
    ),
    url(
        r'^unlock/' + PROJECT + '$',
        'trans.views.lock.unlock_project',
        name='unlock_project',
    ),
    url(
        r'^lock/' + SUBPROJECT + '$',
        'trans.views.lock.lock_subproject',
        name='lock_subproject',
    ),
    url(
        r'^unlock/' + SUBPROJECT + '$',
        'trans.views.lock.unlock_subproject',
        name='unlock_subproject',
    ),
    url(
        r'^lock/' + TRANSLATION + '$',
        'trans.views.lock.lock_translation',
        name='lock_translation',
    ),
    url(
        r'^unlock/' + TRANSLATION + '$',
        'trans.views.lock.unlock_translation',
        name='unlock_translation',
    ),

    # Languages browsing
    url(
        r'^languages/$',
        'lang.views.show_languages',
        name='languages',
    ),
    url(
        r'^languages/' + LANGUAGE + '/$',
        'lang.views.show_language',
        name='show_language',
    ),

    # Checks browsing
    url(
        r'^checks/$',
        'trans.views.checks.show_checks',
        name='checks',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/$',
        'trans.views.checks.show_check',
        name='show_check',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + PROJECT + '$',
        'trans.views.checks.show_check_project',
        name='show_check_project',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + SUBPROJECT + '$',
        'trans.views.checks.show_check_subproject',
        name='show_check_subproject',
    ),

    # Changes browsing
    url(
        r'^changes/$',
        ChangesView.as_view(),
        name='changes',
    ),

    # Notification hooks
    url(
        r'^hooks/update/' + SUBPROJECT + '$',
        'trans.views.api.update_subproject',
        name='hook-subproject',
    ),
    url(
        r'^hooks/update/' + PROJECT + '$',
        'trans.views.api.update_project',
        name='hook-project',
    ),
    url(
        r'^hooks/github/$', 'trans.views.api.git_service_hook',
        {'service': 'github'},
        name='hook-github',
    ),
    url(
        r'^hooks/bitbucket/$', 'trans.views.api.git_service_hook',
        {'service': 'bitbucket'},
        name='hook-bitbucket',
    ),

    # Stats exports
    url(
        r'^exports/stats/' + SUBPROJECT + '$',
        'trans.views.api.export_stats',
        name='export_stats',
    ),

    # RSS exports
    url(
        r'^exports/rss/$',
        ChangesFeed(),
        name='rss',
    ),
    url(
        r'^exports/rss/language/' + LANGUAGE + '/$',
        LanguageChangesFeed(),
        name='rss-language',
    ),
    url(
        r'^exports/rss/' + PROJECT + '$',
        ProjectChangesFeed(),
        name='rss-project',
    ),
    url(
        r'^exports/rss/' + SUBPROJECT + '$',
        SubProjectChangesFeed(),
        name='rss-subproject',
    ),
    url(
        r'^exports/rss/' + TRANSLATION + '$',
        TranslationChangesFeed(),
        name='rss-translation',
    ),

    # Compatibility URLs for Widgets
    url(
        r'^widgets/' + PROJECT + '(?P<widget>[^/]+)/(?P<color>[^/]+)/$',
        'trans.views.widgets.render',
        name='widgets-compat-render-color',
    ),
    url(
        r'^widgets/' + PROJECT + '(?P<widget>[^/]+)/$',
        'trans.views.widgets.render',
        name='widgets-compat-render',
    ),

    # Engagement widgets
    url(
        r'^widgets/' + WIDGET + '-' + LANGUAGE + r'\.png$',
        'trans.views.widgets.render',
        name='widget-image-lang',
    ),
    url(
        r'^widgets/' + WIDGET + r'\.png$',
        'trans.views.widgets.render',
        name='widget-image',
    ),
    url(
        r'^widgets/' + PROJECT + '$',
        'trans.views.widgets.widgets',
        name='widgets',
    ),
    url(
        r'^widgets/$',
        'trans.views.widgets.widgets_root',
        name='widgets_root',
    ),

    # Data exports pages
    url(
        r'^data/$',
        'trans.views.basic.data_root',
        name='data_root',
    ),
    url(
        r'^data/' + PROJECT + '$',
        'trans.views.basic.data_project',
        name='data_project',
    ),

    # AJAX/JS backends
    url(
        r'^js/get/(?P<checksum>[^/]+)/$',
        'trans.views.js.get_string',
        name='js-get',
    ),
    url(
        r'^js/lock/' + TRANSLATION + '$',
        'trans.views.lock.update_lock',
        name='js-lock',
    ),
    url(
        r'^js/ignore-check/(?P<check_id>[0-9]+)/$',
        'trans.views.js.ignore_check',
        name='js-ignore-check',
    ),
    url(
        r'^js/i18n/$',
        'django.views.i18n.javascript_catalog',
        {'packages': ('weblate',)},
        name='js-catalog'
    ),
    url(
        r'^js/config/$',
        'trans.views.js.js_config',
        name='js-config',
    ),
    url(
        r'^js/translate/(?P<unit_id>[0-9]+)/$',
        'trans.views.js.translate',
        name='js-translate',
    ),
    url(
        r'^js/changes/(?P<unit_id>[0-9]+)/$',
        'trans.views.js.get_unit_changes',
        name='js-unit-changes',
    ),
    url(
        r'^js/other/(?P<unit_id>[0-9]+)/$',
        'trans.views.js.get_other',
        name='js-other',
    ),
    url(
        r'^js/dictionary/(?P<unit_id>[0-9]+)/$',
        'trans.views.js.get_dictionary',
        name='js-dictionary',
    ),
    url(
        r'^js/detail/' + SUBPROJECT + '(?P<checksum>[^/]+)/$',
        'trans.views.js.get_detail',
        name='js-detail',
    ),
    url(
        r'^js/git/' + PROJECT + '$',
        'trans.views.js.git_status_project',
        name='git_status_project',
    ),
    url(
        r'^js/git/' + SUBPROJECT + '$',
        'trans.views.js.git_status_subproject',
        name='git_status_subproject',
    ),
    url(
        r'^js/git/' + TRANSLATION + '$',
        'trans.views.js.git_status_translation',
        name='git_status_translation',
    ),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(
        r'^admin/report/$',
        'trans.admin_views.report',
        name='admin-report'
    ),
    url(
        r'^admin/ssh/$',
        'trans.admin_views.ssh',
        name='admin-ssh'
    ),
    url(
        r'^admin/performance/$',
        'trans.admin_views.performance',
        name='admin-performance'
    ),
    url(r'^admin/', include(admin.site.urls)),

    # Auth
    url(r'^accounts/', include(accounts.urls)),

    # Static pages
    url(r'^contact/', 'accounts.views.contact', name='contact'),
    url(r'^hosting/', 'accounts.views.hosting', name='hosting'),
    url(r'^about/$', 'trans.views.basic.about', name='about'),

    # User pages
    url(
        r'^user/(?P<user>[^/]+)/',
        'accounts.views.user_page',
        name='user_page',
    ),

    # Sitemap
    url(
        r'^sitemap\.xml$',
        'django.contrib.sitemaps.views.index',
        {'sitemaps': sitemaps}
    ),
    url(
        r'^sitemap-(?P<section>.+)\.xml$',
        'django.contrib.sitemaps.views.sitemap',
        {'sitemaps': sitemaps}
    ),

    # Media files
    url(
        r'^media/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT}
    ),
)
