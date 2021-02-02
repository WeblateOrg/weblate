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


import os
import re
from itertools import chain

from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.text import slugify

from weblate.logger import LOGGER
from weblate.trans.defines import COMPONENT_NAME_LENGTH
from weblate.trans.models import Component
from weblate.trans.tasks import create_component
from weblate.trans.util import path_separator
from weblate.utils.render import render_template

# Attributes to copy from main component
COPY_ATTRIBUTES = (
    "project",
    "vcs",
    "license",
    "agreement",
    "source_language",
    "report_source_bugs",
    "allow_translation_propagation",
    "enable_suggestions",
    "suggestion_voting",
    "suggestion_autoaccept",
    "check_flags",
    "new_lang",
    "language_code_style",
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "committer_name",
    "committer_email",
    "push_on_commit",
    "commit_pending_age",
    "edit_template",
    "variant_regex",
)


class ComponentDiscovery:
    def __init__(
        self,
        component,
        match,
        name_template,
        file_format,
        language_regex="^[^.]+$",
        base_file_template="",
        new_base_template="",
        path=None,
        copy_addons=True,
    ):
        self.component = component
        if path is None:
            self.path = self.component.full_path
        else:
            self.path = path
        self.path_match = self.compile_match(match)
        self.name_template = name_template
        self.base_file_template = base_file_template
        self.new_base_template = new_base_template
        self.language_re = language_regex
        self.language_match = re.compile(language_regex)
        self.file_format = file_format
        self.copy_addons = copy_addons

    @staticmethod
    def extract_kwargs(params):
        """Extract kwargs for discovery from wider dict."""
        attrs = (
            "match",
            "name_template",
            "language_regex",
            "base_file_template",
            "new_base_template",
            "file_format",
            "copy_addons",
        )
        return {k: v for k, v in params.items() if k in attrs}

    def compile_match(self, match):
        parts = match.split("(?P=language)")
        offset = 1
        while len(parts) > 1:
            parts[0:2] = [
                "{}(?P<_language_{}>(?P=language)){}".format(parts[0], offset, parts[1])
            ]
            offset += 1
        return re.compile("^{}$".format(parts[0]))

    @cached_property
    def matches(self):
        """Return matched files together with match groups and mask."""
        result = []
        base = os.path.realpath(self.path)
        for root, dirnames, filenames in os.walk(self.path, followlinks=True):
            for filename in chain(filenames, dirnames):
                fullname = os.path.join(root, filename)

                # Skip files outside our root
                if not os.path.realpath(fullname).startswith(base):
                    continue

                # Calculate relative path
                path = path_separator(os.path.relpath(fullname, self.path))

                # Check match against our regexp
                matches = self.path_match.match(path)
                if not matches:
                    continue

                # Check language regexp
                language_part = matches.group("language")
                if language_part is None or not self.language_match.match(
                    language_part
                ):
                    continue

                # Calculate file mask for match
                replacements = [(matches.start("language"), matches.end("language"))]
                for group in matches.groupdict().keys():
                    if group.startswith("_language_"):
                        replacements.append((matches.start(group), matches.end(group)))
                maskparts = []
                maskpath = path
                for start, end in sorted(replacements, reverse=True):
                    maskparts.append(maskpath[end:])
                    maskpath = maskpath[:start]
                maskparts.append(maskpath)

                mask = "*".join(reversed(maskparts))

                result.append((path, matches.groupdict(), mask))

        return result

    @cached_property
    def matched_files(self):
        """Return list of matched files."""
        return [x[0] for x in self.matches]

    @cached_property
    def matched_components(self):
        """Return list of matched components."""
        result = {}
        for path, groups, mask in self.matches:
            if mask not in result:
                name = render_template(self.name_template, **groups)
                result[mask] = {
                    "files": {path},
                    "languages": {groups["language"]},
                    "files_langs": {(path, groups["language"])},
                    "base_file": render_template(self.base_file_template, **groups),
                    "new_base": render_template(self.new_base_template, **groups),
                    "mask": mask,
                    "name": name,
                    "slug": slugify(name),
                }
            else:
                result[mask]["files"].add(path)
                result[mask]["languages"].add(groups["language"])
                result[mask]["files_langs"].add((path, groups["language"]))
        return result

    def log(self, *args):
        if self.component:
            self.component.log_info(*args)
        else:
            LOGGER.info(*args)

    def create_component(self, main, match, background=False, **kwargs):
        max_length = COMPONENT_NAME_LENGTH

        def get_val(key, extra=0):
            result = match[key]
            if len(result) > max_length - extra:
                result = result[: max_length - extra]
            return result

        # Get name and slug
        name = get_val("name")
        slug = get_val("slug")

        # Copy attributes from main component
        for key in COPY_ATTRIBUTES:
            if key not in kwargs and main is not None:
                kwargs[key] = getattr(main, key)

        # Fill in repository
        if "repo" not in kwargs:
            kwargs["repo"] = main.get_repo_link_url()

        # Deal with duplicate name or slug
        components = Component.objects.filter(project=kwargs["project"])
        if components.filter(Q(slug__iexact=slug) | Q(name__iexact=name)).exists():
            base_name = get_val("name", 4)
            base_slug = get_val("slug", 4)

            for i in range(1, 1000):
                name = f"{base_name} {i}"
                slug = f"{base_slug}-{i}"

                if components.filter(
                    Q(slug__iexact=slug) | Q(name__iexact=name)
                ).exists():
                    continue
                break

        # Fill in remaining attributes
        kwargs.update(
            {
                "name": name,
                "slug": slug,
                "template": match["base_file"],
                "filemask": match["mask"],
                "new_base": match["new_base"],
                "file_format": self.file_format,
                "language_regex": self.language_re,
                "addons_from": main.pk if self.copy_addons and main else None,
            }
        )

        self.log("Creating component %s", name)
        # Can't pass objects, pass only IDs
        kwargs["project"] = kwargs["project"].pk
        kwargs["source_language"] = kwargs["source_language"].pk
        if background:
            create_component.delay(**kwargs, in_task=True)
            return None
        return create_component(**kwargs)

    def cleanup(self, main, processed, preview=False):
        deleted = []
        for component in main.linked_childs.exclude(pk__in=processed):
            if component.has_template():
                # Valid template?
                if os.path.exists(component.get_template_filename()):
                    continue
            elif component.new_base:
                # Valid new base?
                if os.path.exists(component.get_new_base_filename()):
                    continue
            else:
                if component.get_mask_matches():
                    continue

            # Delete as needed files seem to be missing
            deleted.append((None, component))
            if not preview:
                component.delete()

        return deleted

    def check_valid(self, match):
        def valid_file(name):
            if not name:
                return True
            fullname = os.path.join(self.component.full_path, name)
            return os.path.exists(fullname)

        # Skip matches to main component
        if match["mask"] == self.component.filemask:
            return False

        if not valid_file(match["base_file"]):
            return False

        if not valid_file(match["new_base"]):
            return False

        return True

    def perform(self, preview=False, remove=False, background=False):
        created = []
        matched = []
        deleted = []
        processed = set()

        main = self.component

        for match in self.matched_components.values():
            # Skip invalid matches
            if not self.check_valid(match):
                continue

            try:
                found = main.linked_childs.filter(filemask=match["mask"])[0]
                # Component exists
                matched.append((match, found))
                processed.add(found.id)
            except IndexError:
                # Create new component
                component = None
                if not preview:
                    component = self.create_component(main, match, background)
                if component:
                    processed.add(component.id)
                created.append((match, component))

        if remove:
            deleted = self.cleanup(main, processed, preview)

        return created, matched, deleted
