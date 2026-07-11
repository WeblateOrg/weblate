# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy, pgettext_lazy

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise


def get_change_action_identifier(action: object) -> str:
    """Return action identifier used in Fedora Messaging topics."""
    return str(action).lower().replace(" ", "_")


class ActionEvents(IntegerChoices):
    description: StrOrPromise

    def __new__(cls, value: int, description: StrOrPromise) -> Self:
        obj = cast("Self", int.__new__(cls, value))
        obj._value_ = value
        obj.description = description
        return obj

    # Translators: Name and description of event in the history
    UPDATE = (
        0,
        gettext_lazy("A translation file was synchronized with its repository."),
        gettext_lazy("Resource updated"),
    )
    # Translators: Name and description of event in the history
    COMPLETE = (
        1,
        gettext_lazy(
            "A language translation became fully translated after an individual edit. "
            "Automatic translation, uploads, and bulk edits do not emit this event."
        ),
        gettext_lazy("Translation completed"),
    )
    # Translators: Name and description of event in the history
    CHANGE = (
        2,
        gettext_lazy("An existing translation was edited by a user."),
        gettext_lazy("Translation changed"),
    )
    # Translators: Name and description of event in the history
    COMMENT = (
        3,
        gettext_lazy("A comment was added to a string."),
        gettext_lazy("Comment added"),
    )
    # Translators: Name and description of event in the history
    SUGGESTION = (
        4,
        gettext_lazy("A translation suggestion was added."),
        gettext_lazy("Suggestion added"),
    )
    # Translators: Name and description of event in the history
    NEW = (
        5,
        gettext_lazy("A previously untranslated string was translated by a user."),
        gettext_lazy("Translation added"),
    )
    # Translators: Name and description of event in the history
    AUTO = (
        6,
        gettext_lazy(
            "A translation was added or changed by automatic translation. This is "
            "emitted instead of Translation added or Translation changed."
        ),
        gettext_lazy("Automatically translated"),
    )
    # Translators: Name and description of event in the history
    ACCEPT = (
        7,
        gettext_lazy("A translation suggestion was accepted as the translation."),
        gettext_lazy("Suggestion accepted"),
    )
    # Translators: Name and description of event in the history
    REVERT = (
        8,
        gettext_lazy("A translation was restored to an earlier value."),
        gettext_lazy("Translation reverted"),
    )
    # Translators: Name and description of event in the history
    UPLOAD = (
        9,
        gettext_lazy(
            "A translation was added or changed by a translation file upload. This is "
            "emitted instead of Translation added or Translation changed."
        ),
        gettext_lazy("Translation uploaded"),
    )
    # Translators: Name and description of event in the history
    NEW_SOURCE = (
        13,
        gettext_lazy("A source string was added outside repository or upload updates."),
        gettext_lazy("Source string added"),
    )
    # Translators: Name and description of event in the history
    LOCK = (
        14,
        gettext_lazy("A component was locked for translation."),
        gettext_lazy("Component locked"),
    )
    # Translators: Name and description of event in the history
    UNLOCK = (
        15,
        gettext_lazy("A component was unlocked for translation."),
        gettext_lazy("Component unlocked"),
    )
    # Used to be ACTION_DUPLICATE_STRING = 16
    # Translators: Name and description of event in the history
    COMMIT = (
        17,
        gettext_lazy("Pending component changes were committed."),
        gettext_lazy("Changes committed"),
    )
    # Translators: Name and description of event in the history
    PUSH = (
        18,
        gettext_lazy("Repository changes were pushed upstream."),
        gettext_lazy("Changes pushed"),
    )
    # Translators: Name and description of event in the history
    RESET = (
        19,
        gettext_lazy("A repository was reset to its upstream state."),
        gettext_lazy("Repository reset"),
    )
    # Translators: Name and description of event in the history
    MERGE = (
        20,
        gettext_lazy("Upstream repository changes were merged."),
        gettext_lazy("Repository merged"),
    )
    # Translators: Name and description of event in the history
    REBASE = (
        21,
        gettext_lazy("Repository changes were rebased on upstream."),
        gettext_lazy("Repository rebased"),
    )
    # Translators: Name and description of event in the history
    FAILED_MERGE = (
        22,
        gettext_lazy("Merging upstream repository changes failed."),
        gettext_lazy("Repository merge failed"),
    )
    # Translators: Name and description of event in the history
    FAILED_REBASE = (
        23,
        gettext_lazy("Rebasing repository changes failed."),
        gettext_lazy("Repository rebase failed"),
    )
    # Translators: Name and description of event in the history
    PARSE_ERROR = (
        24,
        gettext_lazy("Weblate could not parse a translation file."),
        gettext_lazy("Parsing failed"),
    )
    # Translators: Name and description of event in the history
    REMOVE_TRANSLATION = (
        25,
        gettext_lazy("A language translation was removed."),
        gettext_lazy("Translation removed"),
    )
    # Translators: Name and description of event in the history
    SUGGESTION_DELETE = (
        26,
        gettext_lazy("A translation suggestion was removed."),
        gettext_lazy("Suggestion removed"),
    )
    # Translators: Name and description of event in the history
    REPLACE = (
        27,
        gettext_lazy(
            "A translation was changed by a search-and-replace operation. This is "
            "emitted instead of Translation changed."
        ),
        gettext_lazy("Translation replaced"),
    )
    # Translators: Name and description of event in the history
    FAILED_PUSH = (
        28,
        gettext_lazy("Pushing repository changes upstream failed."),
        gettext_lazy("Repository push failed"),
    )
    # Translators: Name and description of event in the history
    SUGGESTION_CLEANUP = (
        29,
        gettext_lazy("An obsolete translation suggestion was removed during cleanup."),
        gettext_lazy("Suggestion removed during cleanup"),
    )
    # Translators: Name and description of event in the history
    SOURCE_CHANGE = (
        30,
        gettext_lazy("A source string was edited in Weblate."),
        gettext_lazy("Source string changed"),
    )
    # Translators: Name and description of event in the history
    NEW_UNIT = (
        31,
        gettext_lazy("A new string was added in Weblate."),
        gettext_lazy("String added"),
    )
    # Translators: Name and description of event in the history
    BULK_EDIT = (
        32,
        gettext_lazy(
            "The translation state of one or more strings was changed in bulk."
        ),
        gettext_lazy("Bulk status changed"),
    )
    # Translators: Name and description of event in the history
    ACCESS_EDIT = (
        33,
        gettext_lazy("Project or component visibility was changed."),
        gettext_lazy("Visibility changed"),
    )
    # Translators: Name and description of event in the history
    ADD_USER = (
        34,
        gettext_lazy("A user was granted access."),
        gettext_lazy("User added"),
    )
    # Translators: Name and description of event in the history
    REMOVE_USER = (
        35,
        gettext_lazy("A user's access was removed."),
        gettext_lazy("User removed"),
    )
    # Translators: Name and description of event in the history
    APPROVE = (
        36,
        gettext_lazy("A translation was approved during review."),
        gettext_lazy("Translation approved"),
    )
    # Translators: Name and description of event in the history
    MARKED_EDIT = (
        37,
        gettext_lazy("A translation was marked as needing editing."),
        gettext_lazy("Marked for edit"),
    )
    # Translators: Name and description of event in the history
    REMOVE_COMPONENT = (
        38,
        gettext_lazy("A translation component was removed."),
        gettext_lazy("Component removed"),
    )
    # Translators: Name and description of event in the history
    REMOVE_PROJECT = (
        39,
        gettext_lazy("A translation project was removed."),
        gettext_lazy("Project removed"),
    )
    # Used to be ACTION_DUPLICATE_LANGUAGE = 40
    # Translators: Name and description of event in the history
    RENAME_PROJECT = (
        41,
        gettext_lazy("A translation project was renamed."),
        gettext_lazy("Project renamed"),
    )
    # Translators: Name and description of event in the history
    RENAME_COMPONENT = (
        42,
        gettext_lazy("A translation component was renamed."),
        gettext_lazy("Component renamed"),
    )
    # Translators: Name and description of event in the history
    MOVE_COMPONENT = (
        43,
        gettext_lazy("A component was moved within a project."),
        gettext_lazy("Moved component"),
    )
    # Used to be ACTION_NEW_STRING = 44
    # Translators: Name and description of event in the history
    NEW_CONTRIBUTOR = (
        45,
        gettext_lazy("A user made their first contribution to a translation."),
        gettext_lazy("Contributor joined"),
    )
    # Translators: Name and description of event in the history
    ANNOUNCEMENT = (
        46,
        gettext_lazy("An announcement was posted."),
        gettext_lazy("Announcement posted"),
    )
    # Translators: Name and description of event in the history
    ALERT = (
        47,
        gettext_lazy("A component alert was triggered."),
        gettext_lazy("Alert triggered"),
    )
    # Translators: Name and description of event in the history
    ADDED_LANGUAGE = (
        48,
        gettext_lazy("A language translation was added."),
        gettext_lazy("Language added"),
    )
    # Translators: Name and description of event in the history
    REQUESTED_LANGUAGE = (
        49,
        gettext_lazy("A user requested a new language."),
        gettext_lazy("Language requested"),
    )
    # Translators: Name and description of event in the history
    CREATE_PROJECT = (
        50,
        gettext_lazy("A translation project was created."),
        gettext_lazy("Project created"),
    )
    # Translators: Name and description of event in the history
    CREATE_COMPONENT = (
        51,
        gettext_lazy("A translation component was created."),
        gettext_lazy("Component created"),
    )
    # Translators: Name and description of event in the history
    INVITE_USER = (
        52,
        gettext_lazy("A user was invited to a project."),
        gettext_lazy("User invited"),
    )
    # Translators: Name and description of event in the history
    HOOK = (
        53,
        gettext_lazy("Weblate received a repository notification from a code host."),
        gettext_lazy("Repository notification received"),
    )
    # Translators: Name and description of event in the history
    REPLACE_UPLOAD = (
        54,
        gettext_lazy("A translation file was replaced by an uploaded file."),
        gettext_lazy("Translation replaced file by upload"),
    )
    # Translators: Name and description of event in the history
    LICENSE_CHANGE = (
        55,
        gettext_lazy("Project or component license information changed."),
        gettext_lazy("License changed"),
    )
    # Translators: Name and description of event in the history
    AGREEMENT_CHANGE = (
        56,
        gettext_lazy("The contributor license agreement was changed."),
        gettext_lazy("Contributor license agreement changed"),
    )
    # Translators: Name and description of event in the history
    SCREENSHOT_ADDED = (
        57,
        gettext_lazy("A screenshot was associated with a string."),
        gettext_lazy("Screenshot added"),
    )
    # Translators: Name and description of event in the history
    SCREENSHOT_UPLOADED = (
        58,
        gettext_lazy("A screenshot image was uploaded."),
        gettext_lazy("Screenshot uploaded"),
    )
    # Translators: Name and description of event in the history
    STRING_REPO_UPDATE = (
        59,
        gettext_lazy("A string was changed while synchronizing from the repository."),
        gettext_lazy("String updated in the repository"),
    )
    # Translators: Name and description of event in the history
    ADDON_CREATE = (
        60,
        gettext_lazy("An add-on was installed."),
        gettext_lazy("Add-on installed"),
    )
    # Translators: Name and description of event in the history
    ADDON_CHANGE = (
        61,
        gettext_lazy("An add-on's configuration was changed."),
        gettext_lazy("Add-on configuration changed"),
    )
    # Translators: Name and description of event in the history
    ADDON_REMOVE = (
        62,
        gettext_lazy("An add-on was uninstalled."),
        gettext_lazy("Add-on uninstalled"),
    )
    # Translators: Name and description of event in the history
    STRING_REMOVE = (
        63,
        gettext_lazy("A string was removed from a translation."),
        gettext_lazy("String removed"),
    )
    # Translators: Name and description of event in the history
    COMMENT_DELETE = (
        64,
        gettext_lazy("A string comment was removed."),
        gettext_lazy("Comment removed"),
    )
    # Translators: Name and description of event in the history
    COMMENT_RESOLVE = (
        65,
        gettext_lazy("A string comment was marked as resolved."),
        pgettext_lazy("Name of event in the history", "Comment resolved"),
    )
    # Translators: Name and description of event in the history
    EXPLANATION = (
        66,
        gettext_lazy("The explanation for a source string was updated."),
        gettext_lazy("Explanation updated"),
    )
    # Translators: Name and description of event in the history
    REMOVE_CATEGORY = (
        67,
        gettext_lazy("A component category was removed."),
        gettext_lazy("Category removed"),
    )
    # Translators: Name and description of event in the history
    RENAME_CATEGORY = (
        68,
        gettext_lazy("A component category was renamed."),
        gettext_lazy("Category renamed"),
    )
    # Translators: Name and description of event in the history
    MOVE_CATEGORY = (
        69,
        gettext_lazy("A component category was moved."),
        gettext_lazy("Category moved"),
    )
    # Translators: Name and description of event in the history
    SAVE_FAILED = (
        70,
        gettext_lazy("Weblate could not save a changed string."),
        gettext_lazy("Saving string failed"),
    )
    # Translators: Name and description of event in the history
    NEW_UNIT_REPO = (
        71,
        gettext_lazy("A new string was found while synchronizing from the repository."),
        gettext_lazy("String added in the repository"),
    )
    # Translators: Name and description of event in the history
    STRING_UPLOAD_UPDATE = (
        72,
        gettext_lazy("A string was changed while processing an uploaded file."),
        gettext_lazy("String updated in the upload"),
    )
    # Translators: Name and description of event in the history
    NEW_UNIT_UPLOAD = (
        73,
        gettext_lazy("A new string was found while processing an uploaded file."),
        gettext_lazy("String added in the upload"),
    )
    # Translators: Name and description of event in the history
    SOURCE_UPLOAD = (
        74,
        gettext_lazy("A translation was synchronized after uploading a source file."),
        gettext_lazy("Translation updated by source upload"),
    )
    # Translators: Name and description of event in the history
    COMPLETED_COMPONENT = (
        75,
        gettext_lazy(
            "All language translations in a component became fully translated after "
            "an individual edit. Automatic translation, uploads, and bulk edits do not "
            "emit this event."
        ),
        gettext_lazy("Component translation completed"),
    )
    # Translators: Name and description of event in the history
    ENFORCED_CHECK = (
        76,
        gettext_lazy(
            "A translation was marked as needing editing by an enforced check."
        ),
        gettext_lazy("Applied enforced check"),
    )
    # Translators: Name and description of event in the history
    PROPAGATED_EDIT = (
        77,
        gettext_lazy("A translation edit was propagated to another matching string."),
        gettext_lazy("Propagated change"),
    )
    # Translators: Name and description of event in the history
    FILE_UPLOAD = (
        78,
        gettext_lazy("A file was uploaded to a translation."),
        gettext_lazy("File uploaded"),
    )
    # Translators: Name and description of event in the history
    EXTRA_FLAGS = (
        79,
        gettext_lazy("Additional source-string flags were updated."),
        gettext_lazy("Extra flags updated"),
    )
    # Translators: Name and description of event in the history
    FONT_CREATE = (
        80,
        gettext_lazy("A font was uploaded."),
        gettext_lazy("Font uploaded"),
    )
    # Translators: Name and description of event in the history
    FONT_CHANGE = (
        81,
        gettext_lazy("An uploaded font was changed."),
        gettext_lazy("Font changed"),
    )
    # Translators: Name and description of event in the history
    FONT_REMOVE = (
        82,
        gettext_lazy("An uploaded font was removed."),
        gettext_lazy("Font removed"),
    )
    # Translators: Name and description of event in the history
    FORCE_SYNC = (
        83,
        gettext_lazy(
            "Translation files were forcibly synchronized with the repository."
        ),
        gettext_lazy("Forced synchronization of translations"),
    )
    # Translators: Name and description of event in the history
    FORCE_SCAN = (
        84,
        gettext_lazy("Translation files were forcibly rescanned for changes."),
        gettext_lazy("Forced rescan of translations"),
    )
    # Translators: Name and description of event in the history
    SCREENSHOT_REMOVED = (
        85,
        gettext_lazy("A screenshot was removed."),
        gettext_lazy("Screenshot removed"),
    )
    # Translators: Name and description of event in the history
    LABEL_ADD = (
        86,
        gettext_lazy("A label was added to a string."),
        gettext_lazy("Label added"),
    )
    # Translators: Name and description of event in the history
    LABEL_REMOVE = (
        87,
        gettext_lazy("A label was removed from a string."),
        gettext_lazy("Label removed"),
    )
    # Translators: Name and description of event in the history
    REPO_CLEANUP = (
        88,
        gettext_lazy("The repository working tree was cleaned up."),
        gettext_lazy("Repository cleanup"),
    )
    # Translators: Name and description of event in the history
    NEW_SOURCE_UPLOAD = (
        89,
        gettext_lazy("A source string was added while processing an uploaded file."),
        gettext_lazy("Source string added in the upload"),
    )
    # Translators: Name and description of event in the history
    NEW_SOURCE_REPO = (
        90,
        gettext_lazy(
            "A source string was added while synchronizing from the repository."
        ),
        gettext_lazy("Source string added in the repository"),
    )
    # Translators: Name and description of event in the history
    PROJECT_BACKUP = (
        91,
        gettext_lazy("A project backup was created."),
        gettext_lazy("Project backed up"),
    )
    # Translators: Name and description of event in the history
    PROJECT_RESTORE = (
        92,
        gettext_lazy("A project was restored from a backup."),
        gettext_lazy("Project restored"),
    )
    # Translators: Name and description of event in the history
    COMPONENT_RESTORE = (
        93,
        gettext_lazy("A component was restored from a backup."),
        gettext_lazy("Component restored"),
    )
    # Translators: Name and description of event in the history
    USER_REVERT = (
        94,
        gettext_lazy("All selected edits by a user were reverted."),
        gettext_lazy("User edit reverted"),
    )
    # Translators: Name and description of event in the history
    PROJECT_SETTING_CHANGE = (
        95,
        gettext_lazy("A project setting was changed."),
        gettext_lazy("Project setting changed"),
    )
    # Translators: Name and description of event in the history
    COMPONENT_SETTING_CHANGE = (
        96,
        gettext_lazy("A component setting was changed."),
        gettext_lazy("Component setting changed"),
    )
    # Translators: Name and description of event in the history
    USER_ACCESS_CHANGE = (
        97,
        gettext_lazy("A user's access permissions were changed."),
        gettext_lazy("User access changed"),
    )
    # Translators: Name and description of event in the history
    CREATE_WORKSPACE = (
        98,
        gettext_lazy("A workspace was created."),
        gettext_lazy("Workspace created"),
    )
    # Translators: Name and description of event in the history
    WORKSPACE_SETTING_CHANGE = (
        99,
        gettext_lazy("A workspace setting was changed."),
        gettext_lazy("Workspace setting changed"),
    )
    # Translators: Name and description of event in the history
    MOVE_PROJECT = (
        100,
        gettext_lazy("A project was moved into or out of a workspace."),
        gettext_lazy("Project moved"),
    )
    # Translators: Name and description of event in the history
    REMOTE_UPDATE = (
        101,
        gettext_lazy("A remote repository update was completed."),
        gettext_lazy("Remote repository updated"),
    )
    # Translators: Name and description of event in the history
    FAILED_REMOTE_UPDATE = (
        102,
        gettext_lazy("Updating a remote repository failed."),
        gettext_lazy("Remote repository update failed"),
    )
    # Translators: Name and description of event in the history
    ALERT_DISMISSED = (
        103,
        gettext_lazy("A component alert was dismissed."),
        gettext_lazy("Alert dismissed"),
    )
    # Translators: Name and description of event in the history
    ALERT_REOPENED = (
        104,
        gettext_lazy("A component alert was reopened after its context changed."),
        gettext_lazy("Alert reopened"),
    )


