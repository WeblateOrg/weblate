from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', 'trans.views.home'),
    url(r'^projects/(?P<project>[^/]*)/$', 'trans.views.show_project'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'trans.views.show_subproject'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'trans.views.show_translation'),
    url(r'^projects/(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/translate/$', 'trans.views.translate'),

    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
)
