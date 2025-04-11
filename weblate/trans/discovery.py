# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
from itertools import chain

from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext

from weblate.formats.base import TranslationFormat
from weblate.formats.models import FILE_FORMATS
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
    "pull_message",
    "push_on_commit",
    "commit_pending_age",
    "edit_template",
    "manage_units",
    "variant_regex",
    "category_id",
    "key_filter",
    "secondary_language",
)


class ComponentDiscovery:
    def __init__(
        self,
        component,
        *,
        match: str,
        name_template: str,
        file_format: str,
        language_regex: str = "^[^.]+$",
        base_file_template: str = "",
        new_base_template: str = "",
        intermediate_template: str = "",
        path=None,
        copy_addons=True,
    ) -> None:
        self.component = component
        if path is None:
            self.path = self.component.full_path
        else:
            self.path = path
        self.path_match = self.compile_match(match)
        self.name_template = name_template
        self.base_file_template = base_file_template
        self.new_base_template = new_base_template
        self.intermediate_template = intermediate_template
        self.language_re = language_regex
        self.language_match = re.compile(language_regex)
        self.file_format = file_format
        self.copy_addons = copy_addons

    @cached_property
    def file_format_cls(self) -> type[TranslationFormat]:
        return FILE_FORMATS[self.file_format]

    @staticmethod
    def extract_kwargs(params):
        """Extract kwargs for discovery from wider dict."""
        attrs = (
            "match",
            "name_template",
            "language_regex",
            "base_file_template",
            "new_base_template",
            "intermediate_template",
            "file_format",
            "copy_addons",
        )
        return {k: v for k, v in params.items() if k in attrs}

    def compile_match(self, match):
        parts = match.split("(?P=language)")
        offset = 1
        while len(parts) > 1:
            parts[0:2] = [f"{parts[0]}(?P<_language_{offset}>(?P=language)){parts[1]}"]
            offset += 1
        return re.compile(f"^{parts[0]}$")

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
                replacements.extend(
                    (matches.start(group), matches.end(group))
                    for group in matches.groupdict()
                    if group.startswith("_language_")
                )
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
                    "intermediate": render_template(
                        self.intermediate_template, **groups
                    ),
                    "mask": mask,
                    "name": name,
                    "slug": slugify(name),
                }
            else:
                result[mask]["files"].add(path)
                result[mask]["languages"].add(groups["language"])
                result[mask]["files_langs"].add((path, groups["language"]))
        return result

    def log(self, *args) -> None:
        if self.component:
            self.component.log_info(*args)
        else:
            LOGGER.info(*args)

    def create_component(
        self,
        main: Component | None,
        match,
        *,
        background: bool = False,
        preview: bool = False,
        existing_slugs: set[str],
        existing_names: set[str],
        **kwargs,
    ):
        max_length = COMPONENT_NAME_LENGTH

        def get_val(key, extra=0):
            result = match[key]
            if len(result) > max_length - extra:
                result = result[: max_length - extra]
            return result

        # Get name and slug
        name = get_val("name") or "Component"
        slug = get_val("slug") or "component"

        # Copy attributes from main component
        for key in COPY_ATTRIBUTES:
            if key not in kwargs and main is not None:
                kwargs[key] = getattr(main, key)

        # Disable template editing if not supported by format
        if not self.file_format_cls.can_edit_base:
            kwargs["edit_template"] = False

        # Fill in repository
        if "repo" not in kwargs:
            if main is None:
                raise ValueError
            kwargs["repo"] = main.get_repo_link_url()

        # Deal with duplicate name or slug in the same (or none) category
        if slug.lower() in existing_slugs or name.lower() in existing_names:
            base_name = get_val("name", 4)
            base_slug = get_val("slug", 4)

            for i in range(1, 1000):
                name = f"{base_name} {i}"
                slug = f"{base_slug}-{i}"

                if slug.lower() in existing_slugs or name.lower() in existing_names:
                    continue
                break
        existing_slugs.add(slug.lower())
        existing_names.add(name.lower())

        # Fill in remaining attributes
        kwargs.update(
            {
                "name": name,
                "slug": slug,
                "template": match["base_file"],
                "filemask": match["mask"],
                "new_base": match["new_base"],
                "intermediate": match["intermediate"],
                "file_format": self.file_format,
                "language_regex": self.language_re,
                "copy_from": main.pk if main else None,
                "copy_addons": self.copy_addons,
            }
        )

        # Create non-saved object for validation
        component_kwargs = kwargs.copy()
        component_kwargs.pop("copy_from")
        component_kwargs.pop("copy_addons")
        # main can be None as well
        component = Component(**component_kwargs, linked_component=main)

        # Special handling for new_lang
        try:
            component.clean_new_lang()
        except ValidationError as error:
            component.new_lang = kwargs["new_lang"] = "none"
            self.log("Disabling adding new languages for %s because of %s", name, error)

        # This might raise an exception
        component.full_clean()

        if preview:
            return component

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
            elif component.get_mask_matches():
                continue

            # Delete as needed files seem to be missing
            deleted.append((None, component))
            if not preview:
                component.delete()

        return deleted

    def get_skip_reason(self, match):
        # Skip matches to main component
        if match["mask"] == self.component.filemask:
            return gettext("File mask matches the main component.")

        for param in ("base_file", "new_base", "intermediate"):
            name = match[param]
            if not name:
                continue
            fullname = os.path.join(self.component.full_path, name)
            if not os.path.exists(fullname):
                return gettext("{filename} ({parameter}) does not exist.").format(
                    filename=name,
                    parameter=param,
                )

        return None

    def perform(self, preview=False, remove=False, background=False):
        created = []
        matched = []
        deleted = []
        skipped = []
        processed = set()

        main = self.component
        category_components = main.project.component_set.filter(category=main.category)
        existing_childs: dict[str, Component] = {
            component.filemask: component for component in main.linked_childs.all()
        }
        existing_slugs: set[str] = {
            slug.lower() for slug in category_components.values_list("slug", flat=True)
        }
        existing_names: set[str] = {
            name.lower() for name in category_components.values_list("name", flat=True)
        }

        for match in self.matched_components.values():
            # Skip invalid matches
            reason = self.get_skip_reason(match)
            if reason is not None:
                skipped.append((match, reason))
                continue

            try:
                found = existing_childs[match["mask"]]
            except KeyError:
                # Create new component
                try:
                    component = self.create_component(
                        main,
                        match,
                        background=background,
                        preview=preview,
                        existing_slugs=existing_slugs,
                        existing_names=existing_names,
                    )
                except ValidationError as error:
                    skipped.append((match, str(error)))
                else:
                    # Correctly created
                    if component is not None and component.id:
                        processed.add(component.id)
                    created.append((match, component))
                    existing_childs[match["mask"]] = component
            else:
                # Component already exists
                matched.append((match, found))
                processed.add(found.id)

        if remove:
            deleted = self.cleanup(main, processed, preview)

        return created, matched, deleted, skipped
