# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sphinx plugins for Weblate documentation."""

import re

from docutils import nodes
from docutils.nodes import literal
from sphinx import addnodes
from sphinx.domains.std import Cmdoption

# RE for option descriptions without a '--' prefix
simple_option_desc_re = re.compile(r"([-_a-zA-Z0-9]+)(\s*.*?)(?=,\s+(?:/|-|--)|$)")

GHSSA_URL = "https://github.com/WeblateOrg/weblate/security/advisories/{}"


class WeblateCommandLiteral(literal):
    def __init__(self, rawsource="", text="", *children, **attributes) -> None:
        if not text:
            text = "weblate "
        super().__init__(rawsource, text, *children, **attributes)


def ghsa_link(name, rawtext, text, lineno, inliner, options={}, content=[]):  # noqa:B006
    fullname = f"GHSA-{text}"
    url = GHSSA_URL.format(fullname)
    node = nodes.reference(rawtext, fullname, refuri=url, **options)
    return [node], []


def setup(app) -> None:
    app.add_crossref_type(
        directivename="setting", rolename="setting", indextemplate="pair: %s; setting"
    )
    app.add_object_type(
        directivename="weblate-admin",
        rolename="wladmin",
        indextemplate="pair: %s; weblate admin command",
        parse_node=parse_weblate_admin_node,
        ref_nodeclass=WeblateCommandLiteral,
    )
    app.add_directive("weblate-admin-option", Cmdoption)
    app.add_object_type(
        directivename="django-admin",
        rolename="djadmin",
        indextemplate="pair: %s; django-admin command",
        parse_node=parse_django_admin_node,
    )
    app.add_role("ghsa", ghsa_link)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


def parse_weblate_admin_node(env, sig, signode):
    command = sig.split(" ")[0]
    # Context for options
    env.ref_context["std:program"] = command
    title = f"weblate {sig}"
    signode += addnodes.desc_name(title, title)
    return command


def parse_django_admin_node(env, sig, signode):
    command = sig.split(" ")[0]
    env.ref_context["std:program"] = command
    title = f"django-admin {sig}"
    signode += addnodes.desc_name(title, title)
    return command
