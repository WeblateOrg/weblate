#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import django.contrib.sitemaps.views
import django.views.i18n
import django.views.static
from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control, cache_page
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView, TemplateView

import weblate.accounts.urls
import weblate.accounts.views
import weblate.addons.views
import weblate.api.urls
import weblate.checks.views
import weblate.fonts.views
import weblate.glossary.views
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
import weblate.trans.views.edit
import weblate.trans.views.error
import weblate.trans.views.files
import weblate.trans.views.git
import weblate.trans.views.hooks
import weblate.trans.views.js
import weblate.trans.views.labels
import weblate.trans.views.lock
import weblate.trans.views.reports
import weblate.trans.views.search
import weblate.trans.views.settings
import weblate.trans.views.source
import weblate.trans.views.widgets
import weblate.utils.urls
import weblate.wladmin.sites
import weblate.wladmin.views
from weblate.auth.decorators import management_access
from weblate.configuration.views import CustomCSSView
from weblate.sitemaps import SITEMAPS
from weblate.trans.feeds import (
    ChangesFeed,
    ComponentChangesFeed,
    LanguageChangesFeed,
    ProjectChangesFeed,
    TranslationChangesFeed,
)
from weblate.trans.views.changes import ChangesCSVView, ChangesView, show_change

handler400 = weblate.trans.views.error.bad_request
handler403 = weblate.trans.views.error.denied
handler404 = weblate.trans.views.error.not_found
handler500 = weblate.trans.views.error.server_error

widget_pattern = "<word:widget>-<word:color>.<extension:extension>"