# Actions which are logged
ACTIONS_LOG = {
    ActionEvents.RESET,
    ActionEvents.REMOVE_TRANSLATION,
    ActionEvents.ACCESS_EDIT,
    ActionEvents.ADD_USER,
    ActionEvents.REMOVE_USER,
    ActionEvents.USER_ACCESS_CHANGE,
    ActionEvents.REMOVE_COMPONENT,
    ActionEvents.REMOVE_PROJECT,
    ActionEvents.RENAME_PROJECT,
    ActionEvents.RENAME_COMPONENT,
    ActionEvents.MOVE_COMPONENT,
    ActionEvents.ADDED_LANGUAGE,
    ActionEvents.CREATE_PROJECT,
    ActionEvents.CREATE_COMPONENT,
    ActionEvents.REMOVE_CATEGORY,
    ActionEvents.RENAME_CATEGORY,
    ActionEvents.MOVE_CATEGORY,
    ActionEvents.PROJECT_BACKUP,
    ActionEvents.PROJECT_RESTORE,
    ActionEvents.COMPONENT_RESTORE,
    ActionEvents.PROJECT_SETTING_CHANGE,
    ActionEvents.COMPONENT_SETTING_CHANGE,
    ActionEvents.CREATE_WORKSPACE,
    ActionEvents.WORKSPACE_SETTING_CHANGE,
    ActionEvents.MOVE_PROJECT,
    ActionEvents.ALERT_DISMISSED,
    ActionEvents.ALERT_REOPENED,
}


