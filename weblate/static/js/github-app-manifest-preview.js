// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const previewElement = document.getElementById("github-app-manifest-preview");
  const nameField = document.getElementById("register-name");
  const publicField = document.getElementById("register-public");

  if (previewElement === null || nameField === null || publicField === null) {
    return;
  }

  let manifest;
  try {
    manifest = JSON.parse(previewElement.textContent);
  } catch (_error) {
    return;
  }

  function updatePreview() {
    manifest.name = nameField.value;
    manifest.public = publicField.checked;
    previewElement.textContent = JSON.stringify(manifest, null, 2);
  }

  nameField.addEventListener("input", updatePreview);
  publicField.addEventListener("change", updatePreview);

  updatePreview();
});
