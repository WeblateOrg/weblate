// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const dataElement = document.getElementById("vcs-push-help-data");
  if (dataElement === null) {
    return;
  }
  const categories = JSON.parse(dataElement.getAttribute("data-categories"));

  const vcsField = document.getElementById("id_vcs");
  const pushField = document.getElementById("id_push");
  const pushBranchField = document.getElementById("id_push_branch");
  const branchField = document.getElementById("id_branch");
  const textElement = document.querySelector(
    "#vcs-push-help .vcs-push-help-text",
  );
  const warningElement = document.querySelector(
    "#vcs-push-help .vcs-push-help-warning",
  );

  if (
    vcsField === null ||
    pushField === null ||
    pushBranchField === null ||
    textElement === null ||
    warningElement === null
  ) {
    return;
  }

  function describe(category, push, pushBranch, branch) {
    if (category === "merge_request") {
      if (push && !pushBranch) {
        return {
          text: gettext(
            "A pull or merge request will be created from a branch in the repository.",
          ),
          warning: gettext(
            "A push URL is set but no push branch is given. Set a push branch that differs from the translated branch.",
          ),
        };
      }
      if (push && pushBranch && pushBranch === branch) {
        return {
          text: gettext(
            "A pull or merge request will be created from a branch in the repository.",
          ),
          warning: gettext(
            "The push branch must differ from the translated branch when creating a pull or merge request.",
          ),
        };
      }
      if (!pushBranch) {
        return {
          text: gettext(
            "A pull or merge request will be created from a fork of the repository.",
          ),
        };
      }
      return {
        text: interpolate(
          gettext(
            "A pull or merge request will be created from the “%s” branch in the repository.",
          ),
          [pushBranch],
        ),
      };
    }

    if (category === "gerrit") {
      if (pushBranch) {
        return {
          text: interpolate(
            gettext(
              "Changes will be sent as a Gerrit review request targeting the “%s” branch.",
            ),
            [pushBranch],
          ),
        };
      }
      return {
        text: gettext("Changes will be sent as a Gerrit review request."),
      };
    }

    // Direct push (plain Git, Mercurial, …)
    if (!push) {
      return {
        text: gettext(
          "Changes will not be pushed automatically. You can still push them manually from the repository maintenance.",
        ),
      };
    }
    if (pushBranch) {
      return {
        text: interpolate(
          gettext(
            "Changes will be pushed directly to the “%s” branch in the push repository.",
          ),
          [pushBranch],
        ),
      };
    }
    if (branch) {
      return {
        text: interpolate(
          gettext(
            "Changes will be pushed directly to the “%s” branch in the push repository.",
          ),
          [branch],
        ),
      };
    }
    return {
      text: gettext(
        "Changes will be pushed directly to the default branch of the push repository.",
      ),
    };
  }

  function updateDescription() {
    const category = categories[vcsField.value] || "direct";
    const push = pushField.value.trim();
    const pushBranch = pushBranchField.value.trim();
    const branch = branchField === null ? "" : branchField.value.trim();

    const result = describe(category, push, pushBranch, branch);
    textElement.textContent = result.text;
    warningElement.textContent = result.warning || "";
  }

  for (const field of [vcsField, pushField, pushBranchField, branchField]) {
    if (field !== null) {
      field.addEventListener("change", updateDescription);
      field.addEventListener("input", updateDescription);
    }
  }

  updateDescription();
});
