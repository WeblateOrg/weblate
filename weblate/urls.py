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
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic.simple import direct_to_template
from django.conf import settings
from django.views.generic import RedirectView
from django.contrib.sitemaps import GenericSitemap, Sitemap

from registration.views import activate, register

from weblate.accounts.forms import RegistrationForm
from weblate.trans.feeds import TranslationChangesFeed, SubProjectChangesFeed, ProjectChangesFeed, ChangesFeed, LanguageChangesFeed
from weblate.trans.models import Project, SubProject, Translation
from weblate.accounts.models import Profile

admin.autodiscover()

handler404 = 'weblate.trans.views.not_found'

js_info_dict = {
    'packages': ('weblate',),
}

project_dict = {
    'queryset': Project.objects.all_acl(None),
    'date_field': 'get_last_change',
}

subproject_dict = {
    'queryset': SubProject.objects.all_acl(None),
    'date_field': 'get_last_change',
}

translation_dict = {
    'queryset': Translation.objects.all_acl(None),
    'date_field': 'get_last_change',
}

user_dict = {
    'queryset': Profile.objects.all(),
    'date_field': 'get_last_change',
}

class PagesSitemap(Sitemap):
    def items(self):
        return (
            ('/', 1.0, 'daily'),
            ('/about/', 0.8, 'daily'),
            ('/contact/', 0.2, 'monthly'),
        )

    def location(self, item):
        return item[0]

    def lastmod(self, item):
        from weblate.trans.models import Change
        return Change.objects.all()[0].timestamp

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]

class EngageSitemap(GenericSitemap):
    '''
    Wrapper around GenericSitemap to point to engage page.
    '''
    def location(self, obj):
        from django.core.urlresolvers import reverse
        return reverse('engage', kwargs={'project': obj.slug})

class EngageLangSitemap(Sitemap):
    '''
    Wrapper to generate sitemap for all per language engage pages.
    '''
    priority = 0.9

    def items(self):
        '''
        Return list of existing project, langauge tuples.
        '''
        ret = []
        for project in Project.objects.all_acl(None):
            for lang in project.get_languages():
                ret.append((project, lang))
        return ret

    def location(self, item):
        from django.core.urlresolvers import reverse
        return reverse('engage-lang', kwargs={'project': item[0].slug, 'lang': item[1].code})


sitemaps = {
    'project': GenericSitemap(project_dict, priority=0.8),
    'engage': EngageSitemap(project_dict, priority=1.0),
    'engagelang': EngageLangSitemap(),
    'subproject': GenericSitemap(subproject_dict, priority=0.6),
    'translation': GenericSitemap(translation_dict, priority=0.2),
    'user': GenericSitemap(user_dict, priority=0.1),
    'pages': PagesSitemap(),
}

admin.site.index_template = 'admin/custom-index.html'

