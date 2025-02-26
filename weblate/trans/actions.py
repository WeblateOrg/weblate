# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy, pgettext_lazy


class ActionEvents(IntegerChoices):
    # Translators: Name of event in the history
    ACTION_UPDATE = 0, gettext_lazy("Resource updated")
    ACTION_COMPLETE = 1, gettext_lazy("Translation completed")
    ACTION_CHANGE = 2, gettext_lazy("Translation changed")
    ACTION_NEW = 5, gettext_lazy("Translation added")
    ACTION_COMMENT = 3, gettext_lazy("Comment added")
    ACTION_SUGGESTION = 4, gettext_lazy("Suggestion added")
    ACTION_AUTO = 6, gettext_lazy("Automatically translated")
    ACTION_ACCEPT = 7, gettext_lazy("Suggestion accepted")
    ACTION_REVERT = 8, gettext_lazy("Translation reverted")
    ACTION_UPLOAD = 9, gettext_lazy("Translation uploaded")
    ACTION_NEW_SOURCE = 13, gettext_lazy("Source string added")
    ACTION_LOCK = 14, gettext_lazy("Component locked")
    ACTION_UNLOCK = 15, gettext_lazy("Component unlocked")
    # Used to be ACTION_DUPLICATE_STRING = 16
    ACTION_COMMIT = 17, gettext_lazy("Changes committed")
    ACTION_PUSH = 18, gettext_lazy("Changes pushed")
    ACTION_RESET = 19, gettext_lazy("Repository reset")
    ACTION_MERGE = 20, gettext_lazy("Repository merged")
    ACTION_REBASE = 21, gettext_lazy("Repository rebased")
    ACTION_FAILED_MERGE = 22, gettext_lazy("Repository merge failed")
    ACTION_FAILED_REBASE = 23, gettext_lazy("Repository rebase failed")
    ACTION_PARSE_ERROR = 24, gettext_lazy("Parsing failed")
    ACTION_REMOVE_TRANSLATION = 25, gettext_lazy("Translation removed")
    ACTION_SUGGESTION_DELETE = 26, gettext_lazy("Suggestion removed")
    ACTION_REPLACE = 27, gettext_lazy("Translation replaced")
    ACTION_FAILED_PUSH = 28, gettext_lazy("Repository push failed")
    ACTION_SUGGESTION_CLEANUP = 29, gettext_lazy("Suggestion removed during cleanup")
    ACTION_SOURCE_CHANGE = 30, gettext_lazy("Source string changed")
    ACTION_NEW_UNIT = 31, gettext_lazy("String added")
    ACTION_BULK_EDIT = 32, gettext_lazy("Bulk status changed")
    ACTION_ACCESS_EDIT = 33, gettext_lazy("Visibility changed")
    ACTION_ADD_USER = 34, gettext_lazy("User added")
    ACTION_REMOVE_USER = 35, gettext_lazy("User removed")
    ACTION_APPROVE = 36, gettext_lazy("Translation approved")
    ACTION_MARKED_EDIT = 37, gettext_lazy("Marked for edit")
    ACTION_REMOVE_COMPONENT = 38, gettext_lazy("Component removed")
    ACTION_REMOVE_PROJECT = 39, gettext_lazy("Project removed")
    # Used to be ACTION_DUPLICATE_LANGUAGE = 40
    ACTION_RENAME_PROJECT = 41, gettext_lazy("Project renamed")
    ACTION_RENAME_COMPONENT = 42, gettext_lazy("Component renamed")
    ACTION_MOVE_COMPONENT = 43, gettext_lazy("Moved component")
    # Used to be ACTION_NEW_STRING = 44
    ACTION_NEW_CONTRIBUTOR = 45, gettext_lazy("Contributor joined")
    ACTION_ANNOUNCEMENT = 46, gettext_lazy("Announcement posted")
    ACTION_ALERT = 47, gettext_lazy("Alert triggered")
    ACTION_ADDED_LANGUAGE = 48, gettext_lazy("Language added")
    ACTION_REQUESTED_LANGUAGE = 49, gettext_lazy("Language requested")
    ACTION_CREATE_PROJECT = 50, gettext_lazy("Project created")
    ACTION_CREATE_COMPONENT = 51, gettext_lazy("Component created")
    ACTION_INVITE_USER = 52, gettext_lazy("User invited")
    ACTION_HOOK = 53, gettext_lazy("Repository notification received")
    ACTION_REPLACE_UPLOAD = 54, gettext_lazy("Translation replaced file by upload")
    ACTION_LICENSE_CHANGE = 55, gettext_lazy("License changed")
    ACTION_AGREEMENT_CHANGE = 56, gettext_lazy("Contributor license agreement changed")
    ACTION_SCREENSHOT_ADDED = 57, gettext_lazy("Screenshot added")
    ACTION_SCREENSHOT_UPLOADED = 58, gettext_lazy("Screenshot uploaded")
    ACTION_STRING_REPO_UPDATE = 59, gettext_lazy("String updated in the repository")
    ACTION_ADDON_CREATE = 60, gettext_lazy("Add-on installed")
    ACTION_ADDON_CHANGE = 61, gettext_lazy("Add-on configuration changed")
    ACTION_ADDON_REMOVE = 62, gettext_lazy("Add-on uninstalled")
    ACTION_STRING_REMOVE = 63, gettext_lazy("String removed")
    ACTION_COMMENT_DELETE = 64, gettext_lazy("Comment removed")
    ACTION_COMMENT_RESOLVE = (
        65,
        pgettext_lazy("Name of event in the history", "Comment resolved"),
    )
    ACTION_EXPLANATION = 66, gettext_lazy("Explanation updated")
    ACTION_REMOVE_CATEGORY = 67, gettext_lazy("Category removed")
    ACTION_RENAME_CATEGORY = 68, gettext_lazy("Category renamed")
    ACTION_MOVE_CATEGORY = 69, gettext_lazy("Category moved")
    ACTION_SAVE_FAILED = 70, gettext_lazy("Saving string failed")
    ACTION_NEW_UNIT_REPO = 71, gettext_lazy("String added in the repository")
    ACTION_STRING_UPLOAD_UPDATE = 72, gettext_lazy("String updated in the upload")
    ACTION_NEW_UNIT_UPLOAD = 73, gettext_lazy("String added in the upload")
    ACTION_SOURCE_UPLOAD = 74, gettext_lazy("Translation updated by source upload")
    ACTION_COMPLETED_COMPONENT = 75, gettext_lazy("Component translation completed")
    ACTION_ENFORCED_CHECK = 76, gettext_lazy("Applied enforced check")
    ACTION_PROPAGATED_EDIT = 77, gettext_lazy("Propagated change")


