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
import json
import os
from uuid import uuid4

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_DAILY, EVENT_POST_COMMIT, EVENT_POST_UPDATE
from weblate.addons.forms import CDNJSForm
from weblate.addons.tasks import cdn_parse_html
from weblate.utils.state import STATE_TRANSLATED


class CDNJSAddon(BaseAddon):
    events = (EVENT_DAILY, EVENT_POST_COMMIT, EVENT_POST_UPDATE)
    name = "weblate.cdn.cdnjs"
    verbose = _("JavaScript localization CDN")
    description = _(
        "Publishes translations into content delivery network "
        "for use in JavaScript or HTML localization."
    )

    settings_form = CDNJSForm
    icon = "cloud-upload.svg"
    stay_on_create = True

    @classmethod
    def create_object(cls, component, **kwargs):
        # Generate UUID for the CDN
        if "state" not in kwargs:
            kwargs["state"] = {"uuid": uuid4().hex}
        return super().create_object(component, **kwargs)

    @classmethod
    def can_install(cls, component, user):
        if (
            not settings.LOCALIZE_CDN_URL
            or not settings.LOCALIZE_CDN_PATH
            or not component.has_template()
            or not component.translation_set.exists()
        ):
            return False
        return super().can_install(component, user)

    def cdn_path(self, filename):
        return os.path.join(
            settings.LOCALIZE_CDN_PATH, self.instance.state["uuid"], filename
        )

    @cached_property
    def cdn_js_url(self):
        return os.path.join(
            settings.LOCALIZE_CDN_URL, self.instance.state["uuid"], "weblate.js"
        )

    def post_commit(self, component):
        # Get list of applicable translations
        threshold = self.instance.configuration["threshold"]
        translations = [
            translation
            for translation in component.translation_set.all()
            if (not translation.is_source or component.intermediate)
            and translation.stats.translated > threshold
        ]

        # Create output directory
        dirname = self.cdn_path("")
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # Generate JavasScript loader
        with open(self.cdn_path("weblate.js"), "w") as handle:
            # The languages variable is included inside quotes to make
            # sure the template is valid JavaScript code as well
            handle.write(
                render_to_string(
                    "addons/js/weblate.js",
                    {
                        "languages": '", "'.join(
                            sorted(
                                translation.language.code
                                for translation in translations
                            )
                        ),
                        "url": os.path.join(
                            settings.LOCALIZE_CDN_URL, self.instance.state["uuid"]
                        ),
                        "cookie_name": self.instance.configuration["cookie_name"],
                        "css_selector": self.instance.configuration["css_selector"],
                    },
                )
            )

        # Generate bilingual JSON files
        for translation in translations:
            with open(
                self.cdn_path(f"{translation.language.code}.json"), "w"
            ) as handle:
                json.dump(
                    {
                        unit.source: unit.target
                        for unit in translation.unit_set.filter(
                            state__gte=STATE_TRANSLATED
                        )
                    },
                    handle,
                )

    def daily(self, component):
        if not self.instance.configuration["files"].strip():
            return
        # Trigger parsing files
        cdn_parse_html.delay(
            self.instance.configuration["files"],
            self.instance.configuration["css_selector"],
            component.id,
        )

    def post_update(self, component, previous_head: str, skip_push: bool):
        self.daily(component)
