# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project level backups."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from itertools import chain
from shutil import copyfileobj
from typing import TYPE_CHECKING, Any, BinaryIO, TypedDict
from zipfile import ZipFile

from django.conf import settings
from django.core.files import File
from django.db import connection, transaction
from django.db.models.fields.files import FieldFile
from django.db.models.signals import pre_save
from django.utils import timezone
from weblate_schemas import load_schema, validate_schema

from weblate.auth.models import User, get_anonymous
from weblate.checks.models import Check
from weblate.lang.models import Language, Plural
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.models import (
    Comment,
    Component,
    Label,
    Project,
    Suggestion,
    Translation,
    Unit,
    Vote,
)
from weblate.utils.data import data_dir
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.validators import validate_filename
from weblate.utils.version import VERSION
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Callable

PROJECTBACKUP_PREFIX = "projectbackups"


class BackupListDict(TypedDict):
    name: str
    path: str
    timestamp: datetime
    size: int


class ProjectBackup:
    COMPONENTS_PREFIX = "components/"
    VCS_PREFIX = "vcs/"
    VCS_PREFIX_LEN = len(VCS_PREFIX)

    def __init__(
        self, filename: str | None = None, *, fileio: BinaryIO | None = None
    ) -> None:
        self.data: dict[str, Any] = {}
        self.filename = filename
        self.fileio = fileio
        self.timestamp = timezone.now()
        self.project: Project | None = None
        self.project_schema = load_schema("weblate-backup.schema.json")
        self.component_schema = load_schema("weblate-component.schema.json")
        self.languages_cache: dict[str, Language] = {}
        self.labels_map: dict[str, Label] = {}
        self.user_cache: dict[str, User] = {}

    @property
    def supports_restore(self):
        return connection.features.can_return_rows_from_bulk_insert

    def validate_data(self) -> None:
        validate_schema(self.data, "weblate-backup.schema.json")

    def backup_property(
        self, obj, field: str, extras: dict[str, Callable] | None = None
    ):
        if extras and field in extras:
            return extras[field](obj)
        value = getattr(obj, field)
        if isinstance(value, Language):
            return value.code
        if isinstance(value, Plural):
            return self.backup_object(
                value,
                self.component_schema["properties"]["translations"]["items"][
                    "properties"
                ]["plural"]["required"],
            )
        if isinstance(value, Unit):
            return value.checksum
        if isinstance(value, User):
            return value.username
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, FieldFile):
            return os.path.basename(value.name)  # type: ignore[type-var]
        return value

    def backup_object(
        self, obj, properties: list[str], extras: dict[str, Callable] | None = None
    ):
        return {field: self.backup_property(obj, field, extras) for field in properties}

    def backup_data(self, project) -> None:
        self.project = project
        self.data = {
            "metadata": {
                "version": VERSION,
                "server": settings.SITE_TITLE,
                "domain": settings.SITE_DOMAIN.rsplit(":", 1)[0],
                "timestamp": self.timestamp.isoformat(),
            },
            "project": self.backup_object(
                project, self.project_schema["properties"]["project"]["required"]
            ),
            "labels": [
                {"name": label.name, "color": label.color}
                for label in project.label_set.all()
            ],
        }

        # Make sure generated backup data is correct
        self.validate_data()

    def backup_dir(self, backupzip, directory: str, target: str) -> None:
        """Backup single directory to specified target in zip."""
        for folder, _subfolders, filenames in os.walk(directory):
            for filename in filenames:
                path = os.path.join(folder, filename)
                # zipfile does not support storing symlinks, it dereferences them
                if os.path.islink(path):
                    continue
                backupzip.write(
                    path, os.path.join(target, os.path.relpath(path, directory))
                )

    def backup_json(self, backupzip, data, target: str) -> None:
        with backupzip.open(target, "w") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def generate_filename(self, project) -> None:
        backup_dir = data_dir(PROJECTBACKUP_PREFIX, f"{project.pk}")
        backup_info = os.path.join(backup_dir, "README.txt")
        timestamp = int(self.timestamp.timestamp())
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        if not os.path.exists(backup_info):
            with open(backup_info, "w") as handle:
                handle.write(f"# Weblate project backups for {project.name}\n")
                handle.write(f"slug={project.slug}\n")
                handle.write(f"web={project.web}\n")
                for billing in project.billings:
                    handle.write(f"billing={billing.id}\n")
        while os.path.exists(
            os.path.join(backup_dir, f"{timestamp}.zip")
        ) or os.path.exists(os.path.join(backup_dir, f"{timestamp}.zip.part")):
            timestamp += 1
        self.filename = os.path.join(backup_dir, f"{timestamp}.zip")

    def backup_component(self, backupzip, component) -> None:
        data = {
            "component": self.backup_object(
                component, self.component_schema["properties"]["component"]["required"]
            ),
            "translations": [
                self.backup_object(
                    translation,
                    self.component_schema["properties"]["translations"]["items"][
                        "required"
                    ],
                )
                for translation in component.translation_set.iterator()
            ],
            "units": [
                self.backup_object(
                    unit,
                    self.component_schema["properties"]["units"]["items"]["required"],
                    extras={
                        "id_hash": lambda obj: obj.checksum,
                        "comments": lambda obj: [
                            self.backup_object(
                                comment,
                                self.component_schema["properties"]["units"]["items"][
                                    "properties"
                                ]["comments"]["items"]["required"],
                            )
                            for comment in obj.comment_set.prefetch_related("user")
                        ],
                        "suggestions": lambda obj: [
                            self.backup_object(
                                suggestion,
                                self.component_schema["properties"]["units"]["items"][
                                    "properties"
                                ]["suggestions"]["items"]["required"],
                                extras={
                                    "votes": lambda obj: [
                                        self.backup_object(
                                            vote,
                                            self.component_schema["properties"][
                                                "units"
                                            ]["items"]["properties"]["suggestions"][
                                                "items"
                                            ]["properties"]["votes"]["items"][
                                                "required"
                                            ],
                                        )
                                        for vote in obj.votes.through.objects.filter(
                                            suggestion=obj
                                        ).select_related("user")
                                    ],
                                },
                            )
                            for suggestion in obj.suggestion_set.prefetch_related(
                                "user"
                            )
                        ],
                        "checks": lambda obj: [
                            self.backup_object(
                                check,
                                self.component_schema["properties"]["units"]["items"][
                                    "properties"
                                ]["checks"]["items"]["required"],
                            )
                            for check in obj.check_set.all()
                        ],
                        "labels": lambda obj: list(
                            obj.labels.values_list("name", flat=True)
                        ),
                    },
                )
                for unit in Unit.objects.filter(
                    translation__component=component
                ).iterator()
            ],
        }

        data["screenshots"] = screenshots = []
        for screenshot in Screenshot.objects.filter(
            translation__component=component
        ).prefetch_related("units"):
            screenshots.append(
                self.backup_object(
                    screenshot,
                    self.component_schema["properties"]["screenshots"]["items"][
                        "required"
                    ],
                    extras={
                        "units": lambda obj: [
                            hash_to_checksum(id_hash)
                            for id_hash in obj.units.values_list("id_hash", flat=True)
                        ],
                    },
                )
            )
            backupzip.write(
                os.path.join(settings.MEDIA_ROOT, screenshot.image.path),
                os.path.join("screenshots", os.path.basename(screenshot.image.name)),
            )

        validate_schema(data, "weblate-component.schema.json")
        self.backup_json(
            backupzip, data, f"{self.COMPONENTS_PREFIX}{component.slug}.json"
        )

        # Store VCS repo in case it is present
        if component.is_repo_link:
            return
        self.backup_dir(
            backupzip,
            component.full_path,
            f"{self.VCS_PREFIX}{component.slug}",
        )

    @transaction.atomic
    def backup_project(self, project) -> None:
        """Backup whole project."""
        # Generate data
        self.backup_data(project)

        self.generate_filename(project)
        part_name = f"{self.filename}.part"

        # Create the zip with the content
        with ZipFile(part_name, "x") as backupzip:
            # Project data
            self.backup_json(
                backupzip,
                self.data,
                "weblate-backup.json",
            )

            # Translation memory, avoid using memory_db
            self.backup_json(
                backupzip,
                [
                    item.as_dict()
                    for item in project.memory_set.using("default").iterator()
                ],
                "weblate-memory.json",
            )

            # Components
            for component in project.component_set.iterator():
                self.backup_component(backupzip, component)

        os.rename(part_name, self.filename)

    def list_components(self, zipfile):
        return [
            name
            for name in zipfile.namelist()
            if name.startswith(self.COMPONENTS_PREFIX)
        ]

    def load_data(self, zipfile) -> None:
        with zipfile.open("weblate-backup.json") as handle:
            self.data = json.load(handle)
        self.validate_data()
        self.timestamp = datetime.fromisoformat(self.data["metadata"]["timestamp"])

    def load_memory(self, zipfile):
        with zipfile.open("weblate-memory.json") as handle:
            data = json.load(handle)
        validate_schema(data, "weblate-memory.schema.json")
        return data

    def load_components(self, zipfile, callback: Callable | None = None) -> None:
        for component in self.list_components(zipfile):
            with zipfile.open(component) as handle:
                data = json.load(handle)
                validate_schema(data, "weblate-component.schema.json")
                if data["component"]["vcs"] not in VCS_REGISTRY:
                    raise ValueError(
                        f'Component {data["component"]["name"]} uses unsupported VCS: {data["component"]["vcs"]}'
                    )
                # Validate translations have unique languages
                languages = defaultdict(list)
                for item in data["translations"]:
                    language = self.import_language(item["language_code"])
                    languages[language.code].append(item["language_code"])

                for code, values in languages.items():
                    if len(values) > 1:
                        raise ValueError(
                            f"Several languages from backup map to single language on this server {values} -> {code}"
                        )

                if callback is not None:
                    callback(zipfile, data)

    def validate(self) -> None:
        if not self.supports_restore:
            raise ValueError("Restore is not supported on this database.")
        input_file = self.filename or self.fileio
        if input_file is None:
            raise TypeError("Can not validate None file.")
        with ZipFile(input_file, "r") as zipfile:
            self.load_data(zipfile)
            self.load_memory(zipfile)
            self.load_components(zipfile)
            for name in zipfile.namelist():
                validate_filename(name)

    def restore_unit(self, item, translation_lookup, source_unit_lookup=None):
        kwargs = item.copy()
        for skip in ("labels", "comments", "suggestions", "checks"):
            kwargs.pop(skip)
        kwargs["id_hash"] = checksum_to_hash(kwargs["id_hash"])
        kwargs["translation_id"] = translation_lookup[kwargs["translation_id"]].id
        unit = Unit(**kwargs)
        unit.import_data = item
        if source_unit_lookup is not None:
            unit.source_unit = source_unit_lookup[item["id_hash"]]
        return unit

    def restore_user(self, username):
        if not self.user_cache:
            self.user_cache[settings.ANONYMOUS_USER_NAME] = get_anonymous()
        if username not in self.user_cache:
            try:
                self.user_cache[username] = User.objects.get(username=username)
            except User.DoesNotExist:
                # Fallback to anonymous?
                self.user_cache[username] = self.user_cache[
                    settings.ANONYMOUS_USER_NAME
                ]

        return self.user_cache[username]

    def restore_with_user(self, data, field: str = "user", remove: str | None = None):
        data = data.copy()
        if remove is not None:
            data.pop(remove)
        data[field] = self.restore_user(data[field])
        return data

    def restore_component(self, zipfile, data) -> None:  # noqa: C901
        kwargs = data["component"].copy()
        source_language = kwargs["source_language"] = self.import_language(
            kwargs["source_language"]
        )
        component = Component(project=self.project, **kwargs)
        # Trigger pre_save to update git export URL
        pre_save.send(
            sender=component.__class__,
            instance=component,
            raw=False,
            using=None,
            update_fields=None,
        )
        # Use bulk create to avoid triggering save() and any post_save signals
        component = Component.objects.bulk_create([component])[0]

        # Create translations
        translations = []
        source_translation_id = -1
        for item in data["translations"]:
            language = self.import_language(item["language_code"])
            plurals = language.plural_set.filter(**item["plural"])
            try:
                plural = plurals[0]
            except IndexError:
                if item["plural"]["source"] == Plural.SOURCE_DEFAULT:
                    plural = language.plural
                elif item["plural"]["source"] in {
                    Plural.SOURCE_MANUAL,
                    Plural.SOURCE_GETTEXT,
                }:
                    plural = language.plural_set.create(**item["plural"])
                else:
                    plural = language.plural_set.filter(
                        source=item["plural"]["source"]
                    )[0]
            translation = Translation(
                component=component,
                filename=item["filename"],
                language_code=item["language_code"],
                language=self.import_language(item["language_code"]),
                plural=plural,
                revision=item["revision"],
            )
            translation.original_id = item["id"]
            if language == source_language:
                source_translation_id = item["id"]
            translations.append(translation)
        translations = Translation.objects.bulk_create(translations)
        translation_lookup = {
            translation.original_id: translation for translation in translations
        }

        # Create source units
        source_units = [
            self.restore_unit(item, translation_lookup)
            for item in data["units"]
            if item["translation_id"] == source_translation_id
        ]
        source_units = Unit.objects.bulk_create(source_units)
        # Fix source unit links
        for unit in source_units:
            unit.source_unit = unit
        Unit.objects.bulk_update(source_units, ["source_unit"])
        source_unit_lookup = {unit.checksum: unit for unit in source_units}

        # Create translation units
        units = [
            self.restore_unit(item, translation_lookup, source_unit_lookup)
            for item in data["units"]
            if item["translation_id"] != source_translation_id
        ]
        units = Unit.objects.bulk_create(units)

        # Apply metadata
        for unit in chain(source_units, units):
            # Labels
            for label in unit.import_data["labels"]:
                unit.labels.add(self.labels_map[label])

            # Comments
            if unit.import_data["comments"]:
                Comment.objects.bulk_create(
                    Comment(unit=unit, **self.restore_with_user(comment))
                    for comment in unit.import_data["comments"]
                )

            # Checks
            if unit.import_data["checks"]:
                Check.objects.bulk_create(
                    Check(unit=unit, **check) for check in unit.import_data["checks"]
                )

            # Suggestions
            if unit.import_data["suggestions"]:
                suggestions = Suggestion.objects.bulk_create(
                    Suggestion(
                        unit=unit, **self.restore_with_user(suggestion, remove="votes")
                    )
                    for suggestion in unit.import_data["suggestions"]
                )
                suggestion_data = {
                    item["target"]: item for item in unit.import_data["suggestions"]
                }
                for suggestion in suggestions:
                    if suggestion_data[suggestion.target]["votes"]:
                        Vote.objects.bulk_create(
                            Vote(suggestion=suggestion, **self.restore_with_user(vote))
                            for vote in suggestion_data[suggestion.target]["votes"]
                        )

        # Create screenshots
        screenshots = []
        for item in data["screenshots"]:
            handle = zipfile.open(os.path.join("screenshots", item["image"]))
            screenshot = Screenshot(
                name=item["name"],
                image=File(handle),
                translation=translation_lookup[item["translation_id"]],
                user=self.restore_user(item["user"]),
                timestamp=item["timestamp"],
            )
            screenshot.import_data = item
            screenshot.import_handle = handle
            screenshots.append(screenshot)

        screenshots = Screenshot.objects.bulk_create(screenshots)
        for screenshot in screenshots:
            if screenshot.import_data["units"]:
                screenshot.units.set(
                    screenshot.translation.unit_set.filter(
                        id_hash__in=[
                            checksum_to_hash(id_hash)
                            for id_hash in screenshot.import_data["units"]
                        ]
                    )
                )
            screenshot.import_handle.close()  # type: ignore[union-attr]

        # Trigger checks update, the implementation might have changed
        component.schedule_update_checks()

    def import_language(self, code: str):
        if not self.languages_cache:
            self.languages_cache = {lang.code: lang for lang in Language.objects.all()}
        try:
            return self.languages_cache[code]
        except KeyError:
            self.languages_cache[code] = language = Language.objects.auto_get_or_create(
                code
            )
            return language

    @transaction.atomic
    def restore(self, project_name: str, project_slug: str, user: User, billing=None):
        if not isinstance(self.filename, str):
            raise TypeError("Need a filename string.")
        with ZipFile(self.filename, "r") as zipfile:
            self.load_data(zipfile)

            # Create project
            kwargs = self.data["project"].copy()
            kwargs["name"] = project_name
            kwargs["slug"] = project_slug
            self.project = project = Project.objects.create(**kwargs)

            # Handle billing and ACL (creating user needs access)
            self.project.post_create(user, billing)

            # Create labels
            labels = Label.objects.bulk_create(
                Label(project=project, **entry) for entry in self.data["labels"]
            )
            self.labels_map = {label.name: label for label in labels}

            # Import translation memory
            memory = self.load_memory(zipfile)
            Memory.objects.bulk_create(
                [
                    Memory(
                        project=project,
                        origin=entry["origin"],
                        source=entry["source"],
                        target=entry["target"],
                        source_language=self.import_language(entry["source_language"]),
                        target_language=self.import_language(entry["target_language"]),
                    )
                    for entry in memory
                ]
            )

            # Extract VCS
            for name in zipfile.namelist():
                if name.startswith(self.VCS_PREFIX):
                    path = name[self.VCS_PREFIX_LEN :]
                    # Skip potentially dangerous paths
                    if path != os.path.normpath(path):
                        continue
                    targetpath = os.path.join(project.full_path, path)
                    upperdirs = os.path.dirname(targetpath)
                    if upperdirs and not os.path.exists(upperdirs):
                        os.makedirs(upperdirs)
                    with zipfile.open(name) as source, open(targetpath, "wb") as target:
                        copyfileobj(source, target)

            # Create components
            self.load_components(zipfile, self.restore_component)

        # Fixup linked components
        old_slug = f"/{self.data['project']['slug']}/"
        new_slug = f"/{project.slug}/"
        for component in self.project.component_set.filter(
            repo__istartswith="weblate:"
        ):
            component.repo = component.repo.replace(old_slug, new_slug)
            component.save()

        return self.project

    def store_for_import(self):
        backup_dir = data_dir(PROJECTBACKUP_PREFIX, "import")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        timestamp = int(timezone.now().timestamp())
        if self.fileio is None or isinstance(self.fileio, str):
            raise TypeError("Need a file object.")
        # self.fileio is a file object from upload here
        self.fileio.seek(0)
        while os.path.exists(os.path.join(backup_dir, f"{timestamp}.zip")):
            timestamp += 1
        filename = os.path.join(backup_dir, f"{timestamp}.zip")
        with open(filename, "xb") as target:
            copyfileobj(self.fileio, target)
        return filename
