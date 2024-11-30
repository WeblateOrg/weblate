# Copyright © Loïc LEUILLIOT <loic.leuilliot@gmail.com>
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.utils.translation import gettext_lazy
from translate.storage.lisa import LISAfile

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import XMLCustomizeForm

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.formats.base import TranslationFormat
    from weblate.trans.forms import Component, Translation


class XMLCustomizeAddon(StoreBaseAddon):
    """Class providing XML formatting changes as a component AddOn."""

    name = "weblate.xml.customize"
    verbose = gettext_lazy("Customize XML output")
    description = gettext_lazy(
        "Allows adjusting XML output behavior, for example closing tags."
    )
    settings_form = XMLCustomizeForm

    @classmethod
    def can_install(cls, component: Component, user: User | None):  # noqa: ARG003
        """Event handler to determine if add-on is compatible with component."""
        # component are attached to a file format which is defined by a loader
        # we want to provide this package only for component using LISAfile as loader
        if not hasattr(component.file_format_cls, "get_class"):
            # Non translate-toolkit based formats
            return False
        format_class = component.file_format_cls.get_class()
        return format_class is not None and issubclass(format_class, LISAfile)

    def store_post_load(
        self, translation: Translation, store: TranslationFormat
    ) -> None:
        """Event handler once component formatter has been loaded."""
        config = self.instance.configuration
        cast("LISAfile", store.store).XMLSelfClosingTags = not config.get(
            "closing_tags", True
        )
