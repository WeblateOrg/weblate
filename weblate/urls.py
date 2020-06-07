#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import re

import django.contrib.sitemaps.views
import django.views.i18n
import django.views.static
from django.conf import settings
from django.conf.urls import include, url
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView, TemplateView

import weblate.accounts.urls
import weblate.accounts.views
import weblate.addons.views
import weblate.api.urls
import weblate.checks.views
import weblate.fonts.views
import weblate.lang.views
import weblate.memory.views
import weblate.screenshots.views
import weblate.trans.views.about
import weblate.trans.views.acl
import weblate.trans.views.agreement
import weblate.trans.views.api
import weblate.trans.views.basic
import weblate.trans.views.charts
import weblate.trans.views.create
import weblate.trans.views.dashboard
import weblate.trans.views.dictionary
import weblate.trans.views.edit
import weblate.trans.views.error
import weblate.trans.views.files
import weblate.trans.views.git
import weblate.trans.views.guide
import weblate.trans.views.hooks
import weblate.trans.views.js
import weblate.trans.views.labels
import weblate.trans.views.lock
import weblate.trans.views.reports
import weblate.trans.views.search
import weblate.trans.views.settings
import weblate.trans.views.source
import weblate.trans.views.widgets
import weblate.wladmin.sites
import weblate.wladmin.views
from weblate.auth.decorators import management_access
from weblate.sitemaps import SITEMAPS
from weblate.trans.feeds import (
    ChangesFeed,
    ComponentChangesFeed,
    LanguageChangesFeed,
    ProjectChangesFeed,
    TranslationChangesFeed,
)
from weblate.trans.views.changes import ChangesCSVView, ChangesView, show_change

# URL regexp for language code
LANGUAGE = r"(?P<lang>[^/]+)"

# URL regexp for project
PROJECT = r"(?P<project>[^/]+)/"

# URL regexp for component
COMPONENT = PROJECT + r"(?P<component>[^/]+)/"

# URL regexp for translations
TRANSLATION = COMPONENT + LANGUAGE + "/"

# URL regexp for project language pages
PROJECT_LANG = PROJECT + LANGUAGE + "/"

# URL regexp used as base for widgets
WIDGET = r"(?P<widget>[^/-]+)-(?P<color>[^/-]+)"

# Widget extension match
EXTENSION = r"(?P<extension>(png|svg))"

# UUID regexp
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"

handler400 = weblate.trans.views.error.bad_request
handler403 = weblate.trans.views.error.denied
handler404 = weblate.trans.views.error.not_found
handler500 = weblate.trans.views.error.server_error

