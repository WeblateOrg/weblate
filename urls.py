from django.conf.urls.defaults import patterns, include, url
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin

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
    url(r'^accounts/', include('registration.urls')),
    url(r'^accoints/register/$', 'registration.views.register', {
            'form_class': RegistrationForm,
            'extra_context': {'title': _('User registration')}},
            name='registration_register'),
    url(r'^accounts/profile/', 'accounts.views.profile'),

    url(r'^contact/', 'accounts.views.contact'),

    # Media files
    url(r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': './media'}),
)
