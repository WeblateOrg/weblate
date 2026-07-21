# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project level backups."""

from __future__ import annotations

import json
import os
import warnings
from collections import defaultdict
from datetime import datetime
from functools import partial
from io import BytesIO
from operator import itemgetter
from pathlib import Path
from shutil import copyfileobj
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Literal,
    TypedDict,
    TypeVar,
    cast,
    overload,
)
from zipfile import ZipFile

from django.conf import settings
from django.contrib.staticfiles.storage import HashedFilesMixin, staticfiles_storage
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.db.models.fields.files import FieldFile
from django.db.models.signals import pre_save
from django.utils import timezone
from django.utils.timezone import make_aware
from django.utils.translation import gettext
from weblate_schemas import load_schema, validate_schema

from weblate.auth.models import (
    AutoGroup,
    Group,
    Role,
    TeamMembership,
    User,
    get_anonymous,
)
from weblate.checks.models import Check
from weblate.lang.models import Language, Plural
from weblate.memory.models import Memory, MemoryDict, MemoryScope
from weblate.memory.utils import CATEGORY_PRIVATE_OFFSET
from weblate.screenshots.models import Screenshot
from weblate.trans import defaults
from weblate.trans.actions import ActionEvents
from weblate.trans.inherited_settings import (
    INHERITABLE_COMPONENT_FLAGS,
    INHERITABLE_COMPONENT_SETTINGS,
)
from weblate.trans.models import (
    Category,
    Change,
    Comment,
    Component,
    Label,
    PendingUnitChange,
    Project,
    Suggestion,
    Translation,
    Unit,
    Vote,
)
from weblate.utils.data import data_path
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.validators import (
    validate_bitmap,
    validate_filename,
    validate_repo_url,
)
from weblate.utils.version import VERSION
from weblate.utils.zip import (
    ZipSafetyLimits,
    extract_zip_member,
    iter_safe_zip_members,
    validate_zip_member_path,
)
from weblate.utils.zip import (
    validate_zip_members as validate_safe_zip_members,
)
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from zipfile import ZipInfo

    from django.core.files.storage import Storage
    from django.db.models import Model

    from weblate.billing.models import Billing
    from weblate.workspaces.models import Workspace

warnings.filterwarnings("error", module="zipfile")

ModelT = TypeVar("ModelT", bound="Model")
PROJECTBACKUP_PREFIX = "projectbackups"
BackupValue = str | int | bool | dict[str, Any] | list[Any] | None
PROJECT_INHERITABLE_BACKUP_FIELDS = (
    "check_flags",
    *INHERITABLE_COMPONENT_SETTINGS,
    *INHERITABLE_COMPONENT_FLAGS,
)
COMPONENT_INHERITABLE_BACKUP_FIELDS = (
    "secondary_language",
    *INHERITABLE_COMPONENT_FLAGS,
)
CATEGORY_INHERITABLE_BACKUP_FIELDS = (
    "check_flags",
    *INHERITABLE_COMPONENT_SETTINGS,
    *INHERITABLE_COMPONENT_FLAGS,
)


def get_project_backup_download_storage() -> Storage:
    return staticfiles_storage


def get_project_backup_download_url(name: str) -> str:
    storage = get_project_backup_download_storage()
    if isinstance(storage, HashedFilesMixin):
        return super(HashedFilesMixin, storage).url(name)
    return storage.url(name)


class BackupListDict(TypedDict):
    name: str
    path: str
    timestamp: datetime
    size: int


def list_backups(project_id: Project | int | str) -> list[BackupListDict]:
    if isinstance(project_id, Project):
        project_id = project_id.pk
    backup_dir = data_path(PROJECTBACKUP_PREFIX) / f"{project_id}"
    if not backup_dir.exists():
        return []
    result: list[BackupListDict] = [
        {
            "name": entry.name,
            "path": entry.as_posix(),
            "timestamp": make_aware(
                datetime.fromtimestamp(int(entry.name.split(".")[0]))  # ruff: ignore[call-datetime-fromtimestamp]
            ),
            "size": entry.stat().st_size,
        }
        for entry in backup_dir.glob("*.zip")
    ]
    return sorted(result, key=itemgetter("timestamp"), reverse=True)


