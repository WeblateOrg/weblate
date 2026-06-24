// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const widgetsDataElement = document.getElementById("widgets-data");
  if (widgetsDataElement === null) {
    return;
  }
  const widgetsData = JSON.parse(widgetsDataElement.getAttribute("data-json"));

  const widgetTypeSelect = document.getElementById("widget-type");
  const componentSelect = document.getElementById("component");
  const languageSelect = document.getElementById("translation-language");
  const colorSelect = document.getElementById("color-select");
  const codeLanguageSelect = document.getElementById("code-language");
  const extraParamsContainer = document.getElementById("extra-parameters");

  const jsonLanguage = widgetsData.language || "";
  languageSelect.value = jsonLanguage;

  let jsonComponent = widgetsData.component;
  if (jsonComponent === null) {
    jsonComponent = "";
  }
  componentSelect.value = jsonComponent;

  function generateEmbedCode(
    codeLanguage,
    engageUrl,
    widgetUrl,
    translationStatus,
  ) {
    if (codeLanguage === "html") {
      const link = document.createElement("a");
      link.href = engageUrl;
      const image = document.createElement("img");
      image.src = widgetUrl;
      image.alt = translationStatus;
      link.append(image);
      return link.outerHTML;
    }
    if (codeLanguage === "bb-code") {
      return `[url=${engageUrl}][img alt="${translationStatus}"]${widgetUrl}[/img][/url]`;
    }
    if (codeLanguage === "mdk") {
      return `[![${translationStatus}](${widgetUrl})](${engageUrl})`;
    }
    if (codeLanguage === "rst") {
      return `.. image:: ${widgetUrl}
  :alt: ${translationStatus}
  :target: ${engageUrl}`;
    }
    if (codeLanguage === "textile-code") {
      return `!${widgetUrl}!:${engageUrl}`;
    }
    return widgetUrl;
  }

  function updateLivePreviewAndEmbedCode() {
    const widgetName = widgetTypeSelect.value;
    const componentId = componentSelect.value;
    const component = widgetsData.components.find(
      (c) => String(c.id) === componentId,
    );
    const language = languageSelect.value;
    const widget = widgetsData.widgets[widgetName];
    const color = colorSelect.value;

    const engageUrl = widgetsData.engage_base_url;
    const widgetBaseUrl = widgetsData.widget_base_url;
    let widgetUrl = `${widgetBaseUrl}`;
    if (component !== undefined && language !== "") {
      widgetUrl = `${widgetUrl}/${component.slug}/${language}`;
    } else if (component !== undefined && language === "") {
      widgetUrl = `${widgetUrl}/${component.slug}`;
    } else if (component === undefined && language !== "") {
      widgetUrl = `${widgetUrl}/-/${language}`;
    }

    // Include extra parameters in the URL
    const params = new URLSearchParams();
    for (const input of extraParamsContainer.querySelectorAll("input")) {
      const paramName = input.getAttribute("name");
      const paramValue = input.value;
      if (paramValue) {
        params.set(paramName, paramValue);
      }
    }

    const query = params.toString();
    const suffix = query === "" ? "" : `?${query}`;
    const newUrl = `${widgetUrl}/${widgetName}-${color}.${widget.extension}${suffix}`;
    document.getElementById("widget-image").setAttribute("src", newUrl);

    const translationStatus = widgetsData.translation_status;
    const codeLanguage = codeLanguageSelect.value;
    const code = generateEmbedCode(
      codeLanguage,
      engageUrl,
      newUrl,
      translationStatus,
    );
    document
      .getElementById("embed-code-copy-button")
      .setAttribute("data-clipboard-value", code);
    document.getElementById("embed-code").value = code;
  }

  function updateWidgetColors(widgetName) {
    const widgets = widgetsData.widgets;
    const colors = widgets[widgetName].colors;
    colorSelect.replaceChildren();
    for (const color of colors) {
      const option = document.createElement("option");
      option.value = color;
      option.textContent = color;
      colorSelect.append(option);
    }
    updateLivePreviewAndEmbedCode();
  }

  function updateQueryParams() {
    const params = new URLSearchParams(window.location.search);
    params.set("component", componentSelect.value);
    params.set("lang", languageSelect.value);
    const query = params.toString();
    const suffix = query === "" ? "" : `?${query}`;
    const newUrl = `${window.location.pathname}${suffix}`;
    window.history.pushState({}, "", newUrl);
  }

  function renderExtraParameters(widgetName) {
    const widget = widgetsData.widgets[widgetName];
    extraParamsContainer.replaceChildren();

    if (widget.extra_parameters) {
      for (const param of widget.extra_parameters) {
        const label = document.createElement("label");
        label.setAttribute("for", param.name);
        label.textContent = param.label;
        label.className = "form-label mt-2";
        extraParamsContainer.append(label);

        if (param.type === "number") {
          const input = document.createElement("input");
          input.type = param.type;
          input.id = param.name;
          input.name = param.name;
          input.min = param.min;
          input.max = param.max;
          input.step = param.step;
          input.value = param.default;
          input.className = "form-control mt-2";
          extraParamsContainer.append(input);

          // Add change event listener to update query params and live preview
          input.addEventListener("change", () => {
            updateQueryParams();
            updateLivePreviewAndEmbedCode();
          });
        }
      }
    }
  }

  widgetTypeSelect.addEventListener("change", () => {
    const widgetName = widgetTypeSelect.value;
    updateWidgetColors(widgetName);
    renderExtraParameters(widgetName);
  });

  colorSelect.addEventListener("change", updateLivePreviewAndEmbedCode);
  componentSelect.addEventListener("change", () => {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  languageSelect.addEventListener("change", () => {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  codeLanguageSelect.addEventListener("change", updateLivePreviewAndEmbedCode);

  updateWidgetColors(widgetTypeSelect.value);
  renderExtraParameters(widgetTypeSelect.value);
});
