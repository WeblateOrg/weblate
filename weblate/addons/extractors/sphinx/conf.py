# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Minimal Sphinx configuration for extraction-only builds."""

project = "Documentation"
extensions: list[str] = []
exclude_patterns: list[str] = ["_build", "locales"]