# Actions which can be reverted
ACTIONS_REVERTABLE = {
    ActionEvents.ACTION_ACCEPT,
    ActionEvents.ACTION_REVERT,
    ActionEvents.ACTION_CHANGE,
    ActionEvents.ACTION_UPLOAD,
    ActionEvents.ACTION_NEW,
    ActionEvents.ACTION_REPLACE,
    ActionEvents.ACTION_AUTO,
    ActionEvents.ACTION_APPROVE,
    ActionEvents.ACTION_MARKED_EDIT,
    ActionEvents.ACTION_PROPAGATED_EDIT,
    ActionEvents.ACTION_STRING_REPO_UPDATE,
    ActionEvents.ACTION_STRING_UPLOAD_UPDATE,
}

# Content changes considered when looking for last author
ACTIONS_CONTENT = {
    ActionEvents.ACTION_CHANGE,
    ActionEvents.ACTION_NEW,
    ActionEvents.ACTION_AUTO,
    ActionEvents.ACTION_ACCEPT,
    ActionEvents.ACTION_REVERT,
    ActionEvents.ACTION_UPLOAD,
    ActionEvents.ACTION_REPLACE,
    ActionEvents.ACTION_BULK_EDIT,
    ActionEvents.ACTION_APPROVE,
    ActionEvents.ACTION_MARKED_EDIT,
    ActionEvents.ACTION_PROPAGATED_EDIT,
    ActionEvents.ACTION_SOURCE_CHANGE,
    ActionEvents.ACTION_EXPLANATION,
    ActionEvents.ACTION_NEW_UNIT,
    ActionEvents.ACTION_ENFORCED_CHECK,
}

# Actions shown on the repository management page
ACTIONS_REPOSITORY = {
    ActionEvents.ACTION_COMMIT,
    ActionEvents.ACTION_PUSH,
    ActionEvents.ACTION_RESET,
    ActionEvents.ACTION_MERGE,
    ActionEvents.ACTION_REBASE,
    ActionEvents.ACTION_FAILED_MERGE,
    ActionEvents.ACTION_FAILED_REBASE,
    ActionEvents.ACTION_FAILED_PUSH,
    ActionEvents.ACTION_LOCK,
    ActionEvents.ACTION_UNLOCK,
    ActionEvents.ACTION_HOOK,
}

# Actions where target is rendered as translation string
ACTIONS_SHOW_CONTENT = {
    ActionEvents.ACTION_SUGGESTION,
    ActionEvents.ACTION_SUGGESTION_DELETE,
    ActionEvents.ACTION_SUGGESTION_CLEANUP,
    ActionEvents.ACTION_BULK_EDIT,
    ActionEvents.ACTION_NEW_UNIT,
    ActionEvents.ACTION_STRING_REPO_UPDATE,
    ActionEvents.ACTION_NEW_UNIT_REPO,
    ActionEvents.ACTION_STRING_UPLOAD_UPDATE,
    ActionEvents.ACTION_NEW_UNIT_UPLOAD,
}

# Actions indicating a repository merge failure
ACTIONS_MERGE_FAILURE = {
    ActionEvents.ACTION_FAILED_MERGE,
    ActionEvents.ACTION_FAILED_REBASE,
    ActionEvents.ACTION_FAILED_PUSH,
}

ACTIONS_ADDON = {
    ActionEvents.ACTION_ADDON_CREATE,
    ActionEvents.ACTION_ADDON_CHANGE,
    ActionEvents.ACTION_ADDON_REMOVE,
}