# Actions which can be reverted
ACTIONS_REVERTABLE = {
    ActionEvents.ACCEPT,
    ActionEvents.REVERT,
    ActionEvents.CHANGE,
    ActionEvents.UPLOAD,
    ActionEvents.NEW,
    ActionEvents.REPLACE,
    ActionEvents.AUTO,
    ActionEvents.APPROVE,
    ActionEvents.MARKED_EDIT,
    ActionEvents.PROPAGATED_EDIT,
    ActionEvents.STRING_REPO_UPDATE,
    ActionEvents.STRING_UPLOAD_UPDATE,
    ActionEvents.USER_REVERT,
}

# Content changes considered when looking for last author
ACTIONS_CONTENT = {
    ActionEvents.CHANGE,
    ActionEvents.NEW,
    ActionEvents.AUTO,
    ActionEvents.ACCEPT,
    ActionEvents.REVERT,
    ActionEvents.UPLOAD,
    ActionEvents.REPLACE,
    ActionEvents.BULK_EDIT,
    ActionEvents.APPROVE,
    ActionEvents.MARKED_EDIT,
    ActionEvents.PROPAGATED_EDIT,
    ActionEvents.SOURCE_CHANGE,
    ActionEvents.EXPLANATION,
    ActionEvents.EXTRA_FLAGS,
    ActionEvents.NEW_UNIT,
    ActionEvents.ENFORCED_CHECK,
    ActionEvents.USER_REVERT,
}

