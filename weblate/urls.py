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

from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin
from django.views.generic import RedirectView
import django.contrib.sitemaps.views
import django.views.i18n

from weblate.trans.feeds import (
    TranslationChangesFeed, SubProjectChangesFeed,
    ProjectChangesFeed, ChangesFeed, LanguageChangesFeed
)
from weblate.trans.views.changes import ChangesView, ChangesCSVView
import weblate.accounts.views
import weblate.lang.views
import weblate.trans.admin_views
import weblate.trans.views.acl
import weblate.trans.views.api
import weblate.trans.views.basic
import weblate.trans.views.charts
import weblate.trans.views.checks
import weblate.trans.views.dictionary
import weblate.trans.views.edit
import weblate.trans.views.files
import weblate.trans.views.git
import weblate.trans.views.js
import weblate.trans.views.lock
import weblate.trans.views.reports
import weblate.trans.views.source
import weblate.trans.views.widgets
from weblate.sitemaps import SITEMAPS
import weblate.accounts.urls
import weblate.api.urls

# URL regexp for language code
LANGUAGE = r'(?P<lang>[^/]+)'

# URL regexp for project
PROJECT = r'(?P<project>[^/]+)/'

# URL regexp for subproject
SUBPROJECT = PROJECT + r'(?P<subproject>[^/]+)/'

# URL regexp for translations
TRANSLATION = SUBPROJECT + LANGUAGE + '/'

# URL regexp for project langauge pages
PROJECT_LANG = PROJECT + LANGUAGE + '/'

# URL regexp used as base for widgets
WIDGET = r'(?P<widget>[^/-]+)-(?P<color>[^/-]+)'

# Widget extension match
EXTENSION = r'(?P<extension>(png|svg))'

admin.autodiscover()

handler403 = weblate.trans.views.basic.denied

handler404 = weblate.trans.views.basic.not_found

handler500 = weblate.trans.views.basic.server_error

