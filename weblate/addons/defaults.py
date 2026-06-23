# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DEFAULT_WEBLATE_ADDONS: tuple[str, ...] = (
    "weblate.addons.gettext.GenerateMoAddon",
    "weblate.addons.gettext.UpdateLinguasAddon",
    "weblate.addons.gettext.UpdateConfigureAddon",
    "weblate.addons.gettext.MsgmergeAddon",
    "weblate.addons.gettext.XgettextAddon",
    "weblate.addons.gettext.MesonAddon",
    "weblate.addons.gettext.DjangoAddon",
    "weblate.addons.gettext.SphinxAddon",
    "weblate.addons.gettext.GettextAuthorComments",
    "weblate.addons.cleanup.CleanupAddon",
    "weblate.addons.cleanup.RemoveBlankAddon",
    "weblate.addons.cleanup.ResetAddon",
    "weblate.addons.consistency.LanguageConsistencyAddon",
    "weblate.addons.discovery.DiscoveryAddon",
    "weblate.addons.autotranslate.AutoTranslateAddon",
    "weblate.addons.flags.SourceEditAddon",
    "weblate.addons.flags.TargetEditAddon",
    "weblate.addons.flags.SameEditAddon",
    "weblate.addons.flags.BulkEditAddon",
    "weblate.addons.flags.TargetRepoUpdateAddon",
    "weblate.addons.generate.GenerateFileAddon",
    "weblate.addons.generate.PseudolocaleAddon",
    "weblate.addons.generate.PrefillAddon",
    "weblate.addons.generate.FillReadOnlyAddon",
    "weblate.addons.properties.PropertiesSortAddon",
    "weblate.addons.git.GitSquashAddon",
    "weblate.addons.removal.RemoveComments",
    "weblate.addons.removal.RemoveSuggestions",
    "weblate.addons.resx.ResxUpdateAddon",
    "weblate.addons.cdn.CDNJSAddon",
    "weblate.addons.cdn.CDNFilesAddon",
    "weblate.addons.webhooks.WebhookAddon",
    "weblate.addons.webhooks.SlackWebhookAddon",
    "weblate.addons.fedora_messaging.FedoraMessagingAddon",
)

DEFAULT_LOCALIZE_CDN_URL = None
DEFAULT_LOCALIZE_CDN_PATH = None
DEFAULT_ADDON_ACTIVITY_LOG_EXPIRY = 180

DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT = 5
DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS = 1
DEFAULT_FEDORA_MESSAGING_RETRY_DELAY = 2
