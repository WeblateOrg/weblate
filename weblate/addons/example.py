# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent

if TYPE_CHECKING:
    from weblate.addons.base import CompatDict


class ExampleAddon(BaseAddon):
    # Filter for compatible components, every key is
    # matched against property of component
    compat: ClassVar[CompatDict] = {
        "file_format": {"po", "po-mono"},
    }
    # List of events add-on should receive
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    # Add-on unique identifier
    name = "weblate.example.example"
    # Verbose name shown in the user interface
    verbose = gettext_lazy("Example add-on")
    # Detailed add-on description
    description = gettext_lazy("This add-on does nothing it is just an example.")

    # Callback to implement custom behavior
    def pre_commit(self, translation, author: str, store_hash: bool) -> None:
        return
