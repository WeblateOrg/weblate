from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'weblate.views.home', name='home'),
    # url(r'^weblate/', include('weblate.foo.urls')),
    url(r'^(?P<project>[^/]*)/$', 'trans.views.show_project'),
    url(r'^(?P<project>[^/]*)/(?P<subproject>[^/]*)/$', 'trans.views.show_subproject'),
    url(r'^(?P<project>[^/]*)/(?P<subproject>[^/]*)/(?P<lang>[^/]*)/$', 'trans.views.show_translation'),

    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
)
