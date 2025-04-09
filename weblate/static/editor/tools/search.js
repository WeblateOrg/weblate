// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  searchPreview("#replace", "#id_replace_q");
  searchPreview("#bulk-edit", "#id_bulk_q");
  searchPreview("#addon-form", "#id_bulk_q");

  /**
   * Add preview to the search input search results.
   *
   * @param {string} searchForm The selector string of the parent element of the search input
   * @param {string} searchElment The selector string of the search input or textarea element
   *
   */
  function searchPreview(searchForm, searchElment) {
    const $searchForm = $(searchForm);
    const $searchElment = $searchForm.find(searchElment);

    // Create the preview element
    const $searchPreview = $('<div id="search-preview"></div>');
    $searchElment.parent().parent().after($searchPreview);

    let debounceTimeout = null;

    // Update the preview while typing with a debounce of 300ms
    $searchElment.on("input", () => {
      $searchPreview.show();
      const userSearchInput = $searchElment.val();
      const searchQuery = buildSearchQuery($searchElment);

      // Clear the previous timeout to prevent the previous
      // request since the user is still typing
      clearTimeout(debounceTimeout);

      // fetch search results but not too often
      debounceTimeout = setTimeout(() => {
        if (userSearchInput) {
          $.ajax({
            url: "/api/units/",
            method: "GET",
            data: { q: searchQuery },
            success: (response) => {
              // Clear previous search results
              $searchPreview.html("");
              $("#results-num").remove();
              const results = response.results;
              if (!results || results.length === 0) {
                $searchPreview.text(gettext("No results found"));
              } else {
                showResults(results, response.count, searchQuery);
              }
            },
          });
        }
      }, 300); // If the user stops typing for 300ms, the search results will be fetched
    });

    // Show the preview on focus
    $searchElment.on("focus", () => {
      if ($searchElment.val() !== "" && $searchPreview.html() !== "") {
        $searchPreview.show();
        $("#results-num").show();
      }
    });

    // Close the preview on form submit, form reset, and form clear
    // or if there is no search query
    $searchForm.on("input", () => {
      if ($searchElment.val() === "") {
        $searchPreview.hide();
        $("#results-num").remove();
      }
    });
    $searchForm.on("submit", () => {
      $searchPreview.html("");
      $searchPreview.hide();
      $("#results-num").remove();
    });
    $searchForm.on("reset", () => {
      $searchPreview.html("");
      $searchPreview.hide();
      $("#results-num").remove();
    });
    $searchForm.on("clear", () => {
      $searchPreview.html("");
      $("#results-num").remove();
      $searchPreview.hide();
    });

    /**
     * Handles the search results and displays them in the preview element.
     * @param {any} results fetched search results
     * @param {number} count The number of search results
     * @param {string} searchQuery The user typed search
     * @returns void
     */
    function showResults(results, count, searchQuery) {
      // Show the number of results
      if (count > 0) {
        const t = interpolate(
          ngettext("%s matching string", "%s matching strings", count),
          [count],
        );
        const searchUrl = `/search/?q=${encodeURI(searchQuery)}`;
        const resultsNumber = `<a href="${searchUrl}" target="_blank" rel="noopener noreferrer" id="results-num">${t}</a>`;
        $searchPreview.append(resultsNumber);
      } else {
        $("#results-num").remove();
      }

      for (const result of results) {
        const key = result.context;
        const source = result.source;

        // Make the URL relative
        // biome-ignore lint/performance/useTopLevelRegex: TODO: is this regexp really needed?
        const url = result.web_url.replace(/^[a-zA-Z]+:\/\/[^/]+\//, "/");
        const resultHtml = `
          <a href="${url}" target="_blank" id="search-result" rel="noopener noreferrer">
            <small>${key}</small>
            <div>
              ${source.toString()}
            </div>
          </a>
        `;

        $searchPreview.append(resultHtml);
      }
    }
  }

  /**
   * Builds a search query string from the user input filters.
   * The search query is built by the user input filters.
   * The path lookup is also added to the search query.
   * Built in the following format: `path:proj/comp filters`.
   *
   * @param {jQuery} $searchElment - The user input.
   * @returns {string} - The built search query string.
   *
   * */
  function buildSearchQuery($searchElment) {
    let builtSearchQuery = "";

    // Add path lookup to the search query
    const projectPath = $searchElment
      .closest("form")
      .find("input[name=path]")
      .val();
    if (projectPath) {
      builtSearchQuery = `path:${projectPath}`;
    }

    // Add filters to the search query
    const filters = $searchElment.val();
    if (filters) {
      builtSearchQuery = `${builtSearchQuery} ${filters}`;
    }
    return builtSearchQuery;
  }
});
