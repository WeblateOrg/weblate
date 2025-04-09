# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy, pgettext_lazy


class ActionEvents(IntegerChoices):
    # Translators: Name of event in the history
    UPDATE = 0, gettext_lazy("Resource updated")
    # Translators: Name of event in the history
    COMPLETE = 1, gettext_lazy("Translation completed")
    # Translators: Name of event in the history
    CHANGE = 2, gettext_lazy("Translation changed")
    # Translators: Name of event in the history
    COMMENT = 3, gettext_lazy("Comment added")
    # Translators: Name of event in the history
    SUGGESTION = 4, gettext_lazy("Suggestion added")
    # Translators: Name of event in the history
    NEW = 5, gettext_lazy("Translation added")
    # Translators: Name of event in the history
    AUTO = 6, gettext_lazy("Automatically translated")
    # Translators: Name of event in the history
    ACCEPT = 7, gettext_lazy("Suggestion accepted")
    # Translators: Name of event in the history
    REVERT = 8, gettext_lazy("Translation reverted")
    # Translators: Name of event in the history
    UPLOAD = 9, gettext_lazy("Translation uploaded")
    # Translators: Name of event in the history
    NEW_SOURCE = 13, gettext_lazy("Source string added")
    # Translators: Name of event in the history
    LOCK = 14, gettext_lazy("Component locked")
    # Translators: Name of event in the history
    UNLOCK = 15, gettext_lazy("Component unlocked")
    # Used to be ACTION_DUPLICATE_STRING = 16
    # Translators: Name of event in the history
    COMMIT = 17, gettext_lazy("Changes committed")
    # Translators: Name of event in the history
    PUSH = 18, gettext_lazy("Changes pushed")
    # Translators: Name of event in the history
    RESET = 19, gettext_lazy("Repository reset")
    # Translators: Name of event in the history
    MERGE = 20, gettext_lazy("Repository merged")
    # Translators: Name of event in the history
    REBASE = 21, gettext_lazy("Repository rebased")
    # Translators: Name of event in the history
    FAILED_MERGE = 22, gettext_lazy("Repository merge failed")
    # Translators: Name of event in the history
    FAILED_REBASE = 23, gettext_lazy("Repository rebase failed")
    # Translators: Name of event in the history
    PARSE_ERROR = 24, gettext_lazy("Parsing failed")
    # Translators: Name of event in the history
    REMOVE_TRANSLATION = 25, gettext_lazy("Translation removed")
    # Translators: Name of event in the history
    SUGGESTION_DELETE = 26, gettext_lazy("Suggestion removed")
    # Translators: Name of event in the history
    REPLACE = 27, gettext_lazy("Translation replaced")
    # Translators: Name of event in the history
    FAILED_PUSH = 28, gettext_lazy("Repository push failed")
    # Translators: Name of event in the history
    SUGGESTION_CLEANUP = 29, gettext_lazy("Suggestion removed during cleanup")
    # Translators: Name of event in the history
    SOURCE_CHANGE = 30, gettext_lazy("Source string changed")
    # Translators: Name of event in the history
    NEW_UNIT = 31, gettext_lazy("String added")
    # Translators: Name of event in the history
    BULK_EDIT = 32, gettext_lazy("Bulk status changed")
    # Translators: Name of event in the history
    ACCESS_EDIT = 33, gettext_lazy("Visibility changed")
    # Translators: Name of event in the history
    ADD_USER = 34, gettext_lazy("User added")
    # Translators: Name of event in the history
    REMOVE_USER = 35, gettext_lazy("User removed")
    # Translators: Name of event in the history
    APPROVE = 36, gettext_lazy("Translation approved")
    # Translators: Name of event in the history
    MARKED_EDIT = 37, gettext_lazy("Marked for edit")
    # Translators: Name of event in the history
    REMOVE_COMPONENT = 38, gettext_lazy("Component removed")
    # Translators: Name of event in the history
    REMOVE_PROJECT = 39, gettext_lazy("Project removed")
    # Used to be ACTION_DUPLICATE_LANGUAGE = 40
    # Translators: Name of event in the history
    RENAME_PROJECT = 41, gettext_lazy("Project renamed")
    # Translators: Name of event in the history
    RENAME_COMPONENT = 42, gettext_lazy("Component renamed")
    # Translators: Name of event in the history
    MOVE_COMPONENT = 43, gettext_lazy("Moved component")
    # Used to be ACTION_NEW_STRING = 44
    # Translators: Name of event in the history
    NEW_CONTRIBUTOR = 45, gettext_lazy("Contributor joined")
    # Translators: Name of event in the history
    ANNOUNCEMENT = 46, gettext_lazy("Announcement posted")
    # Translators: Name of event in the history
    ALERT = 47, gettext_lazy("Alert triggered")
    # Translators: Name of event in the history
    ADDED_LANGUAGE = 48, gettext_lazy("Language added")
    # Translators: Name of event in the history
    REQUESTED_LANGUAGE = 49, gettext_lazy("Language requested")
    # Translators: Name of event in the history
    CREATE_PROJECT = 50, gettext_lazy("Project created")
    # Translators: Name of event in the history
    CREATE_COMPONENT = 51, gettext_lazy("Component created")
    # Translators: Name of event in the history
    INVITE_USER = 52, gettext_lazy("User invited")
    # Translators: Name of event in the history
    HOOK = 53, gettext_lazy("Repository notification received")
    # Translators: Name of event in the history
    REPLACE_UPLOAD = 54, gettext_lazy("Translation replaced file by upload")
    # Translators: Name of event in the history
    LICENSE_CHANGE = 55, gettext_lazy("License changed")
    # Translators: Name of event in the history
    AGREEMENT_CHANGE = 56, gettext_lazy("Contributor license agreement changed")
    # Translators: Name of event in the history
    SCREENSHOT_ADDED = 57, gettext_lazy("Screenshot added")
    # Translators: Name of event in the history
    SCREENSHOT_UPLOADED = 58, gettext_lazy("Screenshot uploaded")
    # Translators: Name of event in the history
    STRING_REPO_UPDATE = 59, gettext_lazy("String updated in the repository")
    # Translators: Name of event in the history
    ADDON_CREATE = 60, gettext_lazy("Add-on installed")
    # Translators: Name of event in the history
    ADDON_CHANGE = 61, gettext_lazy("Add-on configuration changed")
    # Translators: Name of event in the history
    ADDON_REMOVE = 62, gettext_lazy("Add-on uninstalled")
    # Translators: Name of event in the history
    STRING_REMOVE = 63, gettext_lazy("String removed")
    # Translators: Name of event in the history
    COMMENT_DELETE = 64, gettext_lazy("Comment removed")
    # Translators: Name of event in the history
    COMMENT_RESOLVE = (
        65,
        pgettext_lazy("Name of event in the history", "Comment resolved"),
    )
    # Translators: Name of event in the history
    EXPLANATION = 66, gettext_lazy("Explanation updated")
    # Translators: Name of event in the history
    REMOVE_CATEGORY = 67, gettext_lazy("Category removed")
    # Translators: Name of event in the history
    RENAME_CATEGORY = 68, gettext_lazy("Category renamed")
    # Translators: Name of event in the history
    MOVE_CATEGORY = 69, gettext_lazy("Category moved")
    # Translators: Name of event in the history
    SAVE_FAILED = 70, gettext_lazy("Saving string failed")
    # Translators: Name of event in the history
    NEW_UNIT_REPO = 71, gettext_lazy("String added in the repository")
    # Translators: Name of event in the history
    STRING_UPLOAD_UPDATE = 72, gettext_lazy("String updated in the upload")
    # Translators: Name of event in the history
    NEW_UNIT_UPLOAD = 73, gettext_lazy("String added in the upload")
    # Translators: Name of event in the history
    SOURCE_UPLOAD = 74, gettext_lazy("Translation updated by source upload")
    # Translators: Name of event in the history
    COMPLETED_COMPONENT = 75, gettext_lazy("Component translation completed")
    # Translators: Name of event in the history
    ENFORCED_CHECK = 76, gettext_lazy("Applied enforced check")
    # Translators: Name of event in the history
    PROPAGATED_EDIT = 77, gettext_lazy("Propagated change")
    # Translators: Name of event in the history
    FILE_UPLOAD = 78, gettext_lazy("File uploaded")
    # Translators: Name of event in the history
    EXTRA_FLAGS = 79, gettext_lazy("Extra flags updated")


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