urlpatterns = patterns('',
    url(r'^$', 'weblate.trans.views.home', name='home'),
    url(r'^projects/$', RedirectView.as_view(url='/')),
    url(r'^projects/(?P<project>[^/]*)/$', 'weblate.trans.views.show_project', name='project'),
    url(r'^engage/(?P<project>[^/]*)/$', 'weblate.trans.views.show_engage', name='engage'),
    url(r'^engage/(?P<project>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.show_engage', name='engage-lang'),

    url(r'^dictionaries/(?P<project>[^/]*)/$', 'weblate.trans.views.show_dictionaries'),
    url(r'^dictionaries/(?P<project>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.show_dictionary'),
    url(r'^dictionaries/(?P<project>[^/]*)/(?P<lang>[^/]*)/upload/$', 'weblate.trans.views.upload_dictionary'),
    url(r'^dictionaries/(?P<project>[^/]*)/(?P<lang>[^/]*)/delete/$', 'weblate.trans.views.delete_dictionary'),
    url(r'^dictionaries/(?P<project>[^/]*)/(?P<lang>[^/]*)/edit/$', 'weblate.trans.views.edit_dictionary'),
    url(r'^dictionaries/(?P<project>[^/]*)/(?P<lang>[^/]*)/download/$', 'weblate.trans.views.download_dictionary'),

    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.show_subproject', name='subproject'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/source/$', 'weblate.trans.views.show_source'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/source/review/$', 'weblate.trans.views.review_source'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.show_translation', name='translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/translate/$', 'weblate.trans.views.translate', name='translate'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/download/$', 'weblate.trans.views.download_translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/upload/$', 'weblate.trans.views.upload_translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/auto/$', 'weblate.trans.views.auto_translation'),

    url(r'^commit/(?P<project>[^/]*)/$', 'weblate.trans.views.commit_project'),
    url(r'^commit/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.commit_subproject'),
    url(r'^commit/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.commit_translation'),

    url(r'^update/(?P<project>[^/]*)/$', 'weblate.trans.views.update_project'),
    url(r'^update/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.update_subproject'),
    url(r'^update/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.update_translation'),

    url(r'^comment/(?P<pk>[0-9]*)/$', 'weblate.trans.views.comment'),

    url(r'^push/(?P<project>[^/]*)/$', 'weblate.trans.views.push_project'),
    url(r'^push/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.push_subproject'),
    url(r'^push/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.push_translation'),

    url(r'^reset/(?P<project>[^/]*)/$', 'weblate.trans.views.reset_project'),
    url(r'^reset/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.reset_subproject'),
    url(r'^reset/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.reset_translation'),

    url(r'^lock/(?P<project>[^/]*)/$', 'weblate.trans.views.lock_project'),
    url(r'^unlock/(?P<project>[^/]*)/$', 'weblate.trans.views.unlock_project'),
    url(r'^lock/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.lock_subproject'),
    url(r'^unlock/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.unlock_subproject'),
    url(r'^lock/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.lock_translation'),
    url(r'^unlock/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.unlock_translation'),

    url(r'^languages/$', 'weblate.trans.views.show_languages', name='languages'),
    url(r'^languages/(?P<lang>[^/]*)/$', 'weblate.trans.views.show_language'),

    url(r'^checks/$', 'weblate.trans.views.show_checks', name='checks'),
    url(r'^checks/(?P<name>[^/]*)/$', 'weblate.trans.views.show_check'),
    url(r'^checks/(?P<name>[^/]*)/(?P<project>[^/]*)/$', 'weblate.trans.views.show_check_project'),
    url(r'^checks/(?P<name>[^/]*)/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.show_check_subproject'),

    url(r'^hooks/update/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.api.update_subproject', name='hook-subproject'),
    url(r'^hooks/update/(?P<project>[^/]*)/$', 'weblate.trans.api.update_project', name='hook-project'),
    url(r'^hooks/github/$', 'weblate.trans.api.git_service_hook', {'service': 'github'}, name='hook-github'),
    url(r'^hooks/bitbucket/$', 'weblate.trans.api.git_service_hook', {'service': 'bitbucket'}, name='hook-bitbucket'),

    url(r'^exports/stats/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.api.export_stats', name='export-stats'),

    url(r'^exports/rss/$', ChangesFeed(), name='rss'),
    url(r'^exports/rss/language/(?P<lang>[^/]*)/$', LanguageChangesFeed(), name='rss-language'),
    url(r'^exports/rss/(?P<project>[^/]*)/$', ProjectChangesFeed(), name='rss-project'),
    url(r'^exports/rss/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', SubProjectChangesFeed(), name='rss-subproject'),
    url(r'^exports/rss/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', TranslationChangesFeed(), name='rss-translation'),

    # Not promoted, compatibility only:
    url(r'^widgets/(?P<project>[^/]*)/(?P<widget>[^/]*)/(?P<color>[^/]*)/$', 'weblate.trans.widgets.render'),
    url(r'^widgets/(?P<project>[^/]*)/(?P<widget>[^/]*)/$', 'weblate.trans.widgets.render'),

    url(r'^widgets/(?P<project>[^/]*)-(?P<widget>[^/-]*)-(?P<color>[^/-]*)-(?P<lang>[^/-]{2,3}([_-][A-Za-z]{2})?)\.png$', 'weblate.trans.widgets.render', name='widget-image-lang'),
    url(r'^widgets/(?P<project>[^/]*)-(?P<widget>[^/-]*)-(?P<color>[^/-]*)\.png$', 'weblate.trans.widgets.render', name='widget-image'),
    url(r'^widgets/(?P<project>[^/]*)/$', 'weblate.trans.widgets.widgets', name='widgets'),
    url(r'^widgets/$', 'weblate.trans.widgets.widgets_root', name='widgets_root'),

    url(r'^data/$', 'weblate.trans.views.data_root'),
    url(r'^data/(?P<project>[^/]*)/$', 'weblate.trans.views.data_project'),

    url(r'^js/get/(?P<checksum>[^/]*)/$', 'weblate.trans.views.get_string', name='js-get'),
    url(r'^js/lock/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.update_lock', name='js-lock'),
    url(r'^js/ignore-check/(?P<check_id>[0-9]*)/$', 'weblate.trans.views.ignore_check', name='js-ignore-check'),
    url(r'^js/i18n/$', 'django.views.i18n.javascript_catalog', js_info_dict),
    url(r'^js/config/$', 'weblate.trans.views.js_config', name='js-config'),
    url(r'^js/similar/(?P<unit_id>[0-9]*)/$', 'weblate.trans.views.get_similar', name='js-similar'),
    url(r'^js/other/(?P<unit_id>[0-9]*)/$', 'weblate.trans.views.get_other', name='js-other'),
    url(r'^js/dictionary/(?P<unit_id>[0-9]*)/$', 'weblate.trans.views.get_dictionary', name='js-dictionary'),
    url(r'^js/git/(?P<project>[^/]*)/$', 'weblate.trans.views.git_status_project'),
    url(r'^js/git/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'weblate.trans.views.git_status_subproject'),
    url(r'^js/git/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'weblate.trans.views.git_status_translation'),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/report/$', 'weblate.trans.admin_views.report'),
    url(r'^admin/ssh/$', 'weblate.trans.admin_views.ssh'),
    url(r'^admin/performance/$', 'weblate.trans.admin_views.performance'),
    url(r'^admin/', include(admin.site.urls)),

    # Auth
    url(r'^accounts/register/$', register, {
                'backend': 'registration.backends.default.DefaultBackend',
                'form_class': RegistrationForm,
                'extra_context': {'title': _('User registration')}
            },
            name='weblate_register'),
    url(r'^accounts/register/complete/$',
        direct_to_template,
        {
            'template': 'registration/registration_complete.html',
            'extra_context': {'title': _('User registration')},
        },
        name='registration_complete'),
    url(r'^accounts/register/closed/$',
        direct_to_template,
        {
            'template': 'registration/registration_closed.html',
            'extra_context': {'title': _('User registration')},
        },
        name='registration_disallowed'),
    url(r'^accounts/activate/complete/$',
        direct_to_template,
        {
            'template': 'registration/activation_complete.html',
            'extra_context': {'title': _('User registration')},
        },
        name='registration_activation_complete'),
    url(r'^accounts/activate/(?P<activation_key>\w+)/$',
        activate,
        {
            'backend': 'registration.backends.default.DefaultBackend',
            'extra_context': {
                'title': _('Account activation'),
                'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS,
            }
        },
        name='registration_activate'),
    url(r'^accounts/login/$',
        auth_views.login,
        {
            'template_name': 'registration/login.html',
            'extra_context': {'title': _('Login')},
        },
        name='auth_login'),
    url(r'^accounts/logout/$',
        auth_views.logout,
        {
            'template_name': 'registration/logout.html',
            'extra_context': {'title': _('Logged out')},
        },
        name='auth_logout'),
    url(r'^accounts/password/change/$',
        auth_views.password_change,
        {'extra_context': {'title': _('Change password')}},
        name='auth_password_change'),
    url(r'^accounts/password/change/done/$',
        auth_views.password_change_done,
        {'extra_context': {'title': _('Password changed')}},
        name='auth_password_change_done'),
    url(r'^accounts/password/reset/$',
        auth_views.password_reset,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset'),
    url(r'^accounts/password/reset/confirm/(?P<uidb36>[0-9A-Za-z]+)-(?P<token>.+)/$',
        auth_views.password_reset_confirm,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_confirm'),
    url(r'^accounts/password/reset/complete/$',
        auth_views.password_reset_complete,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_complete'),
    url(r'^accounts/password/reset/done/$',
        auth_views.password_reset_done,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_done'),
    url(r'^accounts/profile/', 'weblate.accounts.views.profile', name='profile'),

    url(r'^contact/', 'weblate.accounts.views.contact', name='contact'),
    url(r'^about/$', 'weblate.trans.views.about', name='about'),

    # user pages
    url(r'^user/(?P<user>[^/]+)/', 'weblate.accounts.views.user_page', name='user_page'),

    # the sitemap
    (r'^sitemap\.xml$', 'django.contrib.sitemaps.views.index', {'sitemaps': sitemaps}),
    (r'^sitemap-(?P<section>.+)\.xml$', 'django.contrib.sitemaps.views.sitemap', {'sitemaps': sitemaps}),

    # Media files
    url(r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT}),
)
