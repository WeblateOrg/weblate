# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.contrib.sitemaps.views
import django.views.i18n
import django.views.static
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control, cache_page
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

import weblate.accounts.urls
import weblate.accounts.views
import weblate.addons.views
import weblate.api.urls
import weblate.auth.views
import weblate.checks.views
import weblate.fonts.views
import weblate.glossary.views
import weblate.lang.views
import weblate.machinery.views
import weblate.memory.views
import weblate.screenshots.views
import weblate.trans.views.about
import weblate.trans.views.acl
import weblate.trans.views.agreement
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
import weblate.wladmin.views
from weblate.auth.decorators import management_access
from weblate.configuration.views import CustomCSSView
from weblate.sitemaps import SITEMAPS
from weblate.trans.feeds import ChangesFeed, LanguageChangesFeed, TranslationChangesFeed
from weblate.trans.views.changes import ChangesCSVView, ChangesView, show_change
from weblate.utils.version import VERSION

handler400 = weblate.trans.views.error.bad_request
handler403 = weblate.trans.views.error.denied
handler404 = weblate.trans.views.error.not_found
handler500 = weblate.trans.views.error.server_error

widget_pattern = "<word:widget>-<word:color>.<extension:extension>"

URL_PREFIX = settings.URL_PREFIX
if URL_PREFIX:
    URL_PREFIX = URL_PREFIX.strip("/") + "/"