admin.site.index_template = 'admin/custom-index.html'

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
        name='engage-lang',
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
        r'^delete-dictionaries/' + PROJECT_LANG + '$',
        weblate.trans.views.dictionary.delete_dictionary,
        name='delete_dictionary',
    ),
    url(
        r'^edit-dictionaries/' + PROJECT_LANG + '$',
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
        r'^projects/' + SUBPROJECT + '$',
        weblate.trans.views.basic.show_subproject,
        name='subproject',
    ),
    url(
        r'^projects/' + SUBPROJECT + 'source/$',
        weblate.trans.views.source.show_source,
        name='show_source',
    ),
    url(
        r'^projects/' + SUBPROJECT + 'source/review/$',
        weblate.trans.views.source.review_source,
        name='review_source',
    ),
    url(
        r'^source/(?P<pk>[0-9]+)/priority/$',
        weblate.trans.views.source.edit_priority,
        name='edit_priority'
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
        r'^download/' + TRANSLATION + '(?P<fmt>[a-z0-9]+)/$',
        weblate.trans.views.files.download_translation_format,
        name='download_translation_format',
    ),
    url(
        r'^language-pack/' + TRANSLATION + '$',
        weblate.trans.views.files.download_language_pack,
        name='download_language_pack',
    ),
    url(
        r'^upload/' + TRANSLATION + '$',
        weblate.trans.views.files.upload_translation,
        name='upload_translation',
    ),
    url(
        r'^auto-translate/' + TRANSLATION + '$',
        weblate.trans.views.edit.auto_translation,
        name='auto_translation',
    ),
    url(
        r'^credits/' + SUBPROJECT + '$',
        weblate.trans.views.reports.get_credits,
        name='credits',
    ),
    url(
        r'^counts/' + SUBPROJECT + '$',
        weblate.trans.views.reports.get_counts,
        name='counts',
    ),
    url(
        r'^new-lang/' + SUBPROJECT + '$',
        weblate.trans.views.basic.new_language,
        name='new-language',
    ),
    url(
        r'^add-user/' + PROJECT + '$',
        weblate.trans.views.acl.add_user,
        name='add-user',
    ),
    url(
        r'^delete-user/' + PROJECT + '$',
        weblate.trans.views.acl.delete_user,
        name='delete-user',
    ),
    url(
        r'^make-owner/' + PROJECT + '$',
        weblate.trans.views.acl.make_owner,
        name='make-owner',
    ),
    url(
        r'^revoke-owner/' + PROJECT + '$',
        weblate.trans.views.acl.revoke_owner,
        name='revoke-owner',
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
        r'^activity/month/' + SUBPROJECT + '$',
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
        r'^activity/year/' + SUBPROJECT + '$',
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
        r'^commit/' + SUBPROJECT + '$',
        weblate.trans.views.git.commit_subproject,
        name='commit_subproject',
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
        r'^update/' + SUBPROJECT + '$',
        weblate.trans.views.git.update_subproject,
        name='update_subproject',
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
        r'^push/' + SUBPROJECT + '$',
        weblate.trans.views.git.push_subproject,
        name='push_subproject',
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
        r'^reset/' + SUBPROJECT + '$',
        weblate.trans.views.git.reset_subproject,
        name='reset_subproject',
    ),
    url(
        r'^reset/' + TRANSLATION + '$',
        weblate.trans.views.git.reset_translation,
        name='reset_translation',
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
        r'^lock/' + SUBPROJECT + '$',
        weblate.trans.views.lock.lock_subproject,
        name='lock_subproject',
    ),
    url(
        r'^unlock/' + SUBPROJECT + '$',
        weblate.trans.views.lock.unlock_subproject,
        name='unlock_subproject',
    ),
    url(
        r'^lock/' + TRANSLATION + '$',
        weblate.trans.views.lock.lock_translation,
        name='lock_translation',
    ),
    url(
        r'^unlock/' + TRANSLATION + '$',
        weblate.trans.views.lock.unlock_translation,
        name='unlock_translation',
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

    # Checks browsing
    url(
        r'^checks/$',
        weblate.trans.views.checks.show_checks,
        name='checks',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/$',
        weblate.trans.views.checks.show_check,
        name='show_check',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + PROJECT + '$',
        weblate.trans.views.checks.show_check_project,
        name='show_check_project',
    ),
    url(
        r'^checks/(?P<name>[^/]+)/' + SUBPROJECT + '$',
        weblate.trans.views.checks.show_check_subproject,
        name='show_check_subproject',
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
        r'^hooks/update/' + SUBPROJECT + '$',
        weblate.trans.views.api.update_subproject,
        name='hook-subproject',
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
        r'^exports/stats/' + SUBPROJECT + '$',
        weblate.trans.views.api.export_stats,
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
        name='widget-image-lang-dash',
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
        name='widget-image-lang',
    ),
    url(
        r'^widgets/' + PROJECT + '$',
        weblate.trans.views.widgets.widgets,
        name='widgets',
    ),
    url(
        r'^widgets/$',
        weblate.trans.views.widgets.widgets_root,
        name='widgets_root',
    ),

    # Data exports pages
    url(
        r'^data/$',
        weblate.trans.views.basic.data_root,
        name='data_root',
    ),
    url(
        r'^data/' + PROJECT + '$',
        weblate.trans.views.basic.data_project,
        name='data_project',
    ),

    # AJAX/JS backends
    url(
        r'^js/lock/' + TRANSLATION + '$',
        weblate.trans.views.lock.update_lock,
        name='js-lock',
    ),
    url(
        r'^js/ignore-check/(?P<check_id>[0-9]+)/$',
        weblate.trans.views.js.ignore_check,
        name='js-ignore-check',
    ),
    url(
        r'^js/i18n/$',
        django.views.i18n.javascript_catalog,
        {'packages': ('weblate',)},
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
        r'^js/detail/' + SUBPROJECT + '(?P<checksum>[^/]+)/$',
        weblate.trans.views.js.get_detail,
        name='js-detail',
    ),
    url(
        r'^js/git/' + PROJECT + '$',
        weblate.trans.views.js.git_status_project,
        name='git_status_project',
    ),
    url(
        r'^js/git/' + SUBPROJECT + '$',
        weblate.trans.views.js.git_status_subproject,
        name='git_status_subproject',
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
        r'^admin/report/$',
        weblate.trans.admin_views.report,
        name='admin-report'
    ),
    url(
        r'^admin/ssh/$',
        weblate.trans.admin_views.ssh,
        name='admin-ssh'
    ),
    url(
        r'^admin/performance/$',
        weblate.trans.admin_views.performance,
        name='admin-performance'
    ),
    url(r'^admin/', include(admin.site.urls)),

    # Auth
    url(r'^accounts/', include(weblate.accounts.urls)),

    # Auth
    url(r'^api/', include(weblate.api.urls, namespace='api')),

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

    # Avatars
    # Compatibility URL, remove for 2.6
    url(
        r'^avatar/(?P<user>[^/]+)/(?P<size>(32|128))/$',
        weblate.accounts.views.user_avatar,
        name='user_avatar_compat',
    ),
    url(
        r'^avatar/(?P<size>(32|128))/(?P<user>[^/]+)\.png$',
        weblate.accounts.views.user_avatar,
        name='user_avatar',
    ),

    # Sitemap
    url(
        r'^sitemap\.xml$',
        django.contrib.sitemaps.views.index,
        {'sitemaps': SITEMAPS}
    ),
    url(
        r'^sitemap-(?P<section>.+)\.xml$',
        django.contrib.sitemaps.views.sitemap,
        {'sitemaps': SITEMAPS}
    ),

    # Compatibility redirects
    url(
        r'^projects/' + TRANSLATION + 'translate/$',
        RedirectView.as_view(
            url='/translate/%(project)s/%(subproject)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'zen/$',
        RedirectView.as_view(
            url='/zen/%(project)s/%(subproject)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'download/$',
        RedirectView.as_view(
            url='/download/%(project)s/%(subproject)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'language_pack/$',
        RedirectView.as_view(
            url='/language-pack/%(project)s/%(subproject)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'upload/$',
        RedirectView.as_view(
            url='/upload/%(project)s/%(subproject)s/%(lang)s/',
            permanent=True,
            query_string=True
        )
    ),
    url(
        r'^projects/' + TRANSLATION + 'auto/$',
        RedirectView.as_view(
            url='/auto-translate/%(project)s/%(subproject)s/%(lang)s/',
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

    # Old activity charts
    url(
        r'^activity/html/' + TRANSLATION + '$',
        RedirectView.as_view(
            url='/projects/%(project)s/%(subproject)s/%(lang)s/#activity',
            permanent=True,
        )
    ),
    url(
        r'^activity/html/' + SUBPROJECT + '$',
        RedirectView.as_view(
            url='/projects/%(project)s/%(subproject)s/#activity',
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
        weblate.trans.views.basic.search,
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
    # pylint: disable=C0413
    import weblate.billing.views
    urlpatterns += [
        url(
            r'^invoice/(?P<pk>[0-9]+)/download/$',
            weblate.billing.views.download_invoice,
            name='invoice-download',
        ),
    ]
