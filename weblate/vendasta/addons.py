# -*- coding: utf-8 -*-
import os

import requests

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_POST_COMMIT
from weblate.logger import LOGGER
from weblate.utils.requests import request


class NotifyLexicon(BaseAddon):
    """Triggers on translation commit and component update."""

    events = (
        EVENT_COMPONENT_UPDATE,
        EVENT_POST_COMMIT,
    )
    name = "weblate.vendasta.notifylexicon"
    verbose = "Notify Lexicon"
    description = "When this component sees changes to a translation, notify Lexicon"
    lexicon_url_template = (
        "https://lexicon-{env}.apigateway.co/update-translation"
        "?componentName={component_name}&languageCode={language_code}"
    )

    def component_update(self, component):
        """Notify Lexicon after updating component from vcs."""
        self.notify_lexicon(component)

    def post_commit(self, component, translation=None):
        """Notify Lexicon after committing changes."""
        self.notify_lexicon(component)

    def notify_lexicon(self, component):
        component_name = "{}/{}".format(component.project.slug, component.slug)

        for translation in component.translation_set.iterator():
            for env in ("demo", "prod"):
                language_code = translation.language.code
                url = self.lexicon_url_template.format(
                    env=env, component_name=component_name, language_code=language_code,
                )
                response = request(
                    "get",
                    url,
                    headers={
                        "Authorization": "Token {}".format(
                            os.environ.get("WEBLATE_ADMIN_API_TOKEN")
                        )
                    },
                )
                if response.status_code != requests.codes.ok:
                    LOGGER.error(
                        "Unable to notify lexicon of changes to (%s, %s)",
                        component_name,
                        language_code,
                    )
