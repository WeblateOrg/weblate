# -*- coding: utf-8 -*-
import os

import requests
from concurrent.futures import ThreadPoolExecutor

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_COMMIT, EVENT_UPDATE_REMOTE_BRANCH
from weblate.addons.models import Addon
from weblate.logger import LOGGER
from weblate.trans.models import Component
from weblate.utils.requests import request


LEXICON_UPDATE_TRANSLATION_URL_TEMPLATE = (
    "https://lexicon-{env}.apigateway.co/update-translation?"
    "componentName={component_name}&languageCode={language_code}"
)
LEXICON_UPDATE_COMPONENT_LANGUAGE_URL_TEMPLATE = (
    "https://lexicon-{env}.apigateway.co/update-component-language?"
    "componentName={component_name}&languageCode={language_code}"
)


class NotifyLexicon(BaseAddon):
    """Triggers on translation commit and component update."""

    events = (
        EVENT_POST_COMMIT,
        EVENT_UPDATE_REMOTE_BRANCH,
    )
    name = "weblate.vendasta.notifylexicon"
    verbose = "Notify Lexicon"
    description = "When this component sees changes to a translation, notify Lexicon"

    def update_remote_branch(self, component):
        """Notify Lexicon after updating component from vcs."""
        self.notify_lexicon(component, update_linked_components=True)

    def post_commit(self, component, translation=None):
        """Notify Lexicon after committing changes."""
        self.notify_lexicon(component)

    def notify_lexicon(self, component, update_linked_components=False):
        component_name = "{}/{}".format(component.project.slug, component.slug)

        futures = []
        with ThreadPoolExecutor(max_workers=None) as executor:
            for translation in component.translation_set.iterator():
                language_code = translation.language.code
                for env in ("demo", "prod"):
                    futures.append(
                        executor.submit(
                            _update_translation, env, component_name, language_code
                        )
                    )
                    futures.append(
                        executor.submit(
                            _update_component_language,
                            env,
                            component_name,
                            language_code,
                        )
                    )

        while True:
            if all((future.done() for future in futures)):
                break

        if update_linked_components:
            linked_components = Component.objects.filter(
                repo__exact="weblate://{}".format(component_name)
            ).distinct()
            for linked_component in linked_components:
                if (
                    Addon.objects.filter(name__exact=self.name)
                    .filter(component__name__exact=linked_component.name)
                    .count()
                ):
                    self.notify_lexicon(linked_component)


def _update_translation(env, component_name, language_code):
    """Notify Lexicon that a component has updated."""
    url = LEXICON_UPDATE_TRANSLATION_URL_TEMPLATE.format(
        env=env, component_name=component_name, language_code=language_code,
    )
    _lexicon_get(url)


def _update_component_language(env, component_name, language_code):
    """Notify Lexicon that a language has updated."""
    url = LEXICON_UPDATE_COMPONENT_LANGUAGE_URL_TEMPLATE.format(
        env=env, component_name=component_name, language_code=language_code,
    )
    _lexicon_get(url)


def _lexicon_get(url):
    """Lexicon GET request."""
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
        LOGGER.error("Error during Lexicon request: %s", url)