real_patterns = [
    path("", weblate.trans.views.dashboard.home, name="home"),
    path("projects/", weblate.trans.views.basic.list_projects, name="projects"),
    # Object display
    path(
        "projects/<object_path:path>/",
        weblate.trans.views.basic.show,
        name="show",
    ),
    # Engagement pages
    path(
        "engage/<object_path:path>/",
        weblate.trans.views.basic.show_engage,
        name="engage",
    ),
    # Component pages
    path(
        "guide/<object_path:path>/",
        weblate.trans.views.basic.guide,
        name="guide",
    ),
    path(
        "matrix/<object_path:path>/",
        weblate.trans.views.source.matrix,
        name="matrix",
    ),
    path(
        "js/matrix/<object_path:path>/",
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
        "component-list/<name:name>/",
        weblate.trans.views.basic.show_component_list,
        name="component-list",
    ),
    path(
        "browse/<object_path:path>/",
        weblate.trans.views.edit.browse,
        name="browse",
    ),
    path(
        "translate/<object_path:path>/",
        weblate.trans.views.edit.translate,
        name="translate",
    ),
    path(
        "zen/<object_path:path>/",
        weblate.trans.views.edit.zen,
        name="zen",
    ),
    path(
        "download/<object_path:path>/",
        weblate.trans.views.files.download,
        name="download",
    ),
    path(
        "download-list/<name:name>/",
        weblate.trans.views.files.download_component_list,
        name="download_component_list",
    ),
    path(
        "upload/<object_path:path>/",
        weblate.trans.views.files.upload,
        name="upload",
    ),
    path(
        "unit/<int:unit_id>/delete/",
        weblate.trans.views.edit.delete_unit,
        name="delete-unit",
    ),
    path(
        "new-unit/<object_path:path>/",
        weblate.trans.views.edit.new_unit,
        name="new-unit",
    ),
    path(
        "auto-translate/<object_path:path>/",
        weblate.trans.views.edit.auto_translation,
        name="auto_translation",
    ),
    path(
        "replace/<object_path:path>/",
        weblate.trans.views.search.search_replace,
        name="replace",
    ),
    path(
        "bulk-edit/<object_path:path>/",
        weblate.trans.views.search.bulk_edit,
        name="bulk-edit",
    ),
    path("credits/", weblate.trans.views.reports.get_credits, name="credits"),
    path("counts/", weblate.trans.views.reports.get_counts, name="counts"),
    path(
        "credits/<object_path:path>/",
        weblate.trans.views.reports.get_credits,
        name="credits",
    ),
    path(
        "counts/<object_path:path>/",
        weblate.trans.views.reports.get_counts,
        name="counts",
    ),
    path(
        "new-lang/<object_path:path>/",
        weblate.trans.views.basic.new_language,
        name="new-language",
    ),
    path(
        "new-lang/",
        weblate.lang.views.CreateLanguageView.as_view(),
        name="create-language",
    ),
    path(
        "addons/<object_path:path>/",
        weblate.addons.views.AddonList.as_view(),
        name="addons",
    ),
    path(
        "addon/<int:pk>/",
        weblate.addons.views.AddonDetail.as_view(),
        name="addon-detail",
    ),
    path(
        "addon/<int:pk>/logs/",
        weblate.addons.views.AddonLogs.as_view(),
        name="addon-logs",
    ),
    path(
        "access/<name:project>/",
        weblate.trans.views.acl.manage_access,
        name="manage-access",
    ),
    path(
        "settings/<object_path:path>/",
        weblate.trans.views.settings.change,
        name="settings",
    ),
    path(
        "backups/<name:project>/",
        weblate.trans.views.settings.BackupsView.as_view(),
        name="backups",
    ),
    path(
        "backups/<name:project>/<name:backup>",
        weblate.trans.views.settings.BackupsDownloadView.as_view(),
        name="backups-download",
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
        "create/project/import/",
        weblate.trans.views.create.ImportProject.as_view(),
        name="create-project-import",
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
        "contributor-agreement/<object_path:path>",
        weblate.trans.views.agreement.agreement_confirm,
        name="contributor-agreement",
    ),
    path(
        "access/<name:project>/add/",
        weblate.trans.views.acl.add_user,
        name="add-user",
    ),
    path(
        "access/<name:project>/block/",
        weblate.trans.views.acl.block_user,
        name="block-user",
    ),
    path(
        "access/<name:project>/unblock/",
        weblate.trans.views.acl.unblock_user,
        name="unblock-user",
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
        "access/<name:project>/set/",
        weblate.trans.views.acl.set_groups,
        name="set-groups",
    ),
    path(
        "access/<name:project>/team/create/",
        weblate.trans.views.acl.create_group,
        name="create-project-group",
    ),
    path(
        "token/<name:project>/create/",
        weblate.trans.views.acl.create_token,
        name="create-project-token",
    ),
    # Used by weblate.org to render own activity chart on homepage
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
        "commit/<object_path:path>/",
        weblate.trans.views.git.commit,
        name="commit",
    ),
    # VCS manipulation - update
    path(
        "update/<object_path:path>/",
        weblate.trans.views.git.update,
        name="update",
    ),
    # VCS manipulation - push
    path(
        "push/<object_path:path>/",
        weblate.trans.views.git.push,
        name="push",
    ),
    # VCS manipulation - reset
    path(
        "reset/<object_path:path>/",
        weblate.trans.views.git.reset,
        name="reset",
    ),
    # VCS manipulation - cleanup
    path(
        "cleanup/<object_path:path>/",
        weblate.trans.views.git.cleanup,
        name="cleanup",
    ),
    # VCS manipulation - force sync
    path(
        "file-sync/<object_path:path>/",
        weblate.trans.views.git.file_sync,
        name="file_sync",
    ),
    # VCS manipulation - force scan
    path(
        "file-scan/<object_path:path>/",
        weblate.trans.views.git.file_scan,
        name="file_scan",
    ),
    path(
        "progress/<object_path:path>/",
        weblate.trans.views.settings.show_progress,
        name="show_progress",
    ),
    # Announcements
    path(
        "announcement/<object_path:path>/",
        weblate.trans.views.settings.announcement,
        name="announcement",
    ),
    path(
        "js/announcement/<int:pk>/delete/",
        weblate.trans.views.settings.announcement_delete,
        name="announcement-delete",
    ),
    # VCS manipulation - remove
    path(
        "remove/<object_path:path>/",
        weblate.trans.views.settings.remove,
        name="remove",
    ),
    # Project renaming and moving
    path(
        "rename/<object_path:path>/", weblate.trans.views.settings.rename, name="rename"
    ),
    path(
        "category/add/<object_path:path>/",
        weblate.trans.views.settings.add_category,
        name="add-category",
    ),
    # Alerts dismiss
    path(
        "alerts/<object_path:path>/dismiss/",
        weblate.trans.views.settings.dismiss_alert,
        name="dismiss-alert",
    ),
    # Locking
    path(
        "lock/<object_path:path>/",
        weblate.trans.views.lock.lock,
        name="lock",
    ),
    path(
        "unlock/<object_path:path>/",
        weblate.trans.views.lock.unlock,
        name="unlock",
    ),
    # Screenshots
    path(
        "screenshots/<object_path:path>/",
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
        "memory/rebuild/",
        weblate.memory.views.RebuildView.as_view(),
        name="memory-rebuild",
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
        "manage/memory/rebuild/",
        management_access(weblate.memory.views.RebuildView.as_view()),
        kwargs={"manage": 1},
        name="manage-memory-rebuild",
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
        "memory/project/<name:project>/rebuild/",
        weblate.memory.views.RebuildView.as_view(),
        name="memory-rebuild",
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
    # Machinery
    path(
        "manage/machinery/",
        management_access(weblate.machinery.views.ListMachineryGlobalView.as_view()),
        name="manage-machinery",
    ),
    path(
        "manage/machinery/<name:machinery>/",
        management_access(weblate.machinery.views.EditMachineryGlobalView.as_view()),
        name="machinery-edit",
    ),
    path(
        "machinery/<name:project>/",
        weblate.machinery.views.ListMachineryProjectView.as_view(),
        name="machinery-list",
    ),
    path(
        "machinery/<name:project>/<name:machinery>/",
        weblate.machinery.views.EditMachineryProjectView.as_view(),
        name="machinery-edit",
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
        weblate.trans.views.basic.ProjectLanguageRedirectView.as_view(),
        name="project-language-redirect",
    ),
    path(
        "languages/<name:lang>/<name:project>/search/",
        weblate.trans.views.basic.ProjectLanguageRedirectView.as_view(
            pattern_name="search",
        ),
        name="project-language-search-redirect",
    ),
    # Checks browsing
    path("checks/", weblate.checks.views.CheckList.as_view(), name="checks"),
    path(
        "checks/<name:name>/", weblate.checks.views.CheckList.as_view(), name="checks"
    ),
    path(
        "checks/-/<object_path:path>/",
        weblate.checks.views.CheckList.as_view(),
        name="checks",
    ),
    path(
        "checks/<name:name>/<object_path:path>/",
        weblate.checks.views.CheckList.as_view(),
        name="checks",
    ),
    # Changes browsing
    path("changes/", ChangesView.as_view(), name="changes"),
    path("changes/browse/<object_path:path>/", ChangesView.as_view(), name="changes"),
    path("changes/csv/", ChangesCSVView.as_view(), name="changes-csv"),
    path(
        "changes/csv/<object_path:path>/", ChangesCSVView.as_view(), name="changes-csv"
    ),
    path("changes/render/<int:pk>/", show_change, name="show_change"),
    # Notification hooks
    path(
        "hooks/update/<object_path:path>",
        weblate.trans.views.hooks.update,
        name="update-hook",
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
    # RSS exports
    path("exports/rss/", ChangesFeed(), name="rss"),
    path(
        "exports/rss/language/<name:lang>/",
        LanguageChangesFeed(),
        name="rss-language",
    ),
    path("exports/rss/<object_path:path>/", TranslationChangesFeed(), name="rss"),
    # Engagement widgets
    path("exports/og.png", weblate.trans.views.widgets.render_og, name="og-image"),
    path(
        f"widgets/<name:project>/-/{widget_pattern}",
        weblate.trans.views.widgets.WidgetRedirectView.as_view(),
    ),
    path(
        f"widgets/<name:project>/<name:lang>/{widget_pattern}",
        weblate.trans.views.widgets.WidgetRedirectView.as_view(),
    ),
    path(
        f"widgets/<name:project>/-/<name:component>/{widget_pattern}",
        weblate.trans.views.widgets.WidgetRedirectView.as_view(),
    ),
    path(
        f"widgets/<name:project>/<name:lang>/<name:component>/{widget_pattern}",
        weblate.trans.views.widgets.WidgetRedirectView.as_view(),
    ),
    path(
        f"widget/<object_path:path>/{widget_pattern}",
        weblate.trans.views.widgets.render_widget,
        name="widget-image",
    ),
    path(
        "widgets/<object_path:path>/",
        weblate.trans.views.widgets.widgets,
        name="widgets",
    ),
    path(
        "widgets/",
        RedirectView.as_view(
            pattern_name="projects", permanent=True, query_string=True
        ),
    ),
    # Data exports pages
    path(
        "data/",
        RedirectView.as_view(
            pattern_name="projects", permanent=True, query_string=True
        ),
    ),
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
        cache_page(3600, key_prefix=VERSION)(
            vary_on_cookie(
                django.views.i18n.JavaScriptCatalog.as_view(packages=["weblate"])
            )
        ),
        name="js-catalog",
    ),
    path("js/matomo/", weblate.trans.views.js.matomo, name="js-matomo"),
    path(
        "js/translate/<name:service>/<int:unit_id>/",
        weblate.machinery.views.translate,
        name="js-translate",
    ),
    path(
        "js/memory/<int:unit_id>/",
        weblate.machinery.views.memory,
        name="js-memory",
    ),
    path(
        "js/translations/<int:unit_id>/",
        weblate.trans.views.js.get_unit_translations,
        name="js-unit-translations",
    ),
    path(
        "js/git/<object_path:path>/",
        weblate.trans.views.js.git_status,
        name="git_status",
    ),
    path(
        "js/zen/<object_path:path>/",
        weblate.trans.views.edit.load_zen,
        name="load_zen",
    ),
    path(
        "js/save-zen/<object_path:path>/",
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
    path("admin/", admin.site.urls),
    # Weblate management interface
    path("manage/", weblate.wladmin.views.manage, name="manage"),
    path("manage/support/", weblate.wladmin.views.support_form, name="manage-support"),
    path(
        "manage/addons/", weblate.addons.views.AddonList.as_view(), name="manage-addons"
    ),
    path("manage/tools/", weblate.wladmin.views.tools, name="manage-tools"),
    path(
        "manage/users/",
        weblate.wladmin.views.AdminUserList.as_view(),
        name="manage-users",
    ),
    path(
        "manage/teams/",
        weblate.wladmin.views.TeamListView.as_view(),
        name="manage-teams",
    ),
    path(
        "teams/<int:pk>/",
        weblate.auth.views.TeamUpdateView.as_view(),
        name="team",
    ),
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
    # Accounts
    path("accounts/", include(weblate.accounts.urls)),
    # Auth
    path("api/", include((weblate.api.urls, "weblate.api"), namespace="api")),
    # OpenAPI schema
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    # API documentation
    path(
        "api/docs/", SpectacularRedocView.as_view(url_name="api-schema"), name="redoc"
    ),
    # Static pages
    path("contact/", weblate.accounts.views.contact, name="contact"),
    path("hosting/", weblate.accounts.views.hosting, name="hosting"),
    path("trial/", weblate.accounts.views.trial, name="trial"),
    path("about/", weblate.trans.views.about.AboutView.as_view(), name="about"),
    path("donate/", weblate.trans.views.about.DonateView.as_view(), name="donate"),
    path("keys/", weblate.trans.views.about.KeysView.as_view(), name="keys"),
    path("stats/", weblate.trans.views.about.StatsView.as_view(), name="stats"),
    # User pages
    path("user/", weblate.accounts.views.UserList.as_view(), name="user_list"),
    path(
        "user/<name:user>/", weblate.accounts.views.UserPage.as_view(), name="user_page"
    ),
    path(
        "user/<name:user>/contributions/",
        weblate.accounts.views.user_contributions,
        name="user_contributions",
    ),
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
        cache_page(3600, key_prefix=VERSION)(django.contrib.sitemaps.views.index),
        {"sitemaps": SITEMAPS, "sitemap_url_name": "sitemap"},
        name="sitemap-index",
    ),
    path(
        "sitemap-<slug:section>.xml",
        cache_page(3600, key_prefix=VERSION)(django.contrib.sitemaps.views.sitemap),
        {"sitemaps": SITEMAPS},
        name="sitemap",
    ),
    # Site wide search
    path("search/", weblate.trans.views.search.search, name="search"),
    path(
        "search/<object_path:path>/", weblate.trans.views.search.search, name="search"
    ),
    # Health check
    path("healthz/", weblate.trans.views.basic.healthz, name="healthz"),
    # Aliases for static files
    re_path(
        r"^(android-chrome|favicon)-(?P<size>192|512)x(?P=size)\.png$",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-%(size)s.png",
            permanent=True,
        ),
    ),
    path(
        "apple-touch-icon.png",
        RedirectView.as_view(
            url=settings.STATIC_URL + "weblate-180.png",
            permanent=True,
        ),
    ),
    path(
        "favicon.ico",
        RedirectView.as_view(
            url=settings.STATIC_URL + "favicon.ico",
            permanent=True,
        ),
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
    # Redirects for .well-known
    path(
        ".well-known/change-password",
        RedirectView.as_view(pattern_name="password", permanent=True),
    ),
]

