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
    const widgetName = $('#widget_type').val();
    const componentId = $('#component').val();
    const component = widgetsData['components'].find(c => String(c.id) === componentId);
    const language = $('#translation_language').val();
    const widget = widgetsData['widgets'][widgetName];
    const color = $('#color_select').val();

    let engageUrl = widgetsData['engage_base_url'];
    const widgetBaseUrl = widgetsData['widget_base_url'];
    let widgetUrl = `${widgetBaseUrl}`;
    if (component !== undefined && language !== '') {
      widgetUrl = `${widgetUrl}/${component.slug}/${language}`;
    } else if (component !== undefined && language === '') {
      widgetUrl = `${widgetUrl}/${component.slug}`;
    } else if (component === undefined && language !== '') {
      widgetUrl = `${widgetUrl}/-/${language}`;
    }

    // Include extra parameters in the URL
    const params = new URLSearchParams();
    $('#extra-parameters input').each(function() {
      const paramName = $(this).attr('name');
      const paramValue = $(this).val();
      if (paramValue) {
        params.set(paramName, paramValue);
      }
    });

    const newUrl = `${widgetUrl}/${widgetName}-${color}.${widget.extension}?${params.toString()}`;
    $('#widgetImage').attr('src', newUrl);

    let translationStatus = widgetsData['translation_status'];

    let code;
    const codeLanguage = $('#code_language').val();
    if (codeLanguage === 'html') {
      code = `<a href="${engageUrl}">
<img src="${newUrl}" alt="${translationStatus}" />
</a>`;
    } else if (codeLanguage === 'bb-code') {
      code = `[url=${engageUrl}][img alt="${translationStatus}"]${newUrl}[/img][/url]`;
    } else if (codeLanguage === 'mdk') {
      code = `[![${translationStatus}](${newUrl})](${engageUrl})`;
    } else if (codeLanguage === 'rst') {
      code = `.. image:: ${newUrl}
  :alt: ${translationStatus}
  :target: ${engageUrl}`;
    } else if (codeLanguage === 'textile-code') {
      code = `!${newUrl}!:${engageUrl}`;
    } else {
      code = newUrl;
    }

    $('#embedCode').val(code);
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
    updateLivePreviewAndEmbedCode();
  }

  function updateQueryParams() {
    const params = new URLSearchParams(window.location.search);
    params.set("component", $('#component').val());
    params.set("lang", $('#translation_language').val());
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState({}, "", newUrl);
  }

  function renderExtraParameters(widgetName) {
    const widget = widgetsData["widgets"][widgetName];
    const extraParamsContainer = $('#extra-parameters');
    extraParamsContainer.empty();

    if (widget.extra_parameters) {
      widget.extra_parameters.forEach(param => {
        let input;
        if (param.type === 'number') {
          input = $('<input/>', {
            type: param.type,
            id: param.name,
            name: param.name,
            min: param.min,
            max: param.max,
            step: param.step,
            value: param.default,
            class: 'form-control mt-2'
          });
        }

        const label = $('<label/>', {
          for: param.name,
          text: param.label,
          class: 'form-label mt-2'
        });
        extraParamsContainer.append(label).append(input);

        // Add change event listener to update query params and live preview
        input.change(function() {
          updateQueryParams();
          updateLivePreviewAndEmbedCode();
        });
      });
    }
  }

  $("#widget_type").change(function() {
    const widgetName = $(this).val();
    updateWidgetColors(widgetName);
    renderExtraParameters(widgetName);
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
  renderExtraParameters($("#widget_type").val());

});
