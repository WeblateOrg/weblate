// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  const widgetsData = $("#widgets-data").data("json");

  const jsonLanguage = widgetsData.language || "";
  $("#translation-language").val(jsonLanguage);

  let jsonComponent = widgetsData.component;
  if (jsonComponent === null) {
    jsonComponent = "";
  }
  $("#component").val(jsonComponent);

  function generateEmbedCode(
    codeLanguage,
    engageUrl,
    widgetUrl,
    translationStatus,
  ) {
    if (codeLanguage === "html") {
      return `<a href="${engageUrl}">
<img src="${widgetUrl}" alt="${translationStatus}" />
</a>`;
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
    const widgetName = $("#widget-type").val();
    const componentId = $("#component").val();
    const component = widgetsData.components.find(
      (c) => String(c.id) === componentId,
    );
    const language = $("#translation-language").val();
    const widget = widgetsData.widgets[widgetName];
    const color = $("#color-select").val();

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
    $("#extra-parameters input").each(function () {
      const paramName = $(this).attr("name");
      const paramValue = $(this).val();
      if (paramValue) {
        params.set(paramName, paramValue);
      }
    });

    const query = params.toString();
    const suffix = query === "" ? "" : `?${query}`;
    const newUrl = `${widgetUrl}/${widgetName}-${color}.${widget.extension}${suffix}`;
    $("#widget-image").attr("src", newUrl);

    const translationStatus = widgetsData.translation_status;
    const codeLanguage = $("#code-language").val();
    const code = generateEmbedCode(
      codeLanguage,
      engageUrl,
      newUrl,
      translationStatus,
    );
    $("#embed-code-copy-button").attr("data-clipboard-value", code);
    $("#embed-code").val(code);
  }

  function updateWidgetColors(widgetName) {
    const widgets = widgetsData.widgets;
    const colors = widgets[widgetName].colors;
    const colorSelect = $("#color-select");
    colorSelect.empty();
    $.each(colors, (_index, color) => {
      const option = $("<option></option>").val(color).text(color);
      colorSelect.append(option);
    });
    updateLivePreviewAndEmbedCode();
  }

  function updateQueryParams() {
    const params = new URLSearchParams(window.location.search);
    params.set("component", $("#component").val());
    params.set("lang", $("#translation-language").val());
    const query = params.toString();
    const suffix = query === "" ? "" : `?${query}`;
    const newUrl = `${window.location.pathname}${suffix}`;
    window.history.pushState({}, "", newUrl);
  }

  function renderExtraParameters(widgetName) {
    const widget = widgetsData.widgets[widgetName];
    const extraParamsContainer = $("#extra-parameters");
    extraParamsContainer.empty();

    if (widget.extra_parameters) {
      for (const param of widget.extra_parameters) {
        let input;
        if (param.type === "number") {
          input = $("<input/>", {
            type: param.type,
            id: param.name,
            name: param.name,
            min: param.min,
            max: param.max,
            step: param.step,
            value: param.default,
            class: "form-control mt-2",
          });
        }

        const label = $("<label/>", {
          for: param.name,
          text: param.label,
          class: "form-label mt-2",
        });
        extraParamsContainer.append(label).append(input);

        // Add change event listener to update query params and live preview
        input.change(() => {
          updateQueryParams();
          updateLivePreviewAndEmbedCode();
        });
      }
    }
  }

  $("#widget-type").change(function () {
    const widgetName = $(this).val();
    updateWidgetColors(widgetName);
    renderExtraParameters(widgetName);
  });

  $("#color-select").change(updateLivePreviewAndEmbedCode);
  $("#component").change(() => {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  $("#translation-language").change(() => {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  $("#code-language").change(updateLivePreviewAndEmbedCode);

  updateWidgetColors($("#widget-type").val());
  renderExtraParameters($("#widget-type").val());
});
