# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from io import BytesIO

CONTROLCHARS = {
    "\x00",
    "\x01",
    "\x02",
    "\x03",
    "\x04",
    "\x05",
    "\x06",
    "\x07",
    "\x08",
    "\x0b",
    "\x0c",
    "\x0e",
    "\x0f",
    "\x10",
    "\x11",
    "\x12",
    "\x13",
    "\x14",
    "\x15",
    "\x16",
    "\x17",
    "\x18",
    "\x19",
    "\x1a",
    "\x1b",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x1f",
    "\ufffe",
    "\uffff",
}
CONTROLCHARS_TRANS = str.maketrans(dict.fromkeys(CONTROLCHARS))


class NamedBytesIO(BytesIO):
    """StringIO with mode attribute to make ttkit happy."""

    def __init__(self, filename, data) -> None:
        super().__init__(data)
        self.mode = "r"  # type: ignore[misc]
        self.name = filename