# Actions shown on the repository management page
ACTIONS_REPOSITORY = {
    ActionEvents.COMMIT,
    ActionEvents.PUSH,
    ActionEvents.RESET,
    ActionEvents.MERGE,
    ActionEvents.REBASE,
    ActionEvents.FAILED_MERGE,
    ActionEvents.FAILED_REBASE,
    ActionEvents.FAILED_PUSH,
    ActionEvents.LOCK,
    ActionEvents.UNLOCK,
    ActionEvents.HOOK,
    ActionEvents.FILE_UPLOAD,
    ActionEvents.FORCE_SYNC,
    ActionEvents.FORCE_SCAN,
    ActionEvents.REPO_CLEANUP,
    ActionEvents.REMOTE_UPDATE,
    ActionEvents.FAILED_REMOTE_UPDATE,
}

# Actions considered when computing repository status from history
ACTIONS_REPOSITORY_STATUS = ACTIONS_REPOSITORY - {
    ActionEvents.REMOTE_UPDATE,
    ActionEvents.FAILED_REMOTE_UPDATE,
}

# Actions where target is rendered as translation string
ACTIONS_SHOW_CONTENT = {
    ActionEvents.SUGGESTION,
    ActionEvents.SUGGESTION_DELETE,
    ActionEvents.SUGGESTION_CLEANUP,
    ActionEvents.BULK_EDIT,
    ActionEvents.NEW_UNIT,
    ActionEvents.STRING_REPO_UPDATE,
    ActionEvents.NEW_UNIT_REPO,
    ActionEvents.STRING_UPLOAD_UPDATE,
    ActionEvents.NEW_UNIT_UPLOAD,
}

# Actions indicating a repository merge failure
ACTIONS_MERGE_FAILURE = {
    ActionEvents.FAILED_MERGE,
    ActionEvents.FAILED_REBASE,
    ActionEvents.FAILED_PUSH,
}

ACTIONS_ADDON = {
    ActionEvents.ADDON_CREATE,
    ActionEvents.ADDON_CHANGE,
    ActionEvents.ADDON_REMOVE,
}
