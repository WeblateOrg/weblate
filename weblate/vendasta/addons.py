# -*- coding: utf-8 -*-
import os

import requests

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_COMMIT, EVENT_UPDATE_REMOTE_BRANCH
from weblate.addons.models import Addon
from weblate.logger import LOGGER
from weblate.trans.models import Component
from weblate.utils.requests import request


class NotifyLexicon(BaseAddon):
    """Triggers on translation commit and component update."""

    events = (
        EVENT_POST_COMMIT,
        EVENT_UPDATE_REMOTE_BRANCH,
    )
    name = "weblate.vendasta.notifylexicon"
    verbose = "Notify Lexicon"
    description = "When this component sees changes to a translation, notify Lexicon"
    lexicon_url_template = (
        "https://lexicon-{env}.apigateway.co/update-translation"
        "?componentName={component_name}&languageCode={language_code}"
    )

    def update_remote_branch(self, component):
        """Notify Lexicon after updating component from vcs."""
        self.notify_lexicon(component, update_linked_components=True)

    def post_commit(self, component, translation=None):
        """Notify Lexicon after committing changes."""
        self.notify_lexicon(component)

    def notify_lexicon(self, component, update_linked_components=False):
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

        if update_linked_components:
            linked_components = Component.objects.filter(
                repo__exact="weblate://{}".format(component_name)
            ).distinct()

            for linked_component in linked_components:
                LOGGER.info(
                    "######## Found linked component name %s", linked_component.name
                )
                if (
                    Addon.objects.filter(name__exact="Notify Lexicon")
                    .filter(component__name__exact=linked_component.name)
                    .count()
                ):
                    LOGGER.info("######## Notifying lexicon")
                    self.notify_lexicon(linked_component)
                else:
                    LOGGER.info("######## Not notifying lexicon")
            if linked_components.count() == 0:
                LOGGER.info("######## Found zero linked components")
