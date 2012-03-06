from django.conf.urls.defaults import patterns, include, url
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic.simple import direct_to_template

from registration.views import activate
from registration.views import register

from accounts.forms import RegistrationForm

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', 'trans.views.home'),
    url(r'^projects/(?P<project>[^/]*)/$', 'trans.views.show_project'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'trans.views.show_subproject'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'trans.views.show_translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/translate/$', 'trans.views.translate'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/download/$', 'trans.views.download_translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/upload/$', 'trans.views.upload_translation'),

    url(r'^js/get/(?P<checksum>[^/]*)/$', 'trans.views.get_string'),

    # Admin interface
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),

    # Auth
    url(r'^accounts/register/$', register, {
            'form_class': RegistrationForm,
            'extra_context': {'title': _('User registration')}},
            name='weblate_register'),
    url(r'^accounts/register/complete/$',
        direct_to_template,
        {'template': 'registration/registration_complete.html'},
        name='registration_complete'),
    url(r'^accounts/activate/(?P<activation_key>\w+)/$',
        activate,
        name='registration_activate'),
    url(r'^accounts/login/$',
        auth_views.login,
        {'template_name': 'registration/login.html'},
        name='auth_login'),
    url(r'^accounts/logout/$',
        auth_views.logout,
        {'template_name': 'registration/logout.html'},
        name='auth_logout'),
    url(r'^accounts/password/change/$',
        auth_views.password_change,
        name='auth_password_change'),
    url(r'^accounts/password/change/done/$',
        auth_views.password_change_done,
        name='auth_password_change_done'),
    url(r'^accounts/password/reset/$',
        auth_views.password_reset,
        name='auth_password_reset'),
    url(r'^accounts/password/reset/confirm/(?P<uidb36>[0-9A-Za-z]+)-(?P<token>.+)/$',
        auth_views.password_reset_confirm,
        name='auth_password_reset_confirm'),
    url(r'^accounts/password/reset/complete/$',
        auth_views.password_reset_complete,
        name='auth_password_reset_complete'),
    url(r'^accounts/password/reset/done/$',
        auth_views.password_reset_done,
        name='auth_password_reset_done'),
    url(r'^accounts/profile/', 'accounts.views.profile'),

    url(r'^contact/', 'accounts.views.contact'),

    # Media files
    url(r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': './media'}),
)
