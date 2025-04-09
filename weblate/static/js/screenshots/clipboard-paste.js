// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  // The paste trigger button
  const $pasteScreenshotBtn = $("#paste-screenshot-btn");
  // The file input to store the screenshot file
  const $screenshotFileInput = $("#screenshot-form-container input#id_image");

  // Check if the browser supports the Clipboard API
  if (!navigator.clipboard?.read) {
    $pasteScreenshotBtn.remove();
  }

  // biome-ignore lint/complexity/noExcessiveCognitiveComplexity: TODO: factor out clipboard handling
  $pasteScreenshotBtn.on("click", async (e) => {
    e.preventDefault();
    try {
      // Read clipboard content
      const clipboardItems = await navigator.clipboard.read();
      let imageFound = false;
      for (const clipboardItem of clipboardItems) {
        // Find the image in the clipboard
        for (const type of clipboardItem.types) {
          if (type.startsWith("image/")) {
            // Convert the image data to a file data
            const blob = await clipboardItem.getType(type);
            const reader = new FileReader();
            reader.onload = (_event) => {
              if ($screenshotFileInput.length > 0) {
                // Load the file data into the form input
                const fileName = `screenshot_${Date.now()}.${type.split("/")[1]}`;
                const imageFile = new File([blob], fileName, { type: type });
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(imageFile);
                $screenshotFileInput[0].files = dataTransfer.files;
                // Inform paste success
                showInfo("success", gettext("Image Pasted!"));
              } else {
                showInfo("danger", gettext("Something went wrong!"));
              }
            };
            reader.readAsDataURL(blob);
            imageFound = true;
            break;
          }
        }
        if (imageFound) {
          break;
        }
      }
      if (!imageFound) {
        showInfo("warning", gettext("No image found in clipboard"));
      }
    } catch (_err) {
      showInfo("danger", gettext("Something went wrong!"));
    }
  });
});

/**
 * Displays an information message on the screenshot form.
 *
 * @param {string} type - The type of the message (e.g., "success", "error", "warning").
 * @param {string} message - The content of the message.
 */
function showInfo(type, message) {
  const $pasteScreenshotInfo = $("#paste-screenshot-info-label");
  const span = `<span class="text-${type}">${message}</span>`;
  $pasteScreenshotInfo.html(span);
  $pasteScreenshotInfo
    .css("transform", "scale(1)")
    .removeClass("animate__animated animate__fadeIn");
}
