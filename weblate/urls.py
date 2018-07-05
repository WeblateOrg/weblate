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

from django.conf.urls import include, url
from django.conf import settings
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView
import django.contrib.sitemaps.views
import django.views.i18n
import django.views.static

from weblate.trans.feeds import (
    TranslationChangesFeed, ComponentChangesFeed,
    ProjectChangesFeed, ChangesFeed, LanguageChangesFeed
)
from weblate.trans.views.changes import ChangesView, ChangesCSVView
import weblate.accounts.views
import weblate.addons.views
import weblate.checks.views
import weblate.lang.views
import weblate.screenshots.views
import weblate.trans.views.acl
import weblate.trans.views.agreement
import weblate.trans.views.api
import weblate.trans.views.basic
import weblate.trans.views.charts
import weblate.trans.views.dictionary
import weblate.trans.views.edit
import weblate.trans.views.files
import weblate.trans.views.git
import weblate.trans.views.js
import weblate.trans.views.lock
import weblate.trans.views.reports
import weblate.trans.views.search
import weblate.trans.views.settings
import weblate.trans.views.source
import weblate.trans.views.widgets
from weblate.sitemaps import SITEMAPS
import weblate.accounts.urls
import weblate.api.urls
import weblate.wladmin.sites

# URL regexp for language code
LANGUAGE = r'(?P<lang>[^/]+)'

# URL regexp for project
PROJECT = r'(?P<project>[^/]+)/'

# URL regexp for component
COMPONENT = PROJECT + r'(?P<component>[^/]+)/'

# URL regexp for translations
TRANSLATION = COMPONENT + LANGUAGE + '/'

# URL regexp for project language pages
PROJECT_LANG = PROJECT + LANGUAGE + '/'

# URL regexp used as base for widgets
WIDGET = r'(?P<widget>[^/-]+)-(?P<color>[^/-]+)'

# Widget extension match
EXTENSION = r'(?P<extension>(png|svg|bin))'

handler403 = weblate.trans.views.basic.denied

handler404 = weblate.trans.views.basic.not_found

handler500 = weblate.trans.views.basic.server_error

