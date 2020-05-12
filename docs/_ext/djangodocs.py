"""Sphinx plugins for Weblate documentation."""
import re

from sphinx import addnodes
from sphinx.domains.std import Cmdoption

# RE for option descriptions without a '--' prefix
simple_option_desc_re = re.compile(r"([-_a-zA-Z0-9]+)(\s*.*?)(?=,\s+(?:/|-|--)|$)")


def setup(app):
    app.add_crossref_type(
        directivename="setting", rolename="setting", indextemplate="pair: %s; setting"
    )
    app.add_object_type(
        directivename="django-admin",
        rolename="djadmin",
        indextemplate="pair: %s; weblate admin command",
        parse_node=parse_django_admin_node,
    )
    app.add_directive("django-admin-option", Cmdoption)


def parse_django_admin_node(env, sig, signode):
    command = sig.split(" ")[0]
    env.ref_context["std:program"] = command
    title = f"weblate {sig}"
    signode += addnodes.desc_name(title, title)
    return command