# Billing integration
if "weblate.billing" in settings.INSTALLED_APPS:
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
    import weblate.gitexport.views

    real_patterns += [
        # Redirect clone from the Weblate project URL
        path(
            "projects/<object_path:path>.git/<git_path:git_request>",
            RedirectView.as_view(
                pattern_name="git-export",
                permanent=True,
                query_string=True,
            ),
        ),
        path(
            "projects/<object_path:path>/<git_path:git_request>",
            RedirectView.as_view(
                pattern_name="git-export",
                permanent=True,
                query_string=True,
            ),
        ),
        # Redirect clone in case user adds .git to the path
        path(
            "git/<object_path:path>.git/<git_path:git_request>",
            RedirectView.as_view(
                pattern_name="git-export",
                permanent=True,
                query_string=True,
            ),
        ),
        # Redirect accessing Git URL with a browser
        path(
            "git/<object_path:path>.git/",
            RedirectView.as_view(
                pattern_name="show",
                permanent=True,
                query_string=True,
            ),
        ),
        path(
            "git/<object_path:path>/",
            RedirectView.as_view(
                pattern_name="show",
                permanent=True,
                query_string=True,
            ),
        ),
        # Actual git server
        path(
            "git/<object_path:path>/<git_path:git_request>",
            weblate.gitexport.views.git_export,
            name="git-export",
        ),
    ]

# Legal integartion
if "weblate.legal" in settings.INSTALLED_APPS:
    real_patterns.extend(
        (
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
        )
    )

# Serving media files in DEBUG mode
if settings.DEBUG:
    real_patterns.append(
        path(
            "media/<path:path>",
            django.views.static.serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    )

# Django debug toolbar integration
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    real_patterns.append(
        path("__debug__/", include("debug_toolbar.urls")),
    )

# Hosted Weblate integration
if "wlhosted.integrations" in settings.INSTALLED_APPS:
    from wlhosted.integrations.views import CreateBillingView

    real_patterns.append(
        path("create/billing/", CreateBillingView.as_view(), name="create-billing"),
    )

# Django SAML2 Identity Provider
if "djangosaml2idp" in settings.INSTALLED_APPS:
    real_patterns.append(
        path("idp/", include("djangosaml2idp.urls")),
    )

# Handle URL prefix configuration
if not URL_PREFIX:
    urlpatterns = real_patterns
else:
    urlpatterns = [path(URL_PREFIX, include(real_patterns))]