urlpatterns = [
    url(
        r'^$',
        weblate.trans.views.basic.home,
        name='home',
    ),
    url(
        r'^projects/$',
        weblate.trans.views.basic.list_projects,
        name='projects',
    ),
    url(
        r'^projects/' + PROJECT + '$',
        weblate.trans.views.basic.show_project,
        name='project',
    ),

    # Engagement pages
    url(
        r'^engage/' + PROJECT + '$',
        weblate.trans.views.basic.show_engage,
        name='engage',
    ),
    url(
        r'^engage/' + PROJECT_LANG + '$',
        weblate.trans.views.basic.show_engage,
        name='engage',
    ),

    # Glossary/Dictionary pages
    url(
        r'^dictionaries/' + PROJECT + '$',
        weblate.trans.views.dictionary.show_dictionaries,
        name='show_dictionaries',
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + '$',
        weblate.trans.views.dictionary.show_dictionary,
        name='show_dictionary',
    ),
    url(
        r'^upload-dictionaries/' + PROJECT_LANG + '$',
        weblate.trans.views.dictionary.upload_dictionary,
        name='upload_dictionary',
    ),
    url(
        r'^delete-dictionaries/' + PROJECT_LANG + '(?P<pk>[0-9]+)/$',
        weblate.trans.views.dictionary.delete_dictionary,
        name='delete_dictionary',
    ),
    url(
        r'^edit-dictionaries/' + PROJECT_LANG + '(?P<pk>[0-9]+)/$',
        weblate.trans.views.dictionary.edit_dictionary,
        name='edit_dictionary',
    ),
    url(
        r'^download-dictionaries/' + PROJECT_LANG + '$',
        weblate.trans.views.dictionary.download_dictionary,
        name='download_dictionary',
    ),

    # Subroject pages
    url(
        r'^projects/' + COMPONENT + '$',
        weblate.trans.views.basic.show_component,
        name='component',
    ),
    url(
        r'^projects/' + COMPONENT + 'source/$',
        weblate.trans.views.source.show_source,
        name='show_source',
    ),
    url(
        r'^projects/' + COMPONENT + 'source/review/$',
        weblate.trans.views.source.review_source,
        name='review_source',
    ),
    url(
        r'^matrix/' + COMPONENT + '$',
        weblate.trans.views.source.matrix,
        name='matrix',
    ),
    url(
        r'^js/matrix/' + COMPONENT + '$',
        weblate.trans.views.source.matrix_load,
        name='matrix-load',
    ),
    url(
        r'^source/(?P<pk>[0-9]+)/priority/$',
        weblate.trans.views.source.edit_priority,
        name='edit_priority'
    ),
    url(
        r'^source/(?P<pk>[0-9]+)/context/$',
        weblate.trans.views.source.edit_context,
        name='edit_context'
    ),
    url(
        r'^source/(?P<pk>[0-9]+)/check_flags/$',
        weblate.trans.views.source.edit_check_flags,
        name='edit_check_flags'
    ),

    # Translation pages
    url(
        r'^projects/' + TRANSLATION + '$',
        weblate.trans.views.basic.show_translation,
        name='translation',
    ),
    url(
        r'^component-list/(?P<name>[^/]*)/$',
        weblate.trans.views.basic.show_component_list,
        name='component-list',
    ),
    url(
        r'^translate/' + TRANSLATION + '$',
        weblate.trans.views.edit.translate,
        name='translate',
    ),
    url(
        r'^zen/' + TRANSLATION + '$',
        weblate.trans.views.edit.zen,
        name='zen',
    ),
    url(
        r'^download/' + TRANSLATION + '$',
        weblate.trans.views.files.download_translation,
        name='download_translation',
    ),
    url(
        r'^download/' + TRANSLATION + 'custom/$',
        weblate.trans.views.files.download_translation_format,
        name='download_translation_format',
    ),
    url(
        r'^upload/' + TRANSLATION + '$',
        weblate.trans.views.files.upload_translation,
        name='upload_translation',
    ),
    url(
        r'^new-unit/' + TRANSLATION + '$',
        weblate.trans.views.edit.new_unit,
        name='new-unit',
    ),
    url(
        r'^auto-translate/' + TRANSLATION + '$',
        weblate.trans.views.edit.auto_translation,
        name='auto_translation',
    ),
    url(
        r'^replace/' + PROJECT + '$',
        weblate.trans.views.search.search_replace,
        name='replace',
    ),
    url(
        r'^replace/' + COMPONENT + '$',
        weblate.trans.views.search.search_replace,
        name='replace',
    ),
    url(
        r'^replace/' + TRANSLATION + '$',
        weblate.trans.views.search.search_replace,
        name='replace',
    ),
    url(
        r'^state-change/' + PROJECT + '$',
        weblate.trans.views.search.state_change,
        name='state-change',
    ),
    url(
        r'^state-change/' + COMPONENT + '$',
        weblate.trans.views.search.state_change,
        name='state-change',
    ),
    url(
        r'^state-change/' + TRANSLATION + '$',
        weblate.trans.views.search.state_change,
        name='state-change',
    ),
    url(
        r'^credits/' + COMPONENT + '$',
        weblate.trans.views.reports.get_credits,
        name='credits',
    ),
    url(
        r'^counts/' + COMPONENT + '$',
        weblate.trans.views.reports.get_counts,
        name='counts',
    ),
    url(
        r'^new-lang/' + COMPONENT + '$',
        weblate.trans.views.basic.new_language,
        name='new-language',
    ),
    url(
        r'^addons/' + COMPONENT + '$',
        weblate.addons.views.AddonList.as_view(),
        name='addons',
    ),
    url(
        r'^addons/' + COMPONENT + '(?P<pk>[0-9]+)/$',
        weblate.addons.views.AddonDetail.as_view(),
        name='addon-detail',
    ),
    url(
        r'^access/' + PROJECT + '$',
        weblate.trans.views.acl.manage_access,
        name='manage-access',
    ),
    url(
        r'^access/' + PROJECT + 'change/$',
        weblate.trans.views.acl.change_access,
        name='change-access',
    ),
    url(
        r'^settings/' + PROJECT + '$',
        weblate.trans.views.settings.change_project,
        name='settings',
    ),
    url(
        r'^settings/' + COMPONENT + '$',
        weblate.trans.views.settings.change_component,
        name='settings',
    ),
    url(
        r'^contributor-agreement/' + COMPONENT + '$',
        weblate.trans.views.agreement.agreement_confirm,
        name='contributor-agreement',
    ),
    url(
        r'^access/' + PROJECT + 'add/$',
        weblate.trans.views.acl.add_user,
        name='add-user',
    ),
    url(
        r'^access/' + PROJECT + 'remove/$',
        weblate.trans.views.acl.delete_user,
        name='delete-user',
    ),
    url(
        r'^access/' + PROJECT + 'set/$',
        weblate.trans.views.acl.set_groups,
        name='set-groups',
    ),

    # Monthly activity
    url(
        r'^activity/month/$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/month/' + PROJECT + '$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/month/' + COMPONENT + '$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/month/' + TRANSLATION + '$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/language/month/' + LANGUAGE + '/$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/language/month/' + LANGUAGE + '/' + PROJECT + '$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),
    url(
        r'^activity/user/month/(?P<user>[^/]+)/$',
        weblate.trans.views.charts.monthly_activity,
        name='monthly_activity',
    ),

    # Yearly activity
    url(
        r'^activity/year/$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/year/' + PROJECT + '$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/year/' + COMPONENT + '$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/year/' + TRANSLATION + '$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/language/year/' + LANGUAGE + '/$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/language/year/' + LANGUAGE + '/' + PROJECT + '$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),
    url(
        r'^activity/user/year/(?P<user>[^/]+)/$',
        weblate.trans.views.charts.yearly_activity,
        name='yearly_activity',
    ),

    # Comments
    url(
        r'^comment/(?P<pk>[0-9]+)/$',
        weblate.trans.views.edit.comment,
        name='comment',
    ),
    url(
        r'^comment/(?P<pk>[0-9]+)/delete/$',
        weblate.trans.views.edit.delete_comment,
        name='delete-comment',
    ),

    # VCS manipulation - commit
    url(
        r'^commit/' + PROJECT + '$',
        weblate.trans.views.git.commit_project,
        name='commit_project',
    ),
    url(
        r'^commit/' + COMPONENT + '$',
        weblate.trans.views.git.commit_component,
        name='commit_component',
    ),
    url(
        r'^commit/' + TRANSLATION + '$',
        weblate.trans.views.git.commit_translation,
        name='commit_translation',
    ),

    # VCS manipulation - update
    url(
        r'^update/' + PROJECT + '$',
        weblate.trans.views.git.update_project,
        name='update_project',
    ),
    url(
        r'^update/' + COMPONENT + '$',
        weblate.trans.views.git.update_component,
        name='update_component',
    ),
    url(
        r'^update/' + TRANSLATION + '$',
        weblate.trans.views.git.update_translation,
        name='update_translation',
    ),

    # VCS manipulation - push
    url(
        r'^push/' + PROJECT + '$',
        weblate.trans.views.git.push_project,
        name='push_project',
    ),
    url(
        r'^push/' + COMPONENT + '$',
        weblate.trans.views.git.push_component,
        name='push_component',
    ),
    url(
        r'^push/' + TRANSLATION + '$',
        weblate.trans.views.git.push_translation,
        name='push_translation',
    ),

    # VCS manipulation - reset
    url(
        r'^reset/' + PROJECT + '$',
        weblate.trans.views.git.reset_project,
        name='reset_project',
    ),
    url(
        r'^reset/' + COMPONENT + '$',
        weblate.trans.views.git.reset_component,
        name='reset_component',
    ),
    url(
        r'^reset/' + TRANSLATION + '$',
        weblate.trans.views.git.reset_translation,
        name='reset_translation',
    ),

    # VCS manipulation - remove
    url(
        r'^remove/' + TRANSLATION + '$',
        weblate.trans.views.git.remove_translation,
        name='remove_translation',
    ),

    # Locking
    url(
        r'^lock/' + PROJECT + '$',
        weblate.trans.views.lock.lock_project,
        name='lock_project',
    ),
    url(
        r'^unlock/' + PROJECT + '$',
        weblate.trans.views.lock.unlock_project,
        name='unlock_project',
    ),
    url(
        r'^lock/' + COMPONENT + '$',
        weblate.trans.views.lock.lock_component,
        name='lock_component',
    ),
    url(
        r'^unlock/' + COMPONENT + '$',
        weblate.trans.views.lock.unlock_component,
        name='unlock_component',
    ),

    # Screenshots
    url(
        r'^screenshots/' + COMPONENT + '$',
        weblate.screenshots.views.ScreenshotList.as_view(),
        name='screenshots',
    ),
    url(
        r'^screenshot/(?P<pk>[0-9]+)/$',
        weblate.screenshots.views.ScreenshotDetail.as_view(),
        name='screenshot',
    ),
    url(
        r'^screenshot/(?P<pk>[0-9]+)/delete/$',
        weblate.screenshots.views.delete_screenshot,
        name='screenshot-delete',
    ),
    url(
        r'^screenshot/(?P<pk>[0-9]+)/remove/$',
        weblate.screenshots.views.remove_source,
        name='screenshot-remove-source',
    ),
    url(
        r'^js/screenshot/(?P<pk>[0-9]+)/get/$',
        weblate.screenshots.views.get_sources,
        name='screenshot-js-get',
    ),
    url(
        r'^js/screenshot/(?P<pk>[0-9]+)/search/$',
        weblate.screenshots.views.search_source,
        name='screenshot-js-search',
    ),
    url(
        r'^js/screenshot/(?P<pk>[0-9]+)/ocr/$',
        weblate.screenshots.views.ocr_search,
        name='screenshot-js-ocr',
    ),
    url(
        r'^js/screenshot/(?P<pk>[0-9]+)/add/$',
        weblate.screenshots.views.add_source,
        name='screenshot-js-add',
    ),

    # Languages browsing
    url(
        r'^languages/$',
        weblate.lang.views.show_languages,
        name='languages',
    ),
    url(
        r'^languages/' + LANGUAGE + '/$',
        weblate.lang.views.show_language,
        name='show_language',
    ),
    url(
        r'^languages/' + LANGUAGE + '/' + PROJECT + '$',
        weblate.lang.views.show_project,
        name='project-language',
    ),

    # Checks browsing
    url(
        r'^checks/$',
        weblate.checks.views.show_checks,
        name='checks',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/$',
        weblate.checks.views.show_check,
        name='show_check',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + PROJECT + '$',
        weblate.checks.views.show_check_project,
        name='show_check_project',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + COMPONENT + '$',
        weblate.checks.views.show_check_component,
        name='show_check_component',
    ),

    # Changes browsing
    url(
        r'^changes/$',
        ChangesView.as_view(),
        name='changes',
    ),
    url(
        r'^changes/csv/$',
        ChangesCSVView.as_view(),
        name='changes-csv',
    ),

    # Notification hooks
    url(
        r'^hooks/update/' + COMPONENT + '$',
        weblate.trans.views.api.update_component,
        name='hook-component',
    ),
    url(
        r'^hooks/update/' + PROJECT + '$',
        weblate.trans.views.api.update_project,
        name='hook-project',
    ),
    url(
        r'^hooks/github/$', weblate.trans.views.api.vcs_service_hook,
        {'service': 'github'},
        name='hook-github',
    ),
    url(
        r'^hooks/gitlab/$', weblate.trans.views.api.vcs_service_hook,
        {'service': 'gitlab'},
        name='hook-gitlab',
    ),
    url(
        r'^hooks/bitbucket/$', weblate.trans.views.api.vcs_service_hook,
        {'service': 'bitbucket'},
        name='hook-bitbucket',
    ),

    # Stats exports
    url(
        r'^exports/stats/' + COMPONENT + '$',
        weblate.trans.views.api.export_stats,
        name='export_stats',
    ),
    url(
        r'^exports/stats/' + PROJECT + '$',
        weblate.trans.views.api.export_stats_project,
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
        r'^exports/rss/' + COMPONENT + '$',
        ComponentChangesFeed(),
        name='rss-component',
    ),
    url(
        r'^exports/rss/' + TRANSLATION + '$',
        TranslationChangesFeed(),
        name='rss-translation',
    ),

    # Compatibility URLs for Widgets
    url(
        r'^widgets/' + PROJECT + '(?P<widget>[^/]+)/(?P<color>[^/]+)/$',
        weblate.trans.views.widgets.render_widget,
        name='widgets-compat-render-color',
    ),
    url(
        r'^widgets/' + PROJECT + '(?P<widget>[^/]+)/$',
        weblate.trans.views.widgets.render_widget,
        name='widgets-compat-render',
    ),
    url(
        r'^widgets/(?P<project>[^/]+)-' + WIDGET + '-' +
        LANGUAGE + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image-dash',
    ),
    url(
        r'^widgets/(?P<project>[^/]+)-' + WIDGET + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image-dash',
    ),

    # Engagement widgets
    url(
        r'^widgets/' + PROJECT + '-/' + WIDGET + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image',
    ),
    url(
        r'^widgets/' + PROJECT + LANGUAGE + '/' +
        WIDGET + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image',
    ),
    url(
        r'^widgets/' + PROJECT + '-/' +
        r'(?P<component>[^/]+)/' + WIDGET + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image',
    ),
    url(
        r'^widgets/' + PROJECT + LANGUAGE + '/' +
        r'(?P<component>[^/]+)/' + WIDGET + r'\.' + EXTENSION + r'$',
        weblate.trans.views.widgets.render_widget,
        name='widget-image',
    ),
    url(
        r'^widgets/' + PROJECT + '$',
        weblate.trans.views.widgets.widgets,
        name='widgets',
    ),
    url(
        r'^widgets/$',
        RedirectView.as_view(url='/projects/', permanent=True),
    ),

    # Data exports pages
    url(
        r'^data/$',
        RedirectView.as_view(url='/projects/', permanent=True),
    ),
    url(
        r'^data/' + PROJECT + '$',
        weblate.trans.views.basic.data_project,
        name='data_project',
    ),

    # AJAX/JS backends
    url(
        r'^js/ignore-check/(?P<check_id>[0-9]+)/$',
        weblate.trans.views.js.ignore_check,
        name='js-ignore-check',
    ),
    url(
        r'^js/i18n/$',
        cache_page(3600)(
            vary_on_cookie(
                django.views.i18n.JavaScriptCatalog.as_view(
                    packages=['weblate']
                )
            )
        ),
        name='js-catalog'
    ),
    url(
        r'^js/mt-services/$',
        weblate.trans.views.js.mt_services,
        name='js-mt-services',
    ),
    url(
        r'^js/translate/(?P<unit_id>[0-9]+)/$',
        weblate.trans.views.js.translate,
        name='js-translate',
    ),
    url(
        r'^js/changes/(?P<unit_id>[0-9]+)/$',
        weblate.trans.views.js.get_unit_changes,
        name='js-unit-changes',
    ),
    url(
        r'^js/translations/(?P<unit_id>[0-9]+)/$',
        weblate.trans.views.js.get_unit_translations,
        name='js-unit-translations',
    ),
    url(
        r'^js/detail/' + COMPONENT + '(?P<checksum>[^/]+)/$',
        weblate.trans.views.js.get_detail,
        name='js-detail',
    ),
    url(
        r'^js/git/' + PROJECT + '$',
        weblate.trans.views.js.git_status_project,
        name='git_status_project',
    ),
    url(
        r'^js/git/' + COMPONENT + '$',
        weblate.trans.views.js.git_status_component,
        name='git_status_component',
    ),
    url(
        r'^js/git/' + TRANSLATION + '$',
        weblate.trans.views.js.git_status_translation,
        name='git_status_translation',
    ),
    url(
        r'^js/zen/' + TRANSLATION + '$',
        weblate.trans.views.edit.load_zen,
        name='load_zen',
    ),
    url(
        r'^js/save-zen/' + TRANSLATION + '$',
        weblate.trans.views.edit.save_zen,
        name='save_zen',
    ),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(
        r'^admin/',
        include(
            (weblate.wladmin.sites.SITE.urls, 'weblate.wladmin'),
            namespace='admin'
        )
    ),

    # Auth
    url(r'^accounts/', include(weblate.accounts.urls)),

    # Auth
    url(r'^api/', include((weblate.api.urls, 'weblate.api'), namespace='api')),

    # Static pages
    url(r'^contact/', weblate.accounts.views.contact, name='contact'),
    url(r'^hosting/', weblate.accounts.views.hosting, name='hosting'),
    url(r'^about/$', weblate.trans.views.basic.about, name='about'),
    url(r'^stats/$', weblate.trans.views.basic.stats, name='stats'),

    # User pages
    url(
        r'^user/(?P<user>[^/]+)/$',
        weblate.accounts.views.user_page,
        name='user_page',
    ),
    url(
        r'^user/(?P<user>[^/]+)/suggestions/$',
        weblate.accounts.views.SuggestionView.as_view(),
        name='user_suggestions',
    ),

    # Avatars
    url(
        r'^avatar/(?P<size>(32|128))/(?P<user>[^/]+)\.png$',
        weblate.accounts.views.user_avatar,
        name='user_avatar',
    ),

    # Sitemap
    url(
        r'^sitemap\.xml$',
        cache_page(3600)(django.contrib.sitemaps.views.index),
        {'sitemaps': SITEMAPS, 'sitemap_url_name': 'sitemap'},
        name='sitemap-index',
    ),
    url(
        r'^sitemap-(?P<section>.+)\.xml$',
        cache_page(3600)(django.contrib.sitemaps.views.sitemap),
        {'sitemaps': SITEMAPS},
        name='sitemap',
    ),

    # Compatibility redirects
    url(
        r'^projects/' + TRANSLATION + 'translate/$',
        RedirectView.as_view(
            url='/translate/%(project)s/%(component)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'zen/$',
        RedirectView.as_view(
            url='/zen/%(project)s/%(component)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'download/$',
        RedirectView.as_view(
            url='/download/%(project)s/%(component)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'upload/$',
        RedirectView.as_view(
            url='/upload/%(project)s/%(component)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'auto/$',
        RedirectView.as_view(
            url='/auto-translate/%(project)s/%(component)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),

    url(
        r'^dictionaries/' + PROJECT_LANG + 'upload/$',
        RedirectView.as_view(
            url='/upload-dictionaries/%(project)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'delete/$',
        RedirectView.as_view(
            url='/delete-dictionaries/%(project)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'edit/$',
        RedirectView.as_view(
            url='/edit-dictionaries/%(project)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^dictionaries/' + PROJECT_LANG + 'download/$',
        RedirectView.as_view(
            url='/download-dictionaries/%(project)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^js/glossary/(?P<unit_id>[0-9]+)/$',
        weblate.trans.views.dictionary.add_dictionary,
        name='js-add-glossary',
    ),

    # Old activity charts
    url(
        r'^activity/html/' + TRANSLATION + '$',
        RedirectView.as_view(
            url='/projects/%(project)s/%(component)s/%(lang)s/#activity',
            permanent=True,
        )
    ),
    url(
        r'^activity/html/' + COMPONENT + '$',
        RedirectView.as_view(
            url='/projects/%(project)s/%(component)s/#activity',
            permanent=True,
        )
    ),
    url(
        r'^activity/html/' + PROJECT + '$',
        RedirectView.as_view(
            url='/projects/%(project)s/#activity',
            permanent=True,
        )
    ),
    url(
        r'^activity/language/html/' + LANGUAGE + '/$',
        RedirectView.as_view(
            url='/languages/%(lang)s/#activity',
            permanent=True,
        )
    ),

    # Site wide search
    url(
        r'^search/$',
        weblate.trans.views.search.search,
        name="search"
    ),
    url(
        r'^search/' + PROJECT + '$',
        weblate.trans.views.search.search,
        name="search"
    ),
    url(
        r'^search/' + COMPONENT + '$',
        weblate.trans.views.search.search,
        name="search"
    ),
    url(
        r'^languages/' + LANGUAGE + '/' + PROJECT + 'search/$',
        weblate.trans.views.search.search,
        name="search"
    ),

    # Health check
    url(
        r'^healthz/$',
        weblate.trans.views.basic.healthz,
        name='healthz',
    ),
]

if 'weblate.billing' in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.billing.views
    urlpatterns += [
        url(
            r'^invoice/(?P<pk>[0-9]+)/download/$',
            weblate.billing.views.download_invoice,
            name='invoice-download',
        ),
        url(
            r'^billing/$',
            weblate.billing.views.overview,
            name='billing',
        ),
    ]

if 'weblate.gitexport' in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.gitexport.views
    urlpatterns += [
        # Redirect clone from the Weblate project URL
        url(
            r'^projects/' + COMPONENT +
            '(?P<path>(info/|git-upload-pack)[a-z0-9_/-]*)$',
            RedirectView.as_view(
                url='/git/%(project)s/%(component)s/%(path)s',
                permanent=True,
                query_string=True
            )
        ),
        url(
            r'^projects/' + COMPONENT[:-1] +
            r'\.git/' + '(?P<path>(info/|git-upload-pack)[a-z0-9_/-]*)$',
            RedirectView.as_view(
                url='/git/%(project)s/%(component)s/%(path)s',
                permanent=True,
                query_string=True
            )
        ),
        # Redirect clone in case user adds .git to the path
        url(
            r'^git/' + COMPONENT[:-1] + r'\.git/' + '(?P<path>[a-z0-9_/-]*)$',
            RedirectView.as_view(
                url='/git/%(project)s/%(component)s/%(path)s',
                permanent=True,
                query_string=True
            )
        ),
        url(
            r'^git/' + COMPONENT + '(?P<path>[a-z0-9_/-]*)$',
            weblate.gitexport.views.git_export,
            name='git-export',
        ),
    ]

if 'weblate.legal' in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.legal.views
    urlpatterns += [
        url(
            r'^legal/',
            include(('weblate.legal.urls', 'weblate.legal'), namespace='legal')
        ),
    ]

if settings.DEBUG:
    urlpatterns += [
        url(
            r'^media/(?P<path>.*)$',
            django.views.static.serve,
            {'document_root': settings.MEDIA_ROOT}
        ),
    ]

if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import debug_toolbar
    urlpatterns += [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ]
