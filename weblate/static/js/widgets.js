$(document).ready(function() {
  const widgetsData = JSON.parse($("#widgets-data").text());

  let jsonLanguage = widgetsData["language"];
  if (jsonLanguage === null) {
    jsonLanguage = "";
  }
  $("#translation_language").val(jsonLanguage);

  let jsonComponent = widgetsData["component"];
  if (jsonComponent === null) {
    jsonComponent = "";
  }
  $("#component").val(jsonComponent);

  function updateLivePreviewAndEmbedCode() {
    const widgetName = $("#widget_type").val();
    const componentId = $("#component").val();
    const component = widgetsData["components"].find(component => String(component.id) === componentId);

    const language = $("#translation_language").val();

    const widget = widgetsData["widgets"][widgetName];
    const color = $("#color_select").val();

    let engageUrl = widgetsData["engage_base_url"];

    const widgetBaseUrl = widgetsData["widget_base_url"];
    let widgetUrl = `${widgetBaseUrl}`;
    if (component !== undefined && language !== "") {
      widgetUrl = `${widgetUrl}/${component.slug}/${language}`;
    } else if (component !== undefined && language === "") {
      widgetUrl = `${widgetUrl}/${component.slug}`;
    } else if (component === undefined && language !== "") {
      widgetUrl = `${widgetUrl}/-/${language}`;
    }

    const newUrl = `${widgetUrl}/${widgetName}-${color}.${widget.extension}`;
    $("#widgetImage").attr("src", newUrl);

    let translationStatus = widgetsData["translation_status"];

    let code;
    const codeLanguage = $("#code_language").val();
    if (codeLanguage === "html") {
      code = `<a href="${engageUrl}">
<img src="${newUrl}" alt="${translationStatus}" />
</a>`;
    } else if (codeLanguage === "bb-code") {
      code = `[url=${engageUrl}][img alt="${translationStatus}"]${newUrl}[/img][/url]`;
    } else if (codeLanguage === "mdk") {
      code = `[![${translationStatus}](${newUrl})](${engageUrl})`;
    } else if (codeLanguage === "rst") {
      code = `.. image:: ${newUrl}
  :alt: ${translationStatus}
  :target: ${engageUrl}`;
    } else if (codeLanguage === "textile-code") {
      code = `!${newUrl}!:${engageUrl}`;
    } else {
      code = newUrl;
    }

    $("#embedCode").val(code);
  }

  function updateWidgetColors(widgetName) {
    const widgets = widgetsData["widgets"];
    const colors = widgets[widgetName]["colors"];
    const colorSelect = $("#color_select");
    colorSelect.empty();
    $.each(colors, function(index, color) {
      const option = $("<option></option>").val(color).text(color);
      colorSelect.append(option);
    });
    updateLivePreviewAndEmbedCode(widgetName);
  }

  function updateQueryParams() {
    const params = new URLSearchParams(window.location.search);
    params.set("component", $('#component').val());
    params.set("lang", $('#translation_language').val());
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState({}, "", newUrl);
  }

  $("#widget_type").click(function() {
    const widgetName = $(this).val();
    updateWidgetColors(widgetName);
  });

  $("#color_select").change(updateLivePreviewAndEmbedCode);
  $("#component").change(function() {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  $("#translation_language").change(function() {
    updateQueryParams();
    updateLivePreviewAndEmbedCode();
  });
  $("#code_language").change(updateLivePreviewAndEmbedCode);

  updateWidgetColors($("#widget_type").val());

});