real_patterns = [
    path("", weblate.trans.views.dashboard.home, name="home"),
    path("projects/", weblate.trans.views.basic.list_projects, name="projects"),
    path(
        "projects/<name:project>/",
        weblate.trans.views.basic.show_project,
        name="project",
    ),
    # Engagement pages
    path(
        "engage/<name:project>/",
        weblate.trans.views.basic.show_engage,
        name="engage",
    ),
    path(
        "engage/<name:project>/<name:lang>/",
        weblate.trans.views.basic.show_engage,
        name="engage",
    ),
    # Subroject pages
    path(
        "projects/<name:project>/<name:component>/",
        weblate.trans.views.basic.show_component,
        name="component",
    ),
    path(
        "guide/<name:project>/<name:component>/",
        weblate.trans.views.basic.guide,
        name="guide",
    ),
    path(
        "matrix/<name:project>/<name:component>/",
        weblate.trans.views.source.matrix,
        name="matrix",
    ),
    path(
        "js/matrix/<name:project>/<name:component>/",
        weblate.trans.views.source.matrix_load,
        name="matrix-load",
    ),
    path(
        "source/<int:pk>/context/",
        weblate.trans.views.source.edit_context,
        name="edit_context",
    ),
    # Translation pages
    path(
        "projects/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.basic.show_translation,
        name="translation",
    ),
    path(
        "component-list/<name:name>/",
        weblate.trans.views.basic.show_component_list,
        name="component-list",
    ),
    path(
        "browse/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.browse,
        name="browse",
    ),
    path(
        "translate/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.translate,
        name="translate",
    ),
    path(
        "zen/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.zen,
        name="zen",
    ),
    path(
        "download/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.files.download_translation,
        name="download_translation",
    ),
    path(
        "download/<name:project>/<name:component>/",
        weblate.trans.views.files.download_component,
        name="download_component",
    ),
    path(
        "download/<name:project>/",
        weblate.trans.views.files.download_project,
        name="download_project",
    ),
    path(
        "download-list/<name:name>/",
        weblate.trans.views.files.download_component_list,
        name="download_component_list",
    ),
    path(
        "download-language/<name:lang>/<name:project>/",
        weblate.trans.views.files.download_lang_project,
        name="download_lang_project",
    ),
    path(
        "upload/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.files.upload_translation,
        name="upload_translation",
    ),
    path(
        "unit/<int:unit_id>/delete/",
        weblate.trans.views.edit.delete_unit,
        name="delete-unit",
    ),
    path(
        "new-unit/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.new_unit,
        name="new-unit",
    ),
    path(
        "auto-translate/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.auto_translation,
        name="auto_translation",
    ),
    path(
        "replace/<name:project>/",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    path(
        "replace/<name:project>/<name:component>/",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    path(
        "replace/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    path(
        "bulk-edit/<name:project>/",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    path(
        "bulk-edit/<name:project>/<name:component>/",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    path(
        "bulk-edit/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    path("credits/", weblate.trans.views.reports.get_credits, name="credits"),
    path("counts/", weblate.trans.views.reports.get_counts, name="counts"),
    path(
        "credits/<name:project>/",
        weblate.trans.views.reports.get_credits,
        name="credits",
    ),
    path(
        "counts/<name:project>/",
        weblate.trans.views.reports.get_counts,
        name="counts",
    ),
    path(
        "credits/<name:project>/<name:component>/",
        weblate.trans.views.reports.get_credits,
        name="credits",
    ),
    path(
        "counts/<name:project>/<name:component>/",
        weblate.trans.views.reports.get_counts,
        name="counts",
    ),
    path(
        "new-lang/<name:project>/<name:component>/",
        weblate.trans.views.basic.new_language,
        name="new-language",
    ),
    path(
        "new-lang/",
        weblate.lang.views.CreateLanguageView.as_view(),
        name="create-language",
    ),
    path(
        "addons/<name:project>/<name:component>/",
        weblate.addons.views.AddonList.as_view(),
        name="addons",
    ),
    path(
        "addons/<name:project>/<name:component>/<int:pk>/",
        weblate.addons.views.AddonDetail.as_view(),
        name="addon-detail",
    ),
    path(
        "access/<name:project>/",
        weblate.trans.views.acl.manage_access,
        name="manage-access",
    ),
    path(
        "settings/<name:project>/",
        weblate.trans.views.settings.change_project,
        name="settings",
    ),
    path(
        "settings/<name:project>/<name:component>/",
        weblate.trans.views.settings.change_component,
        name="settings",
    ),
    path(
        "labels/<name:project>/",
        weblate.trans.views.labels.project_labels,
        name="labels",
    ),
    path(
        "labels/<name:project>/edit/<int:pk>/",
        weblate.trans.views.labels.label_edit,
        name="label_edit",
    ),
    path(
        "labels/<name:project>/delete/<int:pk>/",
        weblate.trans.views.labels.label_delete,
        name="label_delete",
    ),
    path(
        "fonts/<name:project>/",
        weblate.fonts.views.FontListView.as_view(),
        name="fonts",
    ),
    path(
        "fonts/<name:project>/font/<int:pk>/",
        weblate.fonts.views.FontDetailView.as_view(),
        name="font",
    ),
    path(
        "fonts/<name:project>/group/<int:pk>/",
        weblate.fonts.views.FontGroupDetailView.as_view(),
        name="font_group",
    ),
    path(
        "create/project/",
        weblate.trans.views.create.CreateProject.as_view(),
        name="create-project",
    ),
    path(
        "create/component/",
        weblate.trans.views.create.CreateComponentSelection.as_view(),
        name="create-component",
    ),
    path(
        "create/component/vcs/",
        weblate.trans.views.create.CreateComponent.as_view(),
        name="create-component-vcs",
    ),
    path(
        "create/component/zip/",
        weblate.trans.views.create.CreateFromZip.as_view(),
        name="create-component-zip",
    ),
    path(
        "create/component/doc/",
        weblate.trans.views.create.CreateFromDoc.as_view(),
        name="create-component-doc",
    ),
    path(
        "contributor-agreement/<name:project>/<name:component>/",
        weblate.trans.views.agreement.agreement_confirm,
        name="contributor-agreement",
    ),
    path(
        "access/<name:project>/add/",
        weblate.trans.views.acl.add_user,
        name="add-user",
    ),
    path(
        "access/<name:project>/invite/",
        weblate.trans.views.acl.invite_user,
        name="invite-user",
    ),
    path(
        "access/<name:project>/remove/",
        weblate.trans.views.acl.delete_user,
        name="delete-user",
    ),
    path(
        "access/<name:project>/resend/",
        weblate.trans.views.acl.resend_invitation,
        name="resend_invitation",
    ),
    path(
        "access/<name:project>/set/",
        weblate.trans.views.acl.set_groups,
        name="set-groups",
    ),
    # Used by weblate.org to reder own activity chart on homepage
    path(
        "activity/month.json",
        weblate.trans.views.charts.monthly_activity_json,
        name="monthly_activity_json",
    ),
    # Comments
    path("comment/<int:pk>/", weblate.trans.views.edit.comment, name="comment"),
    path(
        "comment/<int:pk>/delete/",
        weblate.trans.views.edit.delete_comment,
        name="delete-comment",
    ),
    path(
        "comment/<int:pk>/resolve/",
        weblate.trans.views.edit.resolve_comment,
        name="resolve-comment",
    ),
    # VCS manipulation - commit
    path(
        "commit/<name:project>/",
        weblate.trans.views.git.commit_project,
        name="commit_project",
    ),
    path(
        "commit/<name:project>/<name:component>/",
        weblate.trans.views.git.commit_component,
        name="commit_component",
    ),
    path(
        "commit/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.commit_translation,
        name="commit_translation",
    ),
    # VCS manipulation - update
    path(
        "update/<name:project>/",
        weblate.trans.views.git.update_project,
        name="update_project",
    ),
    path(
        "update/<name:project>/<name:component>/",
        weblate.trans.views.git.update_component,
        name="update_component",
    ),
    path(
        "update/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.update_translation,
        name="update_translation",
    ),
    # VCS manipulation - push
    path(
        "push/<name:project>/",
        weblate.trans.views.git.push_project,
        name="push_project",
    ),
    path(
        "push/<name:project>/<name:component>/",
        weblate.trans.views.git.push_component,
        name="push_component",
    ),
    path(
        "push/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.push_translation,
        name="push_translation",
    ),
    # VCS manipulation - reset
    path(
        "reset/<name:project>/",
        weblate.trans.views.git.reset_project,
        name="reset_project",
    ),
    path(
        "reset/<name:project>/<name:component>/",
        weblate.trans.views.git.reset_component,
        name="reset_component",
    ),
    path(
        "reset/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.reset_translation,
        name="reset_translation",
    ),
    # VCS manipulation - cleanup
    path(
        "cleanup/<name:project>/",
        weblate.trans.views.git.cleanup_project,
        name="cleanup_project",
    ),
    path(
        "cleanup/<name:project>/<name:component>/",
        weblate.trans.views.git.cleanup_component,
        name="cleanup_component",
    ),
    path(
        "cleanup/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.cleanup_translation,
        name="cleanup_translation",
    ),
    # VCS manipulation - force sync
    path(
        "file-sync/<name:project>/",
        weblate.trans.views.git.file_sync_project,
        name="file_sync_project",
    ),
    path(
        "file-sync/<name:project>/<name:component>/",
        weblate.trans.views.git.file_sync_component,
        name="file_sync_component",
    ),
    path(
        "file-sync/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.git.file_sync_translation,
        name="file_sync_translation",
    ),
    path(
        "progress/<name:project>/<name:component>/",
        weblate.trans.views.settings.component_progress,
        name="component_progress",
    ),
    # Announcements
    path(
        "announcement/<name:project>/",
        weblate.trans.views.settings.announcement_project,
        name="announcement_project",
    ),
    path(
        "announcement/<name:project>/<name:component>/",
        weblate.trans.views.settings.announcement_component,
        name="announcement_component",
    ),
    path(
        "announcement/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.settings.announcement_translation,
        name="announcement_translation",
    ),
    path(
        "js/announcement/<int:pk>/delete/",
        weblate.trans.views.settings.announcement_delete,
        name="announcement-delete",
    ),
    # VCS manipulation - remove
    path(
        "remove/<name:project>/",
        weblate.trans.views.settings.remove_project,
        name="remove_project",
    ),
    path(
        "remove/<name:project>/<name:component>/",
        weblate.trans.views.settings.remove_component,
        name="remove_component",
    ),
    path(
        "remove/<name:project>/-/<name:lang>/",
        weblate.trans.views.settings.remove_project_language,
        name="remove-project-language",
    ),
    path(
        "remove/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.settings.remove_translation,
        name="remove_translation",
    ),
    # Rename/move
    path(
        "rename/<name:project>/",
        weblate.trans.views.settings.rename_project,
        name="rename",
    ),
    path(
        "rename/<name:project>/<name:component>/",
        weblate.trans.views.settings.rename_component,
        name="rename",
    ),
    path(
        "move/<name:project>/<name:component>/",
        weblate.trans.views.settings.move_component,
        name="move",
    ),
    # Alerts dismiss
    path(
        "alerts/<name:project>/<name:component>/dismiss/",
        weblate.trans.views.settings.dismiss_alert,
        name="dismiss-alert",
    ),
    # Locking
    path(
        "lock/<name:project>/",
        weblate.trans.views.lock.lock_project,
        name="lock_project",
    ),
    path(
        "unlock/<name:project>/",
        weblate.trans.views.lock.unlock_project,
        name="unlock_project",
    ),
    path(
        "lock/<name:project>/<name:component>/",
        weblate.trans.views.lock.lock_component,
        name="lock_component",
    ),
    path(
        "unlock/<name:project>/<name:component>/",
        weblate.trans.views.lock.unlock_component,
        name="unlock_component",
    ),
    # Screenshots
    path(
        "screenshots/<name:project>/<name:component>/",
        weblate.screenshots.views.ScreenshotList.as_view(),
        name="screenshots",
    ),
    path(
        "screenshot/<int:pk>/",
        weblate.screenshots.views.ScreenshotDetail.as_view(),
        name="screenshot",
    ),
    path(
        "screenshot/<int:pk>/delete/",
        weblate.screenshots.views.delete_screenshot,
        name="screenshot-delete",
    ),
    path(
        "screenshot/<int:pk>/remove/",
        weblate.screenshots.views.remove_source,
        name="screenshot-remove-source",
    ),
    path(
        "js/screenshot/<int:pk>/get/",
        weblate.screenshots.views.get_sources,
        name="screenshot-js-get",
    ),
    path(
        "js/screenshot/<int:pk>/search/",
        weblate.screenshots.views.search_source,
        name="screenshot-js-search",
    ),
    path(
        "js/screenshot/<int:pk>/ocr/",
        weblate.screenshots.views.ocr_search,
        name="screenshot-js-ocr",
    ),
    path(
        "js/screenshot/<int:pk>/add/",
        weblate.screenshots.views.add_source,
        name="screenshot-js-add",
    ),
    # Translation memory
    path("memory/", weblate.memory.views.MemoryView.as_view(), name="memory"),
    path(
        "memory/delete/",
        weblate.memory.views.DeleteView.as_view(),
        name="memory-delete",
    ),
    path(
        "memory/upload/",
        weblate.memory.views.UploadView.as_view(),
        name="memory-upload",
    ),
    path(
        "memory/download/",
        weblate.memory.views.DownloadView.as_view(),
        name="memory-download",
    ),
    path(
        "manage/memory/",
        management_access(weblate.memory.views.MemoryView.as_view()),
        kwargs={"manage": 1},
        name="manage-memory",
    ),
    path(
        "manage/memory/upload/",
        management_access(weblate.memory.views.UploadView.as_view()),
        kwargs={"manage": 1},
        name="manage-memory-upload",
    ),
    path(
        "manage/memory/delete/",
        management_access(weblate.memory.views.DeleteView.as_view()),
        kwargs={"manage": 1},
        name="manage-memory-delete",
    ),
    path(
        "manage/memory/download/",
        management_access(weblate.memory.views.DownloadView.as_view()),
        kwargs={"manage": 1},
        name="manage-memory-download",
    ),
    path(
        "memory/project/<name:project>/",
        weblate.memory.views.MemoryView.as_view(),
        name="memory",
    ),
    path(
        "memory/project/<name:project>/delete/",
        weblate.memory.views.DeleteView.as_view(),
        name="memory-delete",
    ),
    path(
        "memory/project/<name:project>/upload/",
        weblate.memory.views.UploadView.as_view(),
        name="memory-upload",
    ),
    path(
        "memory/project/<name:project>/download/",
        weblate.memory.views.DownloadView.as_view(),
        name="memory-download",
    ),
    # Languages browsing
    path("languages/", weblate.lang.views.show_languages, name="languages"),
    path(
        "languages/<name:lang>/",
        weblate.lang.views.show_language,
        name="show_language",
    ),
    path(
        "edit-language/<int:pk>/",
        weblate.lang.views.EditLanguageView.as_view(),
        name="edit-language",
    ),
    path(
        "edit-plural/<int:pk>/",
        weblate.lang.views.EditPluralView.as_view(),
        name="edit-plural",
    ),
    path(
        "languages/<name:lang>/<name:project>/",
        weblate.lang.views.show_project,
        name="project-language",
    ),
    # Checks browsing
    path("checks/", weblate.checks.views.show_checks, name="checks"),
    path("checks/<name:name>/", weblate.checks.views.show_check, name="show_check"),
    path(
        "checks/<name:name>/<name:project>/",
        weblate.checks.views.show_check_project,
        name="show_check_project",
    ),
    path(
        "checks/<name:name>/<name:project>/<name:component>/",
        weblate.checks.views.show_check_component,
        name="show_check_component",
    ),
    # Changes browsing
    path("changes/", ChangesView.as_view(), name="changes"),
    path("changes/csv/", ChangesCSVView.as_view(), name="changes-csv"),
    path("changes/render/<int:pk>/", show_change, name="show_change"),
    # Notification hooks
    path(
        "hooks/update/<name:project>/<name:component>/",
        weblate.trans.views.hooks.update_component,
        name="hook-component",
    ),
    path(
        "hooks/update/<name:project>/",
        weblate.trans.views.hooks.update_project,
        name="hook-project",
    ),
    path(
        "hooks/<slug:service>/",
        weblate.trans.views.hooks.vcs_service_hook,
        name="webhook",
    ),
    # Compatibility URL with no trailing slash
    path(
        "hooks/<slug:service>",
        weblate.trans.views.hooks.vcs_service_hook,
    ),
    # Stats exports
    path(
        "exports/stats/<name:project>/<name:component>/",
        weblate.trans.views.api.export_stats,
        name="export_stats",
    ),
    path(
        "exports/stats/<name:project>/",
        weblate.trans.views.api.export_stats_project,
        name="export_stats",
    ),
    # RSS exports
    path("exports/rss/", ChangesFeed(), name="rss"),
    path(
        "exports/rss/language/<name:lang>/",
        LanguageChangesFeed(),
        name="rss-language",
    ),
    path("exports/rss/<name:project>/", ProjectChangesFeed(), name="rss-project"),
    path(
        "exports/rss/<name:project>/<name:component>/",
        ComponentChangesFeed(),
        name="rss-component",
    ),
    path(
        "exports/rss/<name:project>/<name:component>/<name:lang>/",
        TranslationChangesFeed(),
        name="rss-translation",
    ),
    # Engagement widgets
    path("exports/og.png", weblate.trans.views.widgets.render_og, name="og-image"),
    path(
        f"widgets/<name:project>/-/{widget_pattern}",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    path(
        f"widgets/<name:project>/<name:lang>/{widget_pattern}",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    path(
        f"widgets/<name:project>/-/<name:component>/{widget_pattern}",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    path(
        f"widgets/<name:project>/<name:lang>/<name:component>/{widget_pattern}",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    path(
        "widgets/<name:project>/",
        weblate.trans.views.widgets.widgets,
        name="widgets",
    ),
    path("widgets/", RedirectView.as_view(url="/projects/", permanent=True)),
    # Data exports pages
    path("data/", RedirectView.as_view(url="/projects/", permanent=True)),
    path(
        "data/<name:project>/",
        weblate.trans.views.basic.data_project,
        name="data_project",
    ),
    # AJAX/JS backends
    path(
        "js/render-check/<int:unit_id>/<name:check_id>/",
        weblate.checks.views.render_check,
        name="render-check",
    ),
    path(
        "js/ignore-check/<int:check_id>/",
        weblate.trans.views.js.ignore_check,
        name="js-ignore-check",
    ),
    path(
        "js/ignore-check/<int:check_id>/source/",
        weblate.trans.views.js.ignore_check_source,
        name="js-ignore-check-source",
    ),
    path(
        "js/i18n/",
        cache_page(3600)(
            vary_on_cookie(
                django.views.i18n.JavaScriptCatalog.as_view(packages=["weblate"])
            )
        ),
        name="js-catalog",
    ),
    path("js/matomo/", weblate.trans.views.js.matomo, name="js-matomo"),
    path(
        "js/translate/<name:service>/<int:unit_id>/",
        weblate.trans.views.js.translate,
        name="js-translate",
    ),
    path(
        "js/memory/<int:unit_id>/",
        weblate.trans.views.js.memory,
        name="js-memory",
    ),
    path(
        "js/translations/<int:unit_id>/",
        weblate.trans.views.js.get_unit_translations,
        name="js-unit-translations",
    ),
    path(
        "js/git/<name:project>/",
        weblate.trans.views.js.git_status_project,
        name="git_status_project",
    ),
    path(
        "js/git/<name:project>/<name:component>/",
        weblate.trans.views.js.git_status_component,
        name="git_status_component",
    ),
    path(
        "js/git/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.js.git_status_translation,
        name="git_status_translation",
    ),
    path(
        "js/zen/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.load_zen,
        name="load_zen",
    ),
    path(
        "js/save-zen/<name:project>/<name:component>/<name:lang>/",
        weblate.trans.views.edit.save_zen,
        name="save_zen",
    ),
    # Glossary add
    path(
        "js/glossary/<int:unit_id>/",
        weblate.glossary.views.add_glossary_term,
        name="js-add-glossary",
    ),
    path(
        "css/custom.css",
        CustomCSSView.as_view(),
        name="css-custom",
    ),
    # Admin interface
    path(
        "admin/",
        include(
            (weblate.wladmin.sites.SITE.urls, "weblate.wladmin"), namespace="admin"
        ),
    ),
    # Weblate management interface
    path("manage/", weblate.wladmin.views.manage, name="manage"),
    path("manage/tools/", weblate.wladmin.views.tools, name="manage-tools"),
    path("manage/users/", weblate.wladmin.views.users, name="manage-users"),
    path(
        "manage/users/check/",
        weblate.wladmin.views.users_check,
        name="manage-users-check",
    ),
    path("manage/activate/", weblate.wladmin.views.activate, name="manage-activate"),
    path("manage/discovery/", weblate.wladmin.views.discovery, name="manage-discovery"),
    path("manage/alerts/", weblate.wladmin.views.alerts, name="manage-alerts"),
    path("manage/repos/", weblate.wladmin.views.repos, name="manage-repos"),
    path("manage/ssh/", weblate.wladmin.views.ssh, name="manage-ssh"),
    path("manage/ssh/key/", weblate.wladmin.views.ssh_key, name="manage-ssh-key"),
    path("manage/backup/", weblate.wladmin.views.backups, name="manage-backups"),
    path(
        "manage/appearance/", weblate.wladmin.views.appearance, name="manage-appearance"
    ),
    path(
        "manage/performance/",
        weblate.wladmin.views.performance,
        name="manage-performance",
    ),
    # Auth
    path("accounts/", include(weblate.accounts.urls)),
    # Auth
    path("api/", include((weblate.api.urls, "weblate.api"), namespace="api")),
    # Static pages
    path("contact/", weblate.accounts.views.contact, name="contact"),
    path("hosting/", weblate.accounts.views.hosting, name="hosting"),
    path("trial/", weblate.accounts.views.trial, name="trial"),
    path("about/", weblate.trans.views.about.AboutView.as_view(), name="about"),
    path("keys/", weblate.trans.views.about.KeysView.as_view(), name="keys"),
    path("stats/", weblate.trans.views.about.StatsView.as_view(), name="stats"),
    # User pages
    path("user/", weblate.accounts.views.UserList.as_view(), name="user_list"),
    path("user/<name:user>/", weblate.accounts.views.user_page, name="user_page"),
    path(
        "user/<name:user>/suggestions/",
        weblate.accounts.views.SuggestionView.as_view(),
        name="user_suggestions",
    ),
    # Avatars
    path(
        "avatar/<int:size>/<name:user>.png",
        weblate.accounts.views.user_avatar,
        name="user_avatar",
    ),
    # Sitemap
    path(
        "sitemap.xml",
        cache_page(3600)(django.contrib.sitemaps.views.index),
        {"sitemaps": SITEMAPS, "sitemap_url_name": "sitemap"},
        name="sitemap-index",
    ),
    path(
        "sitemap-<slug:section>.xml",
        cache_page(3600)(django.contrib.sitemaps.views.sitemap),
        {"sitemaps": SITEMAPS},
        name="sitemap",
    ),
    # Site wide search
    path("search/", weblate.trans.views.search.search, name="search"),
    path("search/<name:project>/", weblate.trans.views.search.search, name="search"),
    path(
        "search/<name:project>/<name:component>/",
        weblate.trans.views.search.search,
        name="search",
    ),
    path(
        "languages/<name:lang>/-/search/",
        weblate.trans.views.search.search,
        name="search",
    ),
    path(
        "languages/<name:lang>/<name:project>/search/",
        weblate.trans.views.search.search,
        name="search",
    ),
    # Health check
    path("healthz/", weblate.trans.views.basic.healthz, name="healthz"),
    # Aliases for static files
    re_path(
        r"^(android-chrome|favicon)-(?P<size>192|512)x(?P=size)\.png$",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-%(size)s.png", permanent=True
        ),
    ),
    path(
        "apple-touch-icon.png",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-180.png", permanent=True
        ),
    ),
    path(
        "favicon.ico",
        RedirectView.as_view(url=settings.STATIC_URL + "favicon.ico", permanent=True),
    ),
    path(
        "robots.txt",
        cache_control(max_age=86400)(
            TemplateView.as_view(template_name="robots.txt", content_type="text/plain")
        ),
    ),
    path(
        "browserconfig.xml",
        cache_control(max_age=86400)(
            TemplateView.as_view(
                template_name="browserconfig.xml", content_type="application/xml"
            )
        ),
    ),
    path(
        "site.webmanifest",
        cache_control(max_age=86400)(
            TemplateView.as_view(
                template_name="site.webmanifest", content_type="application/json"
            )
        ),
    ),
]

# Billing integration
if "weblate.billing" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.billing.views

    real_patterns += [
        path(
            "invoice/<int:pk>/download/",
            weblate.billing.views.download_invoice,
            name="invoice-download",
        ),
        path("billing/", weblate.billing.views.overview, name="billing"),
        path("billing/<int:pk>/", weblate.billing.views.detail, name="billing-detail"),
        path("manage/billing/", weblate.wladmin.views.billing, name="manage-billing"),
    ]

# Git exporter integration
if "weblate.gitexport" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.gitexport.views

    real_patterns += [
        # Redirect clone from the Weblate project URL
        path(
            "projects/<name:project>/<name:component>/<gitpath:path>",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        path(
            "projects/<name:project>/<name:component>.git/<gitpath:path>",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        # Redirect clone in case user adds .git to the path
        path(
            "git/<name:project>/<name:component>.git/<optionalpath:path>",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        # Redirect when cloning on component URL
        path(
            "projects/<name:project>/<name:component>/info/refs",
            RedirectView.as_view(
                url="/git/%(project)s/%(component)s/%(path)s",
                permanent=True,
                query_string=True,
            ),
        ),
        path(
            "git/<name:project>/<name:component>/<optionalpath:path>",
            weblate.gitexport.views.git_export,
            name="git-export",
        ),
    ]

# Legal integartion
if "weblate.legal" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import weblate.legal.views

    real_patterns += [
        path(
            "legal/",
            include(("weblate.legal.urls", "weblate.legal"), namespace="legal"),
        ),
        path(
            "security.txt",
            TemplateView.as_view(
                template_name="security.txt", content_type="text/plain"
            ),
        ),
    ]

# Serving media files in DEBUG mode
if settings.DEBUG:
    real_patterns += [
        path(
            "media/<path:path>",
            django.views.static.serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]

# Django debug toolbar integration
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    import debug_toolbar

    real_patterns += [path("__debug__/", include(debug_toolbar.urls))]

# Hosted Weblate integration
if "wlhosted.integrations" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    from wlhosted.integrations.views import CreateBillingView

    real_patterns += [
        path("create/billing/", CreateBillingView.as_view(), name="create-billing")
    ]

# Django SAML2 Identity Provider
if "djangosaml2idp" in settings.INSTALLED_APPS:
    real_patterns += [
        path("idp/", include("djangosaml2idp.urls")),
    ]

# Handle URL prefix configuration
if not settings.URL_PREFIX:
    urlpatterns = real_patterns
else:
    urlpatterns = [path(settings.URL_PREFIX.strip("/") + "/", include(real_patterns))]