class ProjectBackup:
    COMPONENTS_PREFIX = "components/"
    VCS_PREFIX = "vcs/"
    VCS_PREFIX_LEN = len(VCS_PREFIX)
    IMPORT_BATCH_SIZE = 2000
    MAX_ARCHIVE_MEMBERS = defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_MEMBERS
    # Per-entry limits reject suspiciously high compression ratios, while the
    # total uncompressed limit constrains low-compression archives as a whole.
    MAX_COMPRESSED_ENTRY_SIZE = (
        defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE
    )
    MIN_COMPRESSED_RATIO_SIZE = defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE
    MAX_COMPRESSED_ENTRY_RATIO = (
        defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO
    )
    MAX_TOTAL_UNCOMPRESSED_SIZE = (
        defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE
    )

    def __init__(self, filename: str = "", *, fileio: BinaryIO | None = None) -> None:
        self.data: dict[str, Any] = {}
        self.filename = filename
        self.fileio = fileio
        self.timestamp = timezone.now()
        self.validated = False
        self.project: Project | None = None
        self.project_schema = load_schema("weblate-backup.schema.json")
        self.component_schema = load_schema("weblate-component.schema.json")
        self.languages_cache: dict[str, Language] = {}
        self.labels_map: dict[str, Label] = {}
        self.user_cache: dict[str, User] = {}
        self.components_cache: dict[str, Component] = {}
        self.categories_cache: dict[str, Category] = {}
        self.roles_cache: dict[str, Role] = {}
        self.skipped_components: list[str] = []
        # Project.set_language_team field was migrated to file format parameters after 5.17
        self.set_language_team_project: bool = False

    @staticmethod
    def full_slug_without_project(obj: Component | Category) -> str:
        """Return the full slug for a component or category without the project slug."""
        parts = obj.get_url_path()
        return "/".join(parts[1:])

    def validate_data(self) -> None:
        validate_schema(self.data, "weblate-backup.schema.json")

    def backup_value(self, value: object) -> BackupValue:
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
        if value is None or isinstance(value, str | int | bool):
            return value
        if isinstance(value, dict):
            return cast("dict[str, Any]", value)
        if isinstance(value, list):
            return cast("list[Any]", value)
        return cast("BackupValue", value)

    def backup_property(
        self,
        obj: ModelT,
        field: str,
        extras: Mapping[str, Callable[[ModelT], object]] | None = None,
    ) -> BackupValue:
        if extras and field in extras:
            return self.backup_value(extras[field](obj))
        return self.backup_value(getattr(obj, field))

    def backup_object(
        self,
        obj: ModelT,
        properties: list[str],
        extras: Mapping[str, Callable[[ModelT], object]] | None = None,
    ) -> dict[str, BackupValue]:
        return {field: self.backup_property(obj, field, extras) for field in properties}

    @staticmethod
    def extend_fields(fields: list[str], *extra_fields: str) -> list[str]:
        return list(dict.fromkeys((*fields, *extra_fields)))

    def import_inherited_settings(self, kwargs: dict[str, Any]) -> None:
        for field in INHERITABLE_COMPONENT_FLAGS:
            kwargs.setdefault(field, False)
        if "secondary_language" in kwargs and kwargs["secondary_language"] is not None:
            kwargs["secondary_language"] = self.import_language(
                kwargs["secondary_language"]
            )

    def backup_m2m_flat(self, obj: Model, relation: str, field: str) -> list:
        """Backup a many to many relation using a unique identifying field of the related object."""
        return list(getattr(obj, relation).values_list(field, flat=True))

    def backup_teams(self, project: Project) -> list[dict]:
        extras: dict[str, Callable] = {}
        for schema_name, relation, field in [
            ("roles", "roles", "name"),
            ("languages", "languages", "code"),
            ("admins", "admins", "username"),
            ("autogroups", "autogroup_set", "match"),
        ]:
            extras[schema_name] = partial(
                self.backup_m2m_flat,
                relation=relation,
                field=field,
            )
        extras["components"] = lambda obj: [
            self.full_slug_without_project(c) for c in obj.components.all()
        ]
        extras["members"] = self.backup_team_members

        return [
            self.backup_object(
                group,
                self.project_schema["properties"]["teams"]["items"]["required"],
                extras,
            )
            for group in project.defined_groups.all()
        ]

    @staticmethod
    def backup_team_members(group: Group) -> list[str | dict[str, Any]]:
        result: list[str | dict[str, Any]] = []
        memberships = (
            group.memberships.select_related("user")
            .prefetch_related(
                Prefetch("limit_languages", queryset=Language.objects.only("code"))
            )
            .order_by("user__username")
        )
        for membership in memberships:
            limit_languages = sorted(
                language.code for language in membership.limit_languages.all()
            )
            if limit_languages:
                result.append(
                    {
                        "username": membership.user.username,
                        "limit_languages": limit_languages,
                    }
                )
            else:
                result.append(membership.user.username)
        return result

    def backup_memory(self, project: Project) -> list[MemoryDict]:
        project_scope = MemoryScope.objects.using("default").filter(
            memory_id=OuterRef("pk"),
            project_id=project.pk,
            scope__in=(MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE),
        )
        memory = (
            Memory.objects.using("default")
            .alias(has_project_scope=Exists(project_scope))
            .filter(has_project_scope=True)
            .prefetch_scopes()
            .order_by("id")
        )
        category = CATEGORY_PRIVATE_OFFSET + project.pk
        return [
            item.as_dict(category=category)
            for item in memory.iterator(self.IMPORT_BATCH_SIZE)
        ]

    def backup_categories(
        self, obj: Project | Category
    ) -> list[dict[str, BackupValue]]:
        if isinstance(obj, Project):
            categories = obj.category_set.filter(category=None)
        else:
            categories = obj.category_set.all()
        category_fields = self.extend_fields(
            self.project_schema["definitions"]["category"]["required"],
            *CATEGORY_INHERITABLE_BACKUP_FIELDS,
        )
        return [
            self.backup_object(
                category,
                category_fields,
                {"categories": self.backup_categories},
            )
            for category in categories
        ]

    def backup_data(self, project: Project) -> None:
        self.project = project
        project_fields = self.extend_fields(
            self.project_schema["properties"]["project"]["required"],
            "use_workspace_tm",
            "contribute_workspace_tm",
            *PROJECT_INHERITABLE_BACKUP_FIELDS,
        )
        project_extras: dict[str, Callable[[Project], object]] = {
            field: partial(Project.get_effective_setting, field=field)
            for field in INHERITABLE_COMPONENT_SETTINGS
        }
        project_extras["check_flags"] = lambda obj: obj.effective_check_flags.format()
        self.data = {
            "metadata": {
                "version": VERSION,
                "server": settings.SITE_TITLE,
                "domain": settings.SITE_DOMAIN.rsplit(":", 1)[0],
                "timestamp": self.timestamp.isoformat(),
            },
            "project": self.backup_object(project, project_fields, project_extras),
            "labels": [
                {"name": label.name, "color": label.color}
                for label in project.label_set.all()
            ],
            "categories": self.backup_categories(project),
            "teams": self.backup_teams(project),
        }

        # Make sure generated backup data is correct
        self.validate_data()

    def backup_dir(self, backupzip: ZipFile, directory: str, target: str) -> None:
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

    def backup_json(self, backupzip: ZipFile, data: dict | list, target: str) -> None:
        with backupzip.open(target, "w") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def generate_filename(self, project: Project) -> None:
        # Create directory
        backup_dir = data_path(PROJECTBACKUP_PREFIX) / f"{project.pk}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create README.txt
        backup_info = backup_dir / "README.txt"
        if not backup_info.exists():
            with backup_info.open("w") as handle:
                handle.write(f"# Weblate project backups for {project.name}\n")
                handle.write(f"slug={project.slug}\n")
                handle.write(f"web={project.web}\n")
                handle.writelines(
                    f"billing={billing.id}\n" for billing in project.billings
                )

        # Find unused timestamp
        timestamp = int(self.timestamp.timestamp())
        while (filename := backup_dir / f"{timestamp}.zip").exists() or (
            backup_dir / f"{timestamp}.zip.part"
        ).exists():
            timestamp += 1

        self.filename = filename.as_posix()

    @property
    def relative_filename(self) -> str:
        return (
            Path(self.filename).relative_to(data_path(PROJECTBACKUP_PREFIX)).as_posix()
        )

    def backup_component(self, backupzip: ZipFile, component: Component) -> None:
        component_fields = self.extend_fields(
            self.component_schema["properties"]["component"]["required"],
            *COMPONENT_INHERITABLE_BACKUP_FIELDS,
        )
        data: dict = {
            "component": self.backup_object(
                component,
                component_fields,
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
            "pending_unit_changes": [
                self.backup_object(
                    pending_unit_change,
                    self.component_schema["properties"]["pending_unit_changes"][
                        "items"
                    ]["required"],
                    extras={
                        "unit_id_hash": lambda obj: obj.unit.checksum,
                        "translation_id": lambda obj: obj.unit.translation_id,
                    },
                )
                for pending_unit_change in PendingUnitChange.objects.for_component(
                    component, apply_filters=False
                )
                .prefetch_related("unit", "author")
                .iterator(2000)
            ],
        }
        # component category is not a required field
        if component.category:
            data["component"]["category"] = self.full_slug_without_project(
                component.category
            )

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
            image_name = screenshot.image.name
            if image_name is None:
                raise ValidationError(gettext("Screenshot image is missing."))
            backupzip.write(
                os.path.join(settings.MEDIA_ROOT, screenshot.image.path),
                os.path.join("screenshots", os.path.basename(image_name)),
            )

        validate_schema(data, "weblate-component.schema.json")
        self.backup_json(
            backupzip,
            data,
            f"{self.COMPONENTS_PREFIX}{self.full_slug_without_project(component)}.json",
        )

        # Store VCS repo in case it is present
        if component.is_repo_link:
            return

        # Compact the repository
        with component.repository.lock:
            component.repository.maintenance()

        # Actually perform the backup
        self.backup_dir(
            backupzip,
            component.full_path,
            f"{self.VCS_PREFIX}{self.full_slug_without_project(component)}",
        )

    @transaction.atomic
    def backup_project(self, project: Project, user: User | None = None) -> None:
        """Backup whole project."""
        project.log_info("creating project backup")
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
                self.backup_memory(project),
                "weblate-memory.json",
            )

            # Components
            for component in project.component_set.iterator():
                self.backup_component(backupzip, component)

        os.rename(part_name, self.filename)
        self.log_backup(project, user)

    def log_backup(self, project: Project, user: User | None = None) -> None:
        project.log_info("project backup completed")
        project.change_set.create(
            action=ActionEvents.PROJECT_BACKUP,
            user=user,
            author=user,
            details={"backup_filename": self.relative_filename},
        )
        for billing in project.billings:
            self.log_backup_billing(project, billing)

    def log_backup_billing(self, project: Project, billing: Billing) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import (
            BillingEvent,
        )

        billing.billinglog_set.create(
            event=BillingEvent.PROJECT_BACKUP,
            summary=f"Backed up project {project}",
            details={
                "backup_filename": self.relative_filename,
                "project_name": project.name,
            },
        )

    def get_restore_history_details(self) -> dict[str, BackupValue]:
        metadata = self.data["metadata"]
        details: dict[str, BackupValue] = {
            "backup_timestamp": metadata["timestamp"],
            "backup_server": metadata["server"],
            "backup_domain": metadata["domain"],
        }
        if self.skipped_components:
            details["skipped_components"] = self.skipped_components
        return details

    @staticmethod
    def get_component_backup_slug(data: dict[str, Any]) -> str:
        slug = data["slug"]
        if category := data.get("category"):
            return f"{category}/{slug}"
        return slug

    def list_components(self, zipfile: ZipFile) -> list[str]:
        return [
            name
            for name in zipfile.namelist()
            if name.startswith(self.COMPONENTS_PREFIX)
        ]

    @staticmethod
    def is_unsafe_vcs_path(path: str) -> bool:
        normalized = path.replace("\\", "/")
        return (
            normalized.endswith(
                (
                    "/.git",
                    "/.git/config",
                    "/.git/config.worktree",
                    "/.git/hooks",
                    "/.git/modules",
                    "/.hg/hgrc",
                )
            )
            # Hooks are executable content; Gerrit's commit-msg hook is recreated
            # by git-review when needed.
            or "/.git/hooks/" in normalized
            or "/.git/modules/" in normalized
        )

    @classmethod
    def get_limit(cls, setting_name: str, default: int) -> int:
        return int(getattr(settings, setting_name, default))

    def validate_backup_zip_member(self, info: ZipInfo) -> None:
        validate_filename(info.filename, check_prohibited=False)
        if info.is_dir() or not info.filename.startswith(self.VCS_PREFIX):
            return
        validate_zip_member_path(info.filename[self.VCS_PREFIX_LEN :])

    def validate_zip_members(self, zipfile: ZipFile) -> None:
        validate_safe_zip_members(
            zipfile,
            limits=ZipSafetyLimits(
                max_members=self.get_limit(
                    "PROJECT_BACKUP_IMPORT_MAX_MEMBERS", self.MAX_ARCHIVE_MEMBERS
                ),
                max_compressed_entry_size=self.get_limit(
                    "PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE",
                    self.MAX_COMPRESSED_ENTRY_SIZE,
                ),
                min_compressed_ratio_size=self.get_limit(
                    "PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE",
                    self.MIN_COMPRESSED_RATIO_SIZE,
                ),
                max_compressed_entry_ratio=self.get_limit(
                    "PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO",
                    self.MAX_COMPRESSED_ENTRY_RATIO,
                ),
                max_total_uncompressed_size=self.get_limit(
                    "PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE",
                    self.MAX_TOTAL_UNCOMPRESSED_SIZE,
                ),
            ),
            validate_member=self.validate_backup_zip_member,
        )

    def load_data(self, zipfile: ZipFile) -> None:
        with zipfile.open("weblate-backup.json") as handle:
            self.data = json.load(handle)
        self.validate_data()
        self.timestamp = datetime.fromisoformat(self.data["metadata"]["timestamp"])

    def load_memory(self, zipfile: ZipFile) -> dict:
        with zipfile.open("weblate-memory.json") as handle:
            data = json.load(handle)
        validate_schema(data, "weblate-memory.schema.json")
        return data

    @overload
    def load_component(
        self,
        zipfile: ZipFile,
        filename: str,
        *,
        skip_linked: bool = False,
        do_restore: Literal[False] = False,
        actor: None = None,
        changes: None = None,
    ) -> bool: ...

    @overload
    def load_component(
        self,
        zipfile: ZipFile,
        filename: str,
        *,
        skip_linked: bool = False,
        do_restore: Literal[True],
        actor: User,
        changes: list[Change],
    ) -> bool: ...

    def load_component(
        self,
        zipfile: ZipFile,
        filename: str,
        *,
        skip_linked: bool = False,
        do_restore: bool = False,
        actor: User | None = None,
        changes: list[Change] | None = None,
    ) -> bool:
        with zipfile.open(filename) as handle:
            data = json.load(handle)
            validate_schema(data, "weblate-component.schema.json")
            self.validate_component_urls(data["component"])
            if skip_linked and data["component"]["repo"].startswith("weblate:"):
                return False
            if data["component"]["vcs"] not in VCS_REGISTRY:
                msg = f"Component {data['component']['name']} uses unsupported VCS: {data['component']['vcs']}"
                raise ValueError(msg)
            # Validate translations have unique languages
            languages = defaultdict(list)
            for item in data["translations"]:
                language = self.import_language(item["language_code"])
                languages[language.code].append(item["language_code"])

            for code, values in languages.items():
                if len(values) > 1:
                    msg = f"Several languages from backup map to single language on this server {values} -> {code}"
                    raise ValueError(msg)

            if do_restore:
                if actor is None:
                    msg = "Need a restore actor."
                    raise TypeError(msg)
                if changes is None:
                    msg = "Need a restore changes list."
                    raise TypeError(msg)
                return self.restore_component(zipfile, data, actor, changes)
            return True

    @staticmethod
    def validate_component_urls(component: dict[str, Any]) -> None:
        for field in ("repo", "push"):
            value = component.get(field)
            if not value:
                continue
            try:
                validate_repo_url(value)
            except ValidationError as error:
                raise ValidationError({field: error.messages}) from error

    @overload
    def load_components(
        self,
        zipfile: ZipFile,
        *,
        do_restore: Literal[False] = False,
        actor: None = None,
        changes: None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None: ...

    @overload
    def load_components(
        self,
        zipfile: ZipFile,
        *,
        do_restore: Literal[True],
        actor: User,
        changes: list[Change],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None: ...

    def load_components(
        self,
        zipfile: ZipFile,
        *,
        do_restore: bool = False,
        actor: User | None = None,
        changes: list[Change] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        pending: list[str] = []
        if do_restore:
            if actor is None:
                msg = "Need a restore actor."
                raise TypeError(msg)
            if changes is None:
                msg = "Need a restore changes list."
                raise TypeError(msg)
            restored = 0
            components = self.list_components(zipfile)
            total = len(components)
            for component in components:
                processed = self.load_component(
                    zipfile,
                    component,
                    skip_linked=True,
                    do_restore=True,
                    actor=actor,
                    changes=changes,
                )
                if not processed:
                    pending.append(component)
                else:
                    restored += 1
                    if progress_callback is not None:
                        progress_callback(restored, total)
            for component in pending:
                self.load_component(
                    zipfile,
                    component,
                    skip_linked=False,
                    do_restore=True,
                    actor=actor,
                    changes=changes,
                )
                restored += 1
                if progress_callback is not None:
                    progress_callback(restored, total)
            return

        for component in self.list_components(zipfile):
            processed = self.load_component(
                zipfile,
                component,
                skip_linked=True,
                do_restore=False,
            )
            if not processed:
                pending.append(component)
        for component in pending:
            self.load_component(
                zipfile,
                component,
                skip_linked=False,
                do_restore=False,
            )

    def validate(self) -> None:
        input_file = self.filename or self.fileio
        if input_file is None:
            msg = "Can not validate None file."
            raise TypeError(msg)
        self.validated = False
        with ZipFile(input_file, "r") as zipfile:
            self.validate_zip_members(zipfile)
            self.load_data(zipfile)
            self.load_memory(zipfile)
            self.load_components(zipfile)
        self.validated = True

    def restore_unit(
        self,
        item: dict,
        translation_lookup: dict[int, Translation],
        source_unit_lookup: dict[int, int] | None = None,
    ) -> Unit:
        kwargs = item.copy()
        for skip in ("labels", "comments", "suggestions", "checks", "pending"):
            kwargs.pop(skip, None)
        kwargs["id_hash"] = checksum_to_hash(kwargs["id_hash"])
        kwargs["translation_id"] = translation_lookup[kwargs["translation_id"]].id
        if source_unit_lookup is not None:
            kwargs["source_unit_id"] = source_unit_lookup[item["id_hash"]]
        unit = Unit(**kwargs)
        unit.import_data = item
        return unit

    def restore_user(self, username: str) -> User:
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

    def restore_with_user(
        self, data: dict[str, Any], field: str = "user", remove: str | None = None
    ) -> dict[str, Any]:
        data = data.copy()
        if remove is not None:
            data.pop(remove)
        data[field] = self.restore_user(data[field])
        return data

    def restore_users(self, usernames: list[str]) -> list[User]:
        users = []
        for username in usernames:
            user = self.restore_user(username)
            if user.username == settings.ANONYMOUS_USER_NAME:
                continue
            users.append(user)
        return users

    def restore_team_members(
        self, group: Group, members: list[str | dict[str, Any]]
    ) -> None:
        users: dict[str, User] = {}
        limit_languages: dict[str, list[str]] = {}
        for member in members:
            if isinstance(member, str):
                username = member
                languages = []
            else:
                username = member["username"]
                languages = member.get("limit_languages", [])
            missing_languages = [
                language_code
                for language_code in dict.fromkeys(languages)
                if language_code not in self.languages_cache
            ]
            if missing_languages:
                msg = (
                    f"Unknown language codes in limit_languages for {username!r}: "
                    f"{', '.join(missing_languages)}"
                )
                raise ValueError(msg)
            user = self.restore_user(username)
            if user.username == settings.ANONYMOUS_USER_NAME:
                continue
            if user.username in limit_languages and set(
                limit_languages[user.username]
            ) != set(languages):
                warnings.warn(
                    f"Conflicting language limits for {user.username!r} in backup.",
                    stacklevel=2,
                )
            users[user.username] = user
            limit_languages[user.username] = languages

        with transaction.atomic():
            user_list = list(users.values())
            group.user_set.set(user_list)
            memberships = list(
                TeamMembership.objects.filter(
                    group=group, user__in=user_list
                ).select_related("user")
            )
            membership_ids = [membership.id for membership in memberships]
            if not membership_ids:
                return

            through = TeamMembership.limit_languages.through
            through.objects.filter(teammembership_id__in=membership_ids).delete()
            through.objects.bulk_create(
                through(teammembership_id=membership.id, language_id=language_id)
                for membership in memberships
                for language_id in sorted(
                    {
                        language.id
                        for language in self.get_items_from_cache(
                            self.languages_cache,
                            limit_languages[membership.user.username],
                        )
                    }
                )
            )

    @staticmethod
    def get_items_from_cache(cache: dict[str, Any], keys: list[str]) -> list:
        return [value for key in keys if (value := cache.get(key))]

    def restore_team(self, team: dict) -> None:
        if team["name"] == "Administration":
            group = Group.objects.get(name=team["name"], defining_project=self.project)
        else:
            group = Group(name=team["name"], defining_project=self.project)
            group = Group.objects.bulk_create([group])[0]

        group.language_selection = team["language_selection"]
        group.enforced_2fa = team["enforced_2fa"]

        group.roles.set(self.get_items_from_cache(self.roles_cache, team["roles"]))
        group.components.set(
            self.get_items_from_cache(self.components_cache, team["components"])
        )
        group.languages.set(
            self.get_items_from_cache(self.languages_cache, team["languages"])
        )
        group.admins.set(self.restore_users(team["admins"]))
        self.restore_team_members(group, team["members"])

        autogroups = [
            AutoGroup(match=match, group=group) for match in team["autogroups"]
        ]
        AutoGroup.objects.bulk_create(autogroups)

    def restore_teams(self, data: list[dict]) -> None:
        self.roles_cache = {r.name: r for r in Role.objects.all()}
        self.create_language_cache()
        for team in data:
            self.restore_team(team)

    def restore_pending_unit_changes(
        self,
        data: dict,
        *,
        units: list[Unit],
        pending_unit_change_map: dict[tuple[int, int], list[dict]] | None = None,
    ) -> None:
        if "pending_unit_changes" in data:
            pending_unit_changes: list[PendingUnitChange] = []
            if pending_unit_change_map is None:
                pending_unit_change_map = defaultdict(list)
                for item in data["pending_unit_changes"]:
                    pending_unit_change_map[
                        item["translation_id"], item["unit_id_hash"]
                    ].append(item)
            for unit in units:
                backup_unit = unit.import_data
                pending_unit_changes.extend(
                    (
                        PendingUnitChange(
                            unit=unit,
                            author=self.restore_user(item["author"]),
                            target=item["target"],
                            explanation=item["explanation"],
                            source_unit_explanation=item["source_unit_explanation"],
                            timestamp=item["timestamp"],
                            add_unit=item["add_unit"],
                            state=item["state"],
                        )
                    )
                    for item in pending_unit_change_map.get(
                        (backup_unit["translation_id"], backup_unit["id_hash"]), []
                    )
                )
        else:
            pending_unit_changes = [
                PendingUnitChange(
                    unit=unit,
                    author=unit.get_last_content_change()[0],
                    target=unit.target,
                    explanation=unit.explanation,
                    source_unit_explanation=unit.source_unit.explanation,
                    state=unit.state,
                    add_unit=unit.details.get("add_unit", False),
                )
                for unit in units
                if unit.import_data.get("pending")
            ]

        if pending_unit_changes:
            PendingUnitChange.objects.bulk_create(
                pending_unit_changes, batch_size=self.IMPORT_BATCH_SIZE
            )

    def restore_unit_metadata(self, units: list[Unit]) -> None:
        for unit in units:
            # Labels
            unit.labels.through.objects.bulk_create(
                unit.labels.through(unit=unit, label=self.labels_map[label])
                for label in unit.import_data["labels"]
            )

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
                        # Ignore conflicts here as more users can be mapped to anonymous
                        # in restore_user().
                        Vote.objects.bulk_create(
                            [
                                Vote(
                                    suggestion=suggestion,
                                    **self.restore_with_user(vote),
                                )
                                for vote in suggestion_data[suggestion.target]["votes"]
                            ],
                            ignore_conflicts=True,
                        )

    def clear_unit_import_data(self, units: list[Unit]) -> None:
        for unit in units:
            unit.import_data = {}

    def get_pending_unit_change_map(
        self, data: dict
    ) -> dict[tuple[int, int], list[dict]] | None:
        if "pending_unit_changes" not in data:
            return None

        result: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for item in data["pending_unit_changes"]:
            result[item["translation_id"], item["unit_id_hash"]].append(item)
        return result

    def restore_unit_batch(
        self,
        batch: list[Unit],
        data: dict,
        pending_unit_change_map: dict[tuple[int, int], list[dict]] | None,
    ) -> list[Unit]:
        if not batch:
            return []

        units = Unit.objects.bulk_create(batch, batch_size=self.IMPORT_BATCH_SIZE)
        self.restore_unit_metadata(units)
        self.restore_pending_unit_changes(
            data,
            units=units,
            pending_unit_change_map=pending_unit_change_map,
        )
        self.clear_unit_import_data(units)
        return units

    def restore_source_unit_batch(
        self,
        batch: list[Unit],
        data: dict,
        pending_unit_change_map: dict[tuple[int, int], list[dict]] | None,
        source_unit_lookup: dict[int, int],
    ) -> None:
        if not batch:
            return

        source_units = Unit.objects.bulk_create(
            batch, batch_size=self.IMPORT_BATCH_SIZE
        )
        for unit in source_units:
            unit.source_unit = unit
        Unit.objects.bulk_update(
            source_units, ["source_unit"], batch_size=self.IMPORT_BATCH_SIZE
        )
        source_unit_lookup.update(
            {unit.checksum: unit.id for unit in source_units if unit.id is not None}
        )
        self.restore_unit_metadata(source_units)
        self.restore_pending_unit_changes(
            data,
            units=source_units,
            pending_unit_change_map=pending_unit_change_map,
        )
        self.clear_unit_import_data(source_units)

    def restore_source_units(
        self,
        data: dict,
        *,
        translation_lookup: dict,
        source_translation_id: int,
        pending_unit_change_map: dict[tuple[int, int], list[dict]] | None,
    ) -> dict[int, int]:
        source_unit_lookup: dict[int, int] = {}
        batch: list[Unit] = []
        for item in data["units"]:
            if item["translation_id"] != source_translation_id:
                continue
            batch.append(self.restore_unit(item, translation_lookup))
            if len(batch) >= self.IMPORT_BATCH_SIZE:
                self.restore_source_unit_batch(
                    batch, data, pending_unit_change_map, source_unit_lookup
                )
                batch = []
        self.restore_source_unit_batch(
            batch, data, pending_unit_change_map, source_unit_lookup
        )
        return source_unit_lookup

    def restore_translation_units(
        self,
        data: dict,
        *,
        translation_lookup: dict,
        source_translation_id: int,
        source_unit_lookup: dict[int, int],
        pending_unit_change_map: dict[tuple[int, int], list[dict]] | None,
    ) -> None:
        batch: list[Unit] = []
        for item in data["units"]:
            if item["translation_id"] == source_translation_id:
                continue
            batch.append(
                self.restore_unit(item, translation_lookup, source_unit_lookup)
            )
            if len(batch) >= self.IMPORT_BATCH_SIZE:
                self.restore_unit_batch(batch, data, pending_unit_change_map)
                batch = []
        self.restore_unit_batch(batch, data, pending_unit_change_map)

    def restore_memory(self, zipfile: ZipFile, project: Project) -> None:
        memory = self.load_memory(zipfile)
        memory_batch = []
        for entry in memory:
            restored = Memory(
                origin=entry["origin"],
                source=entry["source"],
                context=entry.get("context", ""),
                target=entry["target"],
                source_language=self.import_language(entry["source_language"]),
                target_language=self.import_language(entry["target_language"]),
                status=entry.get("status", Memory.STATUS_ACTIVE),
            )
            restored.pending_scopes = [
                MemoryScope(scope=MemoryScope.SCOPE_PROJECT, project=project)
            ]
            memory_batch.append(restored)
            if len(memory_batch) >= self.IMPORT_BATCH_SIZE:
                with transaction.atomic():
                    Memory.objects.bulk_create(
                        memory_batch, batch_size=self.IMPORT_BATCH_SIZE
                    )
                    MemoryScope.objects.bulk_create_for_memories(memory_batch)
                memory_batch.clear()
        if memory_batch:
            with transaction.atomic():
                Memory.objects.bulk_create(
                    memory_batch, batch_size=self.IMPORT_BATCH_SIZE
                )
                MemoryScope.objects.bulk_create_for_memories(memory_batch)

        memory.clear()

    @staticmethod
    def get_accessible_linked_component(repo: str, actor: User) -> Component | None:
        try:
            linked_component = Component.objects.get_linked(repo)
        except (Component.DoesNotExist, ValueError):
            return None
        if linked_component is None or linked_component.is_repo_link:
            return None
        if not actor.has_perm("component.edit", linked_component):
            return None
        return linked_component

    def restore_component(
        self,
        zipfile: ZipFile,
        data: dict,
        actor: User,
        changes: list[Change],
    ) -> bool:
        if self.project is None:
            raise TypeError
        original_slug = self.get_component_backup_slug(data["component"])
        kwargs = data["component"].copy()
        self.import_inherited_settings(kwargs)
        source_language = kwargs["source_language"] = self.import_language(
            kwargs["source_language"]
        )

        # Fixup linked components
        if kwargs["repo"].startswith("weblate:"):
            old_slug = f"weblate://{self.data['project']['slug']}/"
            new_slug = f"weblate://{self.project.slug}/"
            kwargs["repo"] = kwargs["repo"].replace(old_slug, new_slug)
            linked_component = self.get_accessible_linked_component(
                kwargs["repo"], actor
            )
            if linked_component is None:
                self.skipped_components.append(original_slug)
                return False
            kwargs["linked_component"] = linked_component

        if "category" in kwargs:
            kwargs["category"] = self.categories_cache[kwargs["category"]]

        component = Component(project=self.project, **kwargs)
        # Trigger pre_save to update git export URL
        pre_save.send(
            sender=component.__class__,
            instance=component,
            raw=False,
            using=None,
            update_fields=None,
        )

        if component.file_format in {"po", "po-mono"} and (
            "file_format_params" not in kwargs
            or kwargs["file_format_params"].get("po_set_language_team") is None
        ):
            # fallback to project setting if not set in backup
            component.file_format_params["po_set_language_team"] = (
                self.set_language_team_project
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
            translation.sync_readonly_check_flag(save=False)
            translation.original_id = item["id"]
            if language == source_language:
                source_translation_id = item["id"]
            translations.append(translation)
        translations = Translation.objects.bulk_create(translations)
        translation_lookup = {
            translation.original_id: translation for translation in translations
        }

        pending_unit_change_map = self.get_pending_unit_change_map(data)

        # Create source units first so translation units can link to them.
        source_unit_lookup = self.restore_source_units(
            data,
            translation_lookup=translation_lookup,
            source_translation_id=source_translation_id,
            pending_unit_change_map=pending_unit_change_map,
        )

        # Create translation units in batches to avoid keeping all Unit objects
        # in memory for components with many languages.
        self.restore_translation_units(
            data,
            translation_lookup=translation_lookup,
            source_translation_id=source_translation_id,
            source_unit_lookup=source_unit_lookup,
            pending_unit_change_map=pending_unit_change_map,
        )
        data["units"].clear()

        # Create screenshots
        screenshots = []
        for item in data["screenshots"]:
            screenshot = Screenshot(
                name=item["name"],
                translation=translation_lookup[item["translation_id"]],
                user=self.restore_user(item["user"]),
                timestamp=item["timestamp"],
            )
            with zipfile.open(os.path.join("screenshots", item["image"])) as handle:
                restored_image = File(
                    BytesIO(handle.read()), name=os.path.basename(item["image"])
                )
                try:
                    validate_bitmap(restored_image)
                except ValidationError as error:
                    raise ValidationError(
                        gettext("Could not restore screenshot %(name)s: %(error)s")
                        % {"name": item["image"], "error": error}
                    ) from error
                screenshot.image.save(
                    os.path.basename(item["image"]), restored_image, save=False
                )
            screenshot.import_data = item
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

        # Trigger checks update, the implementation might have changed
        component.schedule_update_checks()

        if not component.is_repo_link:
            component.configure_repo(pull=False)

        changes.append(
            Change(
                component=component,
                action=ActionEvents.COMPONENT_RESTORE,
                user=actor,
                author=actor,
                details={"original_slug": original_slug},
            )
        )

        # Update cache
        self.components_cache[self.full_slug_without_project(component)] = component
        return True

    def create_language_cache(self) -> None:
        if not self.languages_cache:
            self.languages_cache = {lang.code: lang for lang in Language.objects.all()}

    def import_language(self, code: str) -> Language:
        self.create_language_cache()
        try:
            return self.languages_cache[code]
        except KeyError:
            self.languages_cache[code] = language = Language.objects.auto_get_or_create(
                code
            )
            return language

    def restore_categories(
        self, categories: list[dict], parent_category: Category | None = None
    ) -> None:
        category_objs = []
        child_categories = []
        for category in categories:
            kwargs = category.copy()
            child_categories.append(kwargs.pop("categories"))
            self.import_inherited_settings(kwargs)
            kwargs["category"] = parent_category
            kwargs["project"] = self.project
            category_objs.append(Category(**kwargs))
        category_objs = Category.objects.bulk_create(category_objs)
        for nested_categories, obj in zip(
            child_categories, category_objs, strict=False
        ):
            self.categories_cache[self.full_slug_without_project(obj)] = obj
            self.restore_categories(nested_categories, obj)

    @transaction.atomic
    def restore(
        self,
        project_name: str,
        project_slug: str,
        user: User,
        billing: Billing | None = None,
        workspace: Workspace | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Project:
        if not self.filename:
            msg = "Need a filename string."
            raise ValueError(msg)
        if not self.validated:
            msg = "Project backup has to be validated before restore."
            raise ValueError(msg)
        self.skipped_components.clear()
        with ZipFile(self.filename, "r") as zipfile:
            self.validate_zip_members(zipfile)
            self.load_data(zipfile)
            restore_changes: list[Change] = []

            # Create project
            kwargs = self.data["project"].copy()
            kwargs["name"] = project_name
            kwargs["slug"] = project_slug
            self.import_inherited_settings(kwargs)
            if workspace is not None:
                for field in INHERITABLE_COMPONENT_FLAGS:
                    kwargs[field] = False
                kwargs["workspace"] = workspace
            # the attribute `set_language_team` is present in legacy backups prior to 5.17.1
            self.set_language_team_project = kwargs.pop("set_language_team", False)
            self.project = project = Project.objects.create(**kwargs)

            # Handle billing and ACL (creating user needs access)
            self.project.post_create(user, billing)

            # Create labels
            labels = Label.objects.bulk_create(
                Label(project=project, **entry) for entry in self.data["labels"]
            )
            self.labels_map = {label.name: label for label in labels}
            if "categories" in self.data:
                self.restore_categories(self.data["categories"], None)

            # Import translation memory
            self.restore_memory(zipfile, project)

            # Extract VCS
            project_path = Path(project.full_path)

            def skip_vcs_member(info: ZipInfo) -> bool:
                if info.is_dir() or not info.filename.startswith(self.VCS_PREFIX):
                    return True
                path = info.filename[self.VCS_PREFIX_LEN :]
                # Skip potentially dangerous paths
                return path != os.path.normpath(path) or self.is_unsafe_vcs_path(path)

            def vcs_member_name(info: ZipInfo) -> str:
                return info.filename[self.VCS_PREFIX_LEN :]

            for info, targetpath in iter_safe_zip_members(
                zipfile,
                project_path,
                skip_member=skip_vcs_member,
                member_name=vcs_member_name,
            ):
                extract_zip_member(zipfile, info, targetpath)
                # Create possibly missing refs directory in .git, this is not restored as
                # all references are in packed_refs after `git gc`.
                if vcs_member_name(info).endswith(".git/packed-refs"):
                    git_refs_dir = targetpath.parent / "refs"
                    git_refs_dir.mkdir(parents=True, exist_ok=True)

            # Create components
            self.load_components(
                zipfile,
                do_restore=True,
                actor=user,
                changes=restore_changes,
                progress_callback=progress_callback,
            )

            if "teams" in self.data:
                self.restore_teams(self.data["teams"])

        restore_changes.append(
            Change(
                project=project,
                action=ActionEvents.PROJECT_RESTORE,
                user=user,
                author=user,
                details=self.get_restore_history_details(),
            )
        )
        Change.objects.bulk_create(restore_changes, batch_size=500)

        return self.project

    def store_for_import(self) -> str:
        backup_dir = data_path(PROJECTBACKUP_PREFIX) / "import"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # self.fileio is a file object from upload here
        if self.fileio is None or isinstance(self.fileio, str):
            msg = "Need a file object."
            raise TypeError(msg)
        self.fileio.seek(0)

        timestamp = int(timezone.now().timestamp())
        while (filename := backup_dir / f"{timestamp}.zip").exists():
            timestamp += 1

        with filename.open("xb") as target:
            copyfileobj(self.fileio, target)

        return filename.as_posix()
