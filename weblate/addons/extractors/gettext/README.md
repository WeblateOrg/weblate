<!--
Copyright © Michal Čihař <michal@weblate.org>
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Gettext ITS rules

These upstream rules are used by the xgettext and Meson add-ons through
GETTEXTDATADIRS. Keep each .its file together with its .loc file. Do not change
upstream selection semantics locally; update from upstream and run the mixed
extraction tests when refreshing a rule pair.

<!-- BEGIN GENERATED ITS SOURCES -->

| Files | Upstream version | Source |
| --- | --- | --- |
| polkit.* | 127 | <https://github.com/polkit-org/polkit/tree/127/gettext/its> |
| metainfo.* | v1.2.0 | <https://github.com/ximion/appstream/tree/v1.2.0/data/its> |
| gschema.* | 2.90.0 | <https://github.com/GNOME/glib/tree/2.90.0/gio> |
| gtkbuilder.* | 3.24.52 | <https://github.com/GNOME/gtk/tree/3.24.52/gtk> |
| shared-mime-info.* | 2.5.1 | <https://gitlab.freedesktop.org/xdg/shared-mime-info/-/tree/2.5.1/data/its> |

<!-- END GENERATED ITS SOURCES -->

Copyright attribution and licensing are recorded in the repository's REUSE.toml;
full license texts are kept in LICENSES/. Both are included in source distributions
and wheel license metadata. AppStream also includes notices in the rule files.

## Updating

Run `uv run --only-group scripts scripts/update-gettext-rules.py` from a checkout to download all rule
pairs from the pinned upstream releases and refresh the source table above.
The updater also removes obsolete .its and .loc files from the bundle.
Use `--check` to verify that the bundle matches those releases without writing
or removing files. Downloads and XML validation must all succeed before any
files change.

Renovate updates the five version constants in the script. The ITS rules update
workflow then regenerates the bundle and uses the same maintenance-patch flow
as the other third-party data updates. Review upstream licensing changes and
run the ITS extraction tests when updating a release. GTK stays on the 3.24
series; GLib tracks stable (even-minor) releases.
