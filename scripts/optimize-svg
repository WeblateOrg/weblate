#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

optimize() {
    # SVG optimization
    scour --strip-xml-space --strip-xml-prolog --remove-metadata --no-line-breaks --enable-id-stripping --enable-comment-stripping --indent=none --remove-descriptive-elements "$icon" "$icon.tmp"
    # Remove possible doctype
    sed '/!DOCTYPE/d' < "$icon.tmp" > "$icon"
    # Remove trailing newline (imgbot does this and we want to avoid fighting with it)
    truncate -s -1 "$icon"
    rm "$icon.tmp"
}

if [ $# -ne 0 ]; then
    for icon in "$@"; do
        optimize "$icon"
    done
    exit 0
fi

for icon in weblate/static/icons/*.svg weblate/static/auth/*.svg weblate/static/state/*.svg weblate/static/sort/*.svg; do
    optimize "$icon"
done