real_patterns = [
    url(r"^$", weblate.trans.views.dashboard.home, name="home"),
    url(r"^projects/$", weblate.trans.views.basic.list_projects, name="projects"),
    url(
        r"^projects/" + PROJECT + "$",
        weblate.trans.views.basic.show_project,
        name="project",
    ),
    # Engagement pages
    url(
        r"^engage/" + PROJECT + "$",
        weblate.trans.views.basic.show_engage,
        name="engage",
    ),
    url(
        r"^engage/" + PROJECT_LANG + "$",
        weblate.trans.views.basic.show_engage,
        name="engage",
    ),
    # Glossary/Dictionary pages
    url(
        r"^dictionaries/" + PROJECT + "$",
        weblate.trans.views.dictionary.show_dictionaries,
        name="show_dictionaries",
    ),
    url(
        r"^dictionaries/" + PROJECT_LANG + "$",
        weblate.trans.views.dictionary.show_dictionary,
        name="show_dictionary",
    ),
    url(
        r"^upload-dictionaries/" + PROJECT_LANG + "$",
        weblate.trans.views.dictionary.upload_dictionary,
        name="upload_dictionary",
    ),
    url(
        r"^delete-dictionaries/" + PROJECT_LANG + "(?P<pk>[0-9]+)/$",
        weblate.trans.views.dictionary.delete_dictionary,
        name="delete_dictionary",
    ),
    url(
        r"^edit-dictionaries/" + PROJECT_LANG + "(?P<pk>[0-9]+)/$",
        weblate.trans.views.dictionary.edit_dictionary,
        name="edit_dictionary",
    ),
    url(
        r"^download-dictionaries/" + PROJECT_LANG + "$",
        weblate.trans.views.dictionary.download_dictionary,
        name="download_dictionary",
    ),
    # Subroject pages
    url(
        r"^projects/" + COMPONENT + "$",
        weblate.trans.views.basic.show_component,
        name="component",
    ),
    url(r"^guide/" + COMPONENT + "$", weblate.trans.views.guide.guide, name="guide"),
    url(
        r"^matrix/" + COMPONENT + "$", weblate.trans.views.source.matrix, name="matrix"
    ),
    url(
        r"^js/matrix/" + COMPONENT + "$",
        weblate.trans.views.source.matrix_load,
        name="matrix-load",
    ),
    url(
        r"^source/(?P<pk>[0-9]+)/context/$",
        weblate.trans.views.source.edit_context,
        name="edit_context",
    ),
    # Translation pages
    url(
        r"^projects/" + TRANSLATION + "$",
        weblate.trans.views.basic.show_translation,
        name="translation",
    ),
    url(
        r"^component-list/(?P<name>[^/]*)/$",
        weblate.trans.views.basic.show_component_list,
        name="component-list",
    ),
    url(
        r"^translate/" + TRANSLATION + "$",
        weblate.trans.views.edit.translate,
        name="translate",
    ),
    url(r"^zen/" + TRANSLATION + "$", weblate.trans.views.edit.zen, name="zen"),
    url(
        r"^download/" + TRANSLATION + "$",
        weblate.trans.views.files.download_translation,
        name="download_translation",
    ),
    url(
        r"^download/" + COMPONENT + "$",
        weblate.trans.views.files.download_component,
        name="download_component",
    ),
    url(
        r"^download/" + PROJECT + "$",
        weblate.trans.views.files.download_project,
        name="download_project",
    ),
    url(
        r"^download-list/(?P<name>[^/]*)/$",
        weblate.trans.views.files.download_component_list,
        name="download_component_list",
    ),
    url(
        r"^download-language/" + LANGUAGE + "/" + PROJECT + "$",
        weblate.trans.views.files.download_lang_project,
        name="download_lang_project",
    ),
    url(
        r"^upload/" + TRANSLATION + "$",
        weblate.trans.views.files.upload_translation,
        name="upload_translation",
    ),
    url(
        r"^new-unit/" + TRANSLATION + "$",
        weblate.trans.views.edit.new_unit,
        name="new-unit",
    ),
    url(
        r"^auto-translate/" + TRANSLATION + "$",
        weblate.trans.views.edit.auto_translation,
        name="auto_translation",
    ),
    url(
        r"^replace/" + PROJECT + "$",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    url(
        r"^replace/" + COMPONENT + "$",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    url(
        r"^replace/" + TRANSLATION + "$",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    url(
        r"^bulk-edit/" + PROJECT + "$",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    url(
        r"^bulk-edit/" + COMPONENT + "$",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    url(
        r"^bulk-edit/" + TRANSLATION + "$",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    url(r"^credits/$", weblate.trans.views.reports.get_credits, name="credits"),
    url(r"^counts/$", weblate.trans.views.reports.get_counts, name="counts"),
    url(
        r"^credits/" + PROJECT + "$",
        weblate.trans.views.reports.get_credits,
        name="credits",
    ),
    url(
        r"^counts/" + PROJECT + "$",
        weblate.trans.views.reports.get_counts,
        name="counts",
    ),
    url(
        r"^credits/" + COMPONENT + "$",
        weblate.trans.views.reports.get_credits,
        name="credits",
    ),
    url(
        r"^counts/" + COMPONENT + "$",
        weblate.trans.views.reports.get_counts,
        name="counts",
    ),
    url(
        r"^new-lang/" + COMPONENT + "$",
        weblate.trans.views.basic.new_language,
        name="new-language",
    ),
    url(
        r"^new-lang/$",
        weblate.lang.views.CreateLanguageView.as_view(),
        name="create-language",
    ),
    url(
        r"^addons/" + COMPONENT + "$",
        weblate.addons.views.AddonList.as_view(),
        name="addons",
    ),
    url(
        r"^addons/" + COMPONENT + "(?P<pk>[0-9]+)/$",
        weblate.addons.views.AddonDetail.as_view(),
        name="addon-detail",
    ),
    url(
        r"^access/" + PROJECT + "$",
        weblate.trans.views.acl.manage_access,
        name="manage-access",
    ),
    url(
        r"^settings/" + PROJECT + "$",
        weblate.trans.views.settings.change_project,
        name="settings",
    ),
    url(
        r"^settings/" + COMPONENT + "$",
        weblate.trans.views.settings.change_component,
        name="settings",
    ),
    url(
        r"^labels/" + PROJECT + "$",
        weblate.trans.views.labels.project_labels,
        name="labels",
    ),
    url(
        r"^labels/" + PROJECT + "edit/(?P<pk>[0-9]+)/$",
        weblate.trans.views.labels.label_edit,
        name="label_edit",
    ),
    url(
        r"^labels/" + PROJECT + "delete/(?P<pk>[0-9]+)/$",
        weblate.trans.views.labels.label_delete,
        name="label_delete",
    ),
    url(
        r"^fonts/" + PROJECT + "$",
        weblate.fonts.views.FontListView.as_view(),
        name="fonts",
    ),
    url(
        r"^fonts/" + PROJECT + "font/(?P<pk>[0-9]+)/$",
        weblate.fonts.views.FontDetailView.as_view(),
        name="font",
    ),
    url(
        r"^fonts/" + PROJECT + "group/(?P<pk>[0-9]+)/$",
        weblate.fonts.views.FontGroupDetailView.as_view(),
        name="font_group",
    ),
    url(
        r"^create/project/$",
        weblate.trans.views.create.CreateProject.as_view(),
        name="create-project",
    ),
    url(
        r"^create/component/$",
        weblate.trans.views.create.CreateComponentSelection.as_view(),
        name="create-component",
    ),
    url(
        r"^create/component/vcs/$",
        weblate.trans.views.create.CreateComponent.as_view(),
        name="create-component-vcs",
    ),
    url(
        r"^create/component/zip/$",
        weblate.trans.views.create.CreateFromZip.as_view(),
        name="create-component-zip",
    ),
    url(
        r"^create/component/doc/$",
        weblate.trans.views.create.CreateFromDoc.as_view(),
        name="create-component-doc",
    ),
    url(
        r"^contributor-agreement/" + COMPONENT + "$",
        weblate.trans.views.agreement.agreement_confirm,
        name="contributor-agreement",
    ),
    url(
        r"^access/" + PROJECT + "add/$",
        weblate.trans.views.acl.add_user,
        name="add-user",
    ),
    url(
        r"^access/" + PROJECT + "invite/$",
        weblate.trans.views.acl.invite_user,
        name="invite-user",
    ),
    url(
        r"^access/" + PROJECT + "remove/$",
        weblate.trans.views.acl.delete_user,
        name="delete-user",
    ),
    url(
        r"^access/" + PROJECT + "resend/$",
        weblate.trans.views.acl.resend_invitation,
        name="resend_invitation",
    ),
    url(
        r"^access/" + PROJECT + "set/$",
        weblate.trans.views.acl.set_groups,
        name="set-groups",
    ),
    # Monthly activity
    url(
        r"^activity/month/$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/month/" + PROJECT + "$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/month/" + COMPONENT + "$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/month/" + TRANSLATION + "$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/language/month/" + LANGUAGE + "/$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/language/month/" + LANGUAGE + "/" + PROJECT + "$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    url(
        r"^activity/user/month/(?P<user>[^/]+)/$",
        weblate.trans.views.charts.monthly_activity,
        name="monthly_activity",
    ),
    # Yearly activity
    url(
        r"^activity/year/$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/year/" + PROJECT + "$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/year/" + COMPONENT + "$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/year/" + TRANSLATION + "$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/language/year/" + LANGUAGE + "/$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/language/year/" + LANGUAGE + "/" + PROJECT + "$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    url(
        r"^activity/user/year/(?P<user>[^/]+)/$",
        weblate.trans.views.charts.yearly_activity,
        name="yearly_activity",
    ),
    # Comments
    url(r"^comment/(?P<pk>[0-9]+)/$", weblate.trans.views.edit.comment, name="comment"),
    url(
        r"^comment/(?P<pk>[0-9]+)/delete/$",
        weblate.trans.views.edit.delete_comment,
        name="delete-comment",
    ),
    url(
        r"^comment/(?P<pk>[0-9]+)/resolve/$",
        weblate.trans.views.edit.resolve_comment,
        name="resolve-comment",
    ),
    # VCS manipulation - commit
    url(
        r"^commit/" + PROJECT + "$",
        weblate.trans.views.git.commit_project,
        name="commit_project",
    ),
    url(
        r"^commit/" + COMPONENT + "$",
        weblate.trans.views.git.commit_component,
        name="commit_component",
    ),
    url(
        r"^commit/" + TRANSLATION + "$",
        weblate.trans.views.git.commit_translation,
        name="commit_translation",
    ),
    # VCS manipulation - update
    url(
        r"^update/" + PROJECT + "$",
        weblate.trans.views.git.update_project,
        name="update_project",
    ),
    url(
        r"^update/" + COMPONENT + "$",
        weblate.trans.views.git.update_component,
        name="update_component",
    ),
    url(
        r"^update/" + TRANSLATION + "$",
        weblate.trans.views.git.update_translation,
        name="update_translation",
    ),
    # VCS manipulation - push
    url(
        r"^push/" + PROJECT + "$",
        weblate.trans.views.git.push_project,
        name="push_project",
    ),
    url(
        r"^push/" + COMPONENT + "$",
        weblate.trans.views.git.push_component,
        name="push_component",
    ),
    url(
        r"^push/" + TRANSLATION + "$",
        weblate.trans.views.git.push_translation,
        name="push_translation",
    ),
    # VCS manipulation - reset
    url(
        r"^reset/" + PROJECT + "$",
        weblate.trans.views.git.reset_project,
        name="reset_project",
    ),
    url(
        r"^reset/" + COMPONENT + "$",
        weblate.trans.views.git.reset_component,
        name="reset_component",
    ),
    url(
        r"^reset/" + TRANSLATION + "$",
        weblate.trans.views.git.reset_translation,
        name="reset_translation",
    ),
    # VCS manipulation - cleanup
    url(
        r"^cleanup/" + PROJECT + "$",
        weblate.trans.views.git.cleanup_project,
        name="cleanup_project",
    ),
    url(
        r"^cleanup/" + COMPONENT + "$",
        weblate.trans.views.git.cleanup_component,
        name="cleanup_component",
    ),
    url(
        r"^cleanup/" + TRANSLATION + "$",
        weblate.trans.views.git.cleanup_translation,
        name="cleanup_translation",
    ),
    url(
        r"^progress/" + COMPONENT + "$",
        weblate.trans.views.settings.component_progress,
        name="component_progress",
    ),
    url(
        r"^progress/" + COMPONENT + "terminate/$",
        weblate.trans.views.settings.component_progress_terminate,
        name="component_progress_terminate",
    ),
    url(
        r"^js/progress/" + COMPONENT + "$",
        weblate.trans.views.settings.component_progress_js,
        name="component_progress_js",
    ),
    # Announcements
    url(
        r"^announcement/" + PROJECT + "$",
        weblate.trans.views.settings.announcement_project,
        name="announcement_project",
    ),
    url(
        r"^announcement/" + COMPONENT + "$",
        weblate.trans.views.settings.announcement_component,
        name="announcement_component",
    ),
    url(
        r"^announcement/" + TRANSLATION + "$",
        weblate.trans.views.settings.announcement_translation,
        name="announcement_translation",
    ),
    url(
        r"^js/announcement/(?P<pk>[0-9]+)/delete/$",
        weblate.trans.views.settings.announcement_delete,
        name="announcement-delete",
    ),
    # VCS manipulation - remove
    url(
        r"^remove/" + PROJECT + "$",
        weblate.trans.views.settings.remove_project,
        name="remove_project",
    ),
    url(
        r"^remove/" + COMPONENT + "$",
        weblate.trans.views.settings.remove_component,
        name="remove_component",
    ),
    url(
        r"^remove/" + TRANSLATION + "$",
        weblate.trans.views.settings.remove_translation,
        name="remove_translation",
    ),
    # Rename/move
    url(
        r"^rename/" + PROJECT + "$",
        weblate.trans.views.settings.rename_project,
        name="rename",
    ),
    url(
        r"^rename/" + COMPONENT + "$",
        weblate.trans.views.settings.rename_component,
        name="rename",
    ),
    url(
        r"^move/" + COMPONENT + "$",
        weblate.trans.views.settings.move_component,
        name="move",
    ),
    # Locking
    url(
        r"^lock/" + PROJECT + "$",
        weblate.trans.views.lock.lock_project,
        name="lock_project",
    ),
    url(
        r"^unlock/" + PROJECT + "$",
        weblate.trans.views.lock.unlock_project,
        name="unlock_project",
    ),
    url(
        r"^lock/" + COMPONENT + "$",
        weblate.trans.views.lock.lock_component,
        name="lock_component",
    ),
    url(
        r"^unlock/" + COMPONENT + "$",
        weblate.trans.views.lock.unlock_component,
        name="unlock_component",
    ),
    # Screenshots
    url(
        r"^screenshots/" + COMPONENT + "$",
        weblate.screenshots.views.ScreenshotList.as_view(),
        name="screenshots",
    ),
    url(
        r"^screenshot/(?P<pk>[0-9]+)/$",
        weblate.screenshots.views.ScreenshotDetail.as_view(),
        name="screenshot",
    ),
    url(
        r"^screenshot/(?P<pk>[0-9]+)/delete/$",
        weblate.screenshots.views.delete_screenshot,
        name="screenshot-delete",
    ),
    url(
        r"^screenshot/(?P<pk>[0-9]+)/remove/$",
        weblate.screenshots.views.remove_source,
        name="screenshot-remove-source",
    ),
    url(
        r"^js/screenshot/(?P<pk>[0-9]+)/get/$",
        weblate.screenshots.views.get_sources,
        name="screenshot-js-get",
    ),
    url(
        r"^js/screenshot/(?P<pk>[0-9]+)/search/$",
        weblate.screenshots.views.search_source,
        name="screenshot-js-search",
    ),
    url(
        r"^js/screenshot/(?P<pk>[0-9]+)/ocr/$",
        weblate.screenshots.views.ocr_search,
        name="screenshot-js-ocr",
    ),
    url(
        r"^js/screenshot/(?P<pk>[0-9]+)/add/$",
        weblate.screenshots.views.add_source,
        name="screenshot-js-add",
    ),
    # Translation memory
    url(r"^memory/$", weblate.memory.views.MemoryView.as_view(), name="memory"),
    url(
        r"^memory/delete/$",
        weblate.memory.views.DeleteView.as_view(),
        name="memory-delete",
    ),
    url(
        r"^memory/upload/$",
        weblate.memory.views.UploadView.as_view(),
        name="memory-upload",
    ),
    url(
        r"^memory/download/$",
        weblate.memory.views.DownloadView.as_view(),
        name="memory-download",
    ),
    url(
        r"^(?P<manage>manage)/memory/$",
        management_access(weblate.memory.views.MemoryView.as_view()),
        name="memory",
    ),
    # This is hacky way of adding second name to a URL
    url(
        r"^manage/memory/$",
        management_access(weblate.memory.views.MemoryView.as_view()),
        name="manage-memory",
    ),
    url(
        r"^(?P<manage>manage)/memory/upload/$",
        management_access(weblate.memory.views.UploadView.as_view()),
        name="memory-upload",
    ),
    url(
        r"^(?P<manage>manage)/memory/delete/$",
        management_access(weblate.memory.views.DeleteView.as_view()),
        name="memory-delete",
    ),
    url(
        r"^(?P<manage>manage)/memory/download/$",
        management_access(weblate.memory.views.DownloadView.as_view()),
        name="memory-download",
    ),
    url(
        r"^memory/project/" + PROJECT + "$",
        weblate.memory.views.MemoryView.as_view(),
        name="memory",
    ),
    url(
        r"^memory/project/" + PROJECT + "delete/$",
        weblate.memory.views.DeleteView.as_view(),
        name="memory-delete",
    ),
    url(
        r"^memory/project/" + PROJECT + "upload/$",
        weblate.memory.views.UploadView.as_view(),
        name="memory-upload",
    ),
    url(
        r"^memory/project/" + PROJECT + "download/$",
        weblate.memory.views.DownloadView.as_view(),
        name="memory-download",
    ),
    # Languages browsing
    url(r"^languages/$", weblate.lang.views.show_languages, name="languages"),
    url(
        r"^languages/" + LANGUAGE + "/$",
        weblate.lang.views.show_language,
        name="show_language",
    ),
    url(
        r"^edit-language/(?P<pk>[0-9]+)/$",
        weblate.lang.views.EditLanguageView.as_view(),
        name="edit-language",
    ),
    url(
        r"^edit-plural/(?P<pk>[0-9]+)/$",
        weblate.lang.views.EditPluralView.as_view(),
        name="edit-plural",
    ),
    url(
        r"^languages/" + LANGUAGE + "/" + PROJECT + "$",
        weblate.lang.views.show_project,
        name="project-language",
    ),
    # Checks browsing
    url(r"^checks/$", weblate.checks.views.show_checks, name="checks"),
    url(
        r"^checks/(?P<name>[^/]+)/$", weblate.checks.views.show_check, name="show_check"
    ),
    url(
        r"^checks/(?P<name>[^/]+)/" + PROJECT + "$",
        weblate.checks.views.show_check_project,
        name="show_check_project",
    ),
    url(
        r"^checks/(?P<name>[^/]+)/" + COMPONENT + "$",
        weblate.checks.views.show_check_component,
        name="show_check_component",
    ),
    # Changes browsing
    url(r"^changes/$", ChangesView.as_view(), name="changes"),
    url(r"^changes/csv/$", ChangesCSVView.as_view(), name="changes-csv"),
    url(r"^changes/render/(?P<pk>[0-9]+)/$", show_change, name="show_change"),
    # Notification hooks
    url(
        r"^hooks/update/" + COMPONENT + "$",
        weblate.trans.views.hooks.update_component,
        name="hook-component",
    ),
    url(
        r"^hooks/update/" + PROJECT + "$",
        weblate.trans.views.hooks.update_project,
        name="hook-project",
    ),
    url(
        r"^hooks/(?P<service>github|gitlab|bitbucket|pagure|azure|gitea|gitee)/?$",
        weblate.trans.views.hooks.vcs_service_hook,
        name="webhook",
    ),
    # Stats exports
    url(
        r"^exports/stats/" + COMPONENT + "$",
        weblate.trans.views.api.export_stats,
        name="export_stats",
    ),
    url(
        r"^exports/stats/" + PROJECT + "$",
        weblate.trans.views.api.export_stats_project,
        name="export_stats",
    ),
    # RSS exports
    url(r"^exports/rss/$", ChangesFeed(), name="rss"),
    url(
        r"^exports/rss/language/" + LANGUAGE + "/$",
        LanguageChangesFeed(),
        name="rss-language",
    ),
    url(r"^exports/rss/" + PROJECT + "$", ProjectChangesFeed(), name="rss-project"),
    url(
        r"^exports/rss/" + COMPONENT + "$", ComponentChangesFeed(), name="rss-component"
    ),
    url(
        r"^exports/rss/" + TRANSLATION + "$",
        TranslationChangesFeed(),
        name="rss-translation",
    ),
    # Compatibility URLs for Widgets
    url(
        r"^widgets/" + PROJECT + "(?P<widget>[^/]+)/(?P<color>[^/]+)/$",
        weblate.trans.views.widgets.render_widget,
        name="widgets-compat-render-color",
    ),
    url(
        r"^widgets/" + PROJECT + "(?P<widget>[^/]+)/$",
        weblate.trans.views.widgets.render_widget,
        name="widgets-compat-render",
    ),
    url(
        r"^widgets/(?P<project>[^/]+)-"
        + WIDGET
        + "-"
        + LANGUAGE
        + r"\."
        + EXTENSION
        + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image-dash",
    ),
    url(
        r"^widgets/(?P<project>[^/]+)-" + WIDGET + r"\." + EXTENSION + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image-dash",
    ),
    # Engagement widgets
    url(r"^exports/og\.png$", weblate.trans.views.widgets.render_og, name="og-image"),
    url(
        r"^widgets/" + PROJECT + "-/" + WIDGET + r"\." + EXTENSION + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    url(
        r"^widgets/" + PROJECT + LANGUAGE + "/" + WIDGET + r"\." + EXTENSION + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    url(
        r"^widgets/"
        + PROJECT
        + "-/"
        + r"(?P<component>[^/]+)/"
        + WIDGET
        + r"\."
        + EXTENSION
        + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    url(
        r"^widgets/"
        + PROJECT
        + LANGUAGE
        + "/"
        + r"(?P<component>[^/]+)/"
        + WIDGET
        + r"\."
        + EXTENSION
        + r"$",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    url(
        r"^widgets/" + PROJECT + "$",
        weblate.trans.views.widgets.widgets,
        name="widgets",
    ),
    url(r"^widgets/$", RedirectView.as_view(url="/projects/", permanent=True)),
    # Data exports pages
    url(r"^data/$", RedirectView.as_view(url="/projects/", permanent=True)),
    url(
        r"^data/" + PROJECT + "$",
        weblate.trans.views.basic.data_project,
        name="data_project",
    ),
    # AJAX/JS backends
    url(
        r"^js/render-check/(?P<unit_id>[0-9]+)/(?P<check_id>[a-z_-]+)/$",
        weblate.checks.views.render_check,
        name="render-check",
    ),
    url(
        r"^js/ignore-check/(?P<check_id>[0-9]+)/$",
        weblate.trans.views.js.ignore_check,
        name="js-ignore-check",
    ),
    url(
        r"^js/ignore-check/(?P<check_id>[0-9]+)/source/$",
        weblate.trans.views.js.ignore_check_source,
        name="js-ignore-check-source",
    ),
    url(
        r"^js/task/(?P<task_id>" + UUID + ")/$",
        weblate.trans.views.js.task_progress,
        name="js_task_progress",
    ),
    url(
        r"^js/i18n/$",
        cache_page(3600)(
            vary_on_cookie(
                django.views.i18n.JavaScriptCatalog.as_view(packages=["weblate"])
            )
        ),
        name="js-catalog",
    ),
    url(r"^js/matomo/$", weblate.trans.views.js.matomo, name="js-matomo"),
    url(
        r"^js/mt-services/$", weblate.trans.views.js.mt_services, name="js-mt-services"
    ),
    url(
        r"^js/translate/(?P<service>[^/]+)/(?P<unit_id>[0-9]+)/$",
        weblate.trans.views.js.translate,
        name="js-translate",
    ),
    url(
        r"^js/memory/(?P<unit_id>[0-9]+)/$",
        weblate.trans.views.js.memory,
        name="js-memory",
    ),
    url(
        r"^js/translations/(?P<unit_id>[0-9]+)/$",
        weblate.trans.views.js.get_unit_translations,
        name="js-unit-translations",
    ),
    url(
        r"^js/git/" + PROJECT + "$",
        weblate.trans.views.js.git_status_project,
        name="git_status_project",
    ),
    url(
        r"^js/git/" + COMPONENT + "$",
        weblate.trans.views.js.git_status_component,
        name="git_status_component",
    ),
    url(
        r"^js/git/" + TRANSLATION + "$",
        weblate.trans.views.js.git_status_translation,
        name="git_status_translation",
    ),
    url(
        r"^js/zen/" + TRANSLATION + "$",
        weblate.trans.views.edit.load_zen,
        name="load_zen",
    ),
    url(
        r"^js/save-zen/" + TRANSLATION + "$",
        weblate.trans.views.edit.save_zen,
        name="save_zen",
    ),
    # Admin interface
    url(
        r"^admin/",
        include(
            (weblate.wladmin.sites.SITE.urls, "weblate.wladmin"), namespace="admin"
        ),
    ),
    # Weblate management interface
    url(r"^manage/$", weblate.wladmin.views.manage, name="manage"),
    url(r"^manage/tools/$", weblate.wladmin.views.tools, name="manage-tools"),
    url(r"^manage/users/$", weblate.wladmin.views.users, name="manage-users"),
    url(r"^manage/activate/$", weblate.wladmin.views.activate, name="manage-activate"),
    url(r"^manage/alerts/$", weblate.wladmin.views.alerts, name="manage-alerts"),
    url(r"^manage/repos/$", weblate.wladmin.views.repos, name="manage-repos"),
    url(r"^manage/ssh/$", weblate.wladmin.views.ssh, name="manage-ssh"),
    url(r"^manage/ssh/key/$", weblate.wladmin.views.ssh_key, name="manage-ssh-key"),
    url(r"^manage/backup/$", weblate.wladmin.views.backups, name="manage-backups"),
    url(
        r"^manage/performance/$",
        weblate.wladmin.views.performance,
        name="manage-performance",
    ),
    # Auth
    url(r"^accounts/", include(weblate.accounts.urls)),
    # Auth
    url(r"^api/", include((weblate.api.urls, "weblate.api"), namespace="api")),
    # Static pages
    url(r"^contact/$", weblate.accounts.views.contact, name="contact"),
    url(r"^hosting/$", weblate.accounts.views.hosting, name="hosting"),
    url(r"^about/$", weblate.trans.views.about.AboutView.as_view(), name="about"),
    url(r"^keys/$", weblate.trans.views.about.KeysView.as_view(), name="keys"),
    url(r"^stats/$", weblate.trans.views.about.StatsView.as_view(), name="stats"),
    # User pages
    url(r"^user/(?P<user>[^/]+)/$", weblate.accounts.views.user_page, name="user_page"),
    url(
        r"^user/(?P<user>[^/]+)/suggestions/$",
        weblate.accounts.views.SuggestionView.as_view(),
        name="user_suggestions",
    ),
    # Avatars, 80 pixes used when linked with weblate.org
    url(
        r"^avatar/(?P<size>(24|32|80|128))/(?P<user>[^/]+)\.png$",
        weblate.accounts.views.user_avatar,
        name="user_avatar",
    ),
    # Sitemap
    url(
        r"^sitemap\.xml$",
        cache_page(3600)(django.contrib.sitemaps.views.index),
        {"sitemaps": SITEMAPS, "sitemap_url_name": "sitemap"},
        name="sitemap-index",
    ),
    url(
        r"^sitemap-(?P<section>.+)\.xml$",
        cache_page(3600)(django.contrib.sitemaps.views.sitemap),
        {"sitemaps": SITEMAPS},
        name="sitemap",
    ),
    # Compatibility redirects
    url(
        r"^projects/" + TRANSLATION + "translate/$",
        RedirectView.as_view(
            url="/translate/%(project)s/%(component)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^projects/" + TRANSLATION + "zen/$",
        RedirectView.as_view(
            url="/zen/%(project)s/%(component)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^projects/" + TRANSLATION + "download/$",
        RedirectView.as_view(
            url="/download/%(project)s/%(component)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^projects/" + TRANSLATION + "upload/$",
        RedirectView.as_view(
            url="/upload/%(project)s/%(component)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^projects/" + TRANSLATION + "auto/$",
        RedirectView.as_view(
            url="/auto-translate/%(project)s/%(component)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^dictionaries/" + PROJECT_LANG + "upload/$",
        RedirectView.as_view(
            url="/upload-dictionaries/%(project)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^dictionaries/" + PROJECT_LANG + "delete/$",
        RedirectView.as_view(
            url="/delete-dictionaries/%(project)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^dictionaries/" + PROJECT_LANG + "edit/$",
        RedirectView.as_view(
            url="/edit-dictionaries/%(project)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^dictionaries/" + PROJECT_LANG + "download/$",
        RedirectView.as_view(
            url="/download-dictionaries/%(project)s/%(lang)s/",
            permanent=True,
            query_string=True,
        ),
    ),
    url(
        r"^js/glossary/(?P<unit_id>[0-9]+)/$",
        weblate.trans.views.dictionary.add_dictionary,
        name="js-add-glossary",
    ),
    # Old activity charts
    url(
        r"^activity/html/" + TRANSLATION + "$",
        RedirectView.as_view(
            url="/projects/%(project)s/%(component)s/%(lang)s/#activity", permanent=True
        ),
    ),
    url(
        r"^activity/html/" + COMPONENT + "$",
        RedirectView.as_view(
            url="/projects/%(project)s/%(component)s/#activity", permanent=True
        ),
    ),
    url(
        r"^activity/html/" + PROJECT + "$",
        RedirectView.as_view(url="/projects/%(project)s/#activity", permanent=True),
    ),
    url(
        r"^activity/language/html/" + LANGUAGE + "/$",
        RedirectView.as_view(url="/languages/%(lang)s/#activity", permanent=True),
    ),
    # Site wide search
    url(r"^search/$", weblate.trans.views.search.search, name="search"),
    url(r"^search/" + PROJECT + "$", weblate.trans.views.search.search, name="search"),
    url(
        r"^search/" + COMPONENT + "$", weblate.trans.views.search.search, name="search"
    ),
    url(
        r"^languages/" + LANGUAGE + "/" + PROJECT + "search/$",
        weblate.trans.views.search.search,
        name="search",
    ),
    # Health check
    url(r"^healthz/$", weblate.trans.views.basic.healthz, name="healthz"),
    # Aliases for static files
    url(
        r"^(android-chrome|favicon)-(?P<size>192|512)x(?P=size)\.png$",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-%(size)s.png", permanent=True
        ),
    ),
    url(
        r"^apple-touch-icon\.png$",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-180.png", permanent=True
        ),
    ),
    url(
        r"^(?P<name>favicon\.ico)$",
        RedirectView.as_view(url=settings.STATIC_URL + "%(name)s", permanent=True),
    ),
    url(
        r"^robots\.txt$",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
    url(
        r"^browserconfig\.xml$",
        TemplateView.as_view(
            template_name="browserconfig.xml", content_type="application/xml"
        ),
    ),
    url(
        r"^site\.webmanifest$",
        TemplateView.as_view(
            template_name="site.webmanifest", content_type="application/json"
        ),
    ),
]

if "weblate.billing" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.billing.views

    real_patterns += [
        url(
            r"^invoice/(?P<pk>[0-9]+)/download/$",
            weblate.billing.views.download_invoice,
            name="invoice-download",
        ),
        url(r"^billing/$", weblate.billing.views.overview, name="billing"),
    ]

if "weblate.gitexport" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.gitexport.views

    real_patterns += [
        # Redirect clone from the Weblate project URL
        url(
            r"^projects/"
            + COMPONENT
            + "(?P<path>(info/|git-upload-pack)[a-z0-9_/-]*)$",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        url(
            r"^projects/"
            + COMPONENT[:-1]
            + r"\.git/"
            + "(?P<path>(info/|git-upload-pack)[a-z0-9_/-]*)$",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        # Redirect clone in case user adds .git to the path
        url(
            r"^git/" + COMPONENT[:-1] + r"\.git/" + "(?P<path>[a-z0-9_/-]*)$",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        url(
            r"^git/" + COMPONENT + "(?P<path>[a-z0-9_/-]*)$",
            weblate.gitexport.views.git_export,
            name="git-export",
        ),
    ]

if "weblate.legal" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.legal.views

    real_patterns += [
        url(
            r"^legal/",
            include(("weblate.legal.urls", "weblate.legal"), namespace="legal"),
        ),
        url(
            r"^security\.txt$",
            TemplateView.as_view(
                template_name="security.txt", content_type="text/plain"
            ),
        ),
    ]

if settings.DEBUG:
    real_patterns += [
        url(
            r"^media/(?P<path>.*)$",
            django.views.static.serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import debug_toolbar

    real_patterns += [url(r"^__debug__/", include(debug_toolbar.urls))]

if "wlhosted.integrations" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    from wlhosted.integrations.views import CreateBillingView

    real_patterns += [
        url(r"^create/billing/$", CreateBillingView.as_view(), name="create-billing")
    ]

if "djangosaml2idp" in settings.INSTALLED_APPS:
    real_patterns += [
        url(r"^idp/", include("djangosaml2idp.urls")),
    ]


def get_url_prefix():
    if not settings.URL_PREFIX:
        return ""
    return re.escape(settings.URL_PREFIX.strip("/")) + "/"


urlpatterns = [url(get_url_prefix(), include(real_patterns))]
