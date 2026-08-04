// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  // The paste trigger button
  const pasteScreenshotBtn = document.getElementById("paste-screenshot-btn");
  if (pasteScreenshotBtn === null) {
    return;
  }
  const screenshotForm = document.getElementById("screenshot-form-container");
  // The file input to store the screenshot file
  const screenshotFileInput = screenshotForm?.querySelector("input#id_image");
  if (screenshotForm === null || screenshotFileInput === null) {
    pasteScreenshotBtn.remove();
    return;
  }

  const setScreenshotImage = (blob, type) => {
    const fileName = `screenshot_${Date.now()}.${type.split("/")[1]}`;
    const imageFile = new File([blob], fileName, { type: type });
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(imageFile);
    screenshotFileInput.files = dataTransfer.files;
    screenshotFileInput.dispatchEvent(new Event("change", { bubbles: true }));
    showInfo("success", gettext("Image Pasted!"));
  };

  const showPasteInstructions = () => {
    showInfo("info", gettext("Press Ctrl+V or Command+V to paste an image."));
  };

  screenshotForm.addEventListener("paste", (event) => {
    const clipboardItems = event.clipboardData?.items;
    if (clipboardItems === undefined) {
      return;
    }
    const imageItem = Array.from(clipboardItems).find(
      (item) => item.kind === "file" && item.type.startsWith("image/"),
    );
    const imageFile = imageItem?.getAsFile();
    if (imageFile === null || imageFile === undefined) {
      return;
    }
    event.preventDefault();
    setScreenshotImage(imageFile, imageItem.type);
  });

  pasteScreenshotBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!navigator.clipboard?.read) {
      showPasteInstructions();
      return;
    }
    try {
      // Read clipboard content
      const clipboardItems = await navigator.clipboard.read();
      for (const clipboardItem of clipboardItems) {
        // Find the image in the clipboard
        const type = clipboardItem.types.find((itemType) =>
          itemType.startsWith("image/"),
        );
        if (type !== undefined) {
          setScreenshotImage(await clipboardItem.getType(type), type);
          return;
        }
      }
      showInfo("warning", gettext("No image found in clipboard"));
    } catch (_err) {
      showPasteInstructions();
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
  const pasteScreenshotInfo = document.getElementById(
    "paste-screenshot-info-label",
  );
  if (pasteScreenshotInfo === null) {
    return;
  }
  const span = document.createElement("span");
  span.classList.add(`text-${type}`);
  span.textContent = message;
  pasteScreenshotInfo.replaceChildren(span);
  pasteScreenshotInfo.style.transform = "scale(1)";
  pasteScreenshotInfo.classList.remove("animate__animated", "animate__fadeIn");
}
