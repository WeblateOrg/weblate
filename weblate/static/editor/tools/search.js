// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  searchPreview("#replace", "#id_replace_search", "#id_replace_q");
  // searchPreview('#bulk-edit', '#id_bulk_q');

  /**
   * Add preview to the search input search results.
   *
   * @param {string} searchForm The selector string of the parent element of the search input
   * @param {string} searchElment The selector string of the search input or textarea element
   * @param {string} filtersElement The selector string of the filters input element
   * @param {number} fetchMax The maximum number of preview results to fetch
   *
   */
  function searchPreview(searchForm, searchElment, filtersElement, fetchMax) {
    const $searchForm = $(searchForm);
    const $searchElment = $searchForm.find(searchElment);
    const $filtersElement = $searchForm.find(filtersElement);

    const includeFilters = !!filtersElement;

    // Create the preview element
    const $searchPreview = $('<div id="search-preview"></div>');
    $searchElment.after($searchPreview);

    let debounceTimeout = null;

    // Update the preview while typing with a debounce of 300ms
    $searchElment.on("input", () => {
      $searchPreview.show();
      const userSearchInput = $searchElment.val();
      let searchQuery = `'${userSearchInput}'`;

      // Clear the previous timeout to prevent the previous
      // request since the user is still typing
      clearTimeout(debounceTimeout);

      // fetch search results but not too often
      debounceTimeout = setTimeout(() => {
        if (userSearchInput) {
          searchQuery = buildSearchQuery(
            searchQuery,
            $filtersElement,
            includeFilters,
          );
          $.ajax({
            url: "/api/units/",
            method: "GET",
            data: { q: searchQuery, page_size: fetchMax },
            success: (response) => {
              // Clear previous search results
              $searchPreview.html("");

              const results = response.results;
              if (!results || results.length === 0) {
                $searchPreview.text(gettext("No results found"));
              } else {
                for (const result of results) {
                  const key = result.context;
                  const source = result.source;
                  const sourceHighlighted = highlightMatch(
                    userSearchInput,
                    source.toString(),
                  );

                  // Make the URL relative
                  const url = result.web_url.replace(/^(?:\/\/|[^/]+)*\//, "/");
                  const resultHtml = `
                    <a href="${url}" target="_blank" id="search-result" rel="noopener noreferrer">
                      <small>${key}</small>
                      <div>
                        ${sourceHighlighted}
                      </div>
                    </a>
                  `;

                  // Some results are not relevant (case in-sensetive), so we filter them out
                  if (sourceHighlighted === source) {
                    return;
                  }
                  $searchPreview.append(resultHtml);
                }
              }
            },
            error: (error) => {
              console.error("Error fetching search results: ", error);
            },
          });
        }
      }, 300); // If the user stops typing for 300ms, the search results will be fetched
    });

    // Show the preview on focus
    $searchElment.on("focus", () => {
      if ($searchElment.val() !== "" && $searchPreview.html() !== "") {
        $searchPreview.show();
      }
    });

    // Close the preview on focusout, form submit, form reset, and form clear
    $searchElment.on("focusout", () => {
      // Hide after a delay to allow click on a result
      setTimeout(() => {
        $searchPreview.hide();
      }, 700);
    });
    $searchForm.on("submit", () => {
      $searchPreview.html("");
      $searchPreview.hide();
    });
    $searchForm.on("reset", () => {
      $searchPreview.html("");
      $searchPreview.hide();
    });
    $searchForm.on("clear", () => {
      $searchPreview.html("");
      $searchPreview.hide();
    });
  }

  /**
   * Builds a search query string with the user input and filters.
   * The search query is built by concatenating the user input with the filters.
   * The path lookup is also added to the search query.
   * Built in the following format: `userInput path:proj/comp filters`.
   *
   * @param {string} searchQuery - The user input search query.
   * @param {jQuery} $filtersElement - The jQuery object of the filters input element.
   * @param {boolean} includeFilters - A boolean indicating whether to include the filters in the search query.
   * @returns {string} - The built search query string.
   *
   * */
  function buildSearchQuery(searchQuery, $filtersElement, includeFilters) {
    let builtSearchQuery = searchQuery;

    // Add path lookup to the search query
    const pathSplited = window.location.pathname.split("/");
    const projectPath = `${pathSplited[2]}/${pathSplited[3]}`;
    if (projectPath) {
      builtSearchQuery = `${searchQuery} path:${projectPath}`;
    }

    // Add filters to the search query
    if (includeFilters) {
      const filters = $filtersElement.val();
      if (filters) {
        builtSearchQuery = `${builtSearchQuery} ${filters}`;
      }
    }
    return builtSearchQuery;
  }

  /**
   * Highlights all occurrences of string1 in string2 by surrounding them with a `span` element.
   *
   * @param {string} string1 - The substring that should be highlighted in string2.
   * @param {string} string2 - The string where the occurrences of string1 will be highlighted.
   * @returns {string} - A new string with all occurrences of string1 in string2 surrounded by <span> elements.
   *
   */
  function highlightMatch(string1, string2) {
    // If either string is empty, do not highlight anything
    if (!(string1 && string2)) {
      return string2;
    }

    // Escape special regex characters in string1 to prevent issues in the RegExp
    const escapedString1 = string1.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    // Create a regular expression with the escaped string1, globally matching all occurrences
    const regex = new RegExp(`(${escapedString1})`, "g");

    // Replace every occurrence of string1 in string2 with a <span> surrounding the matched text
    const highlightedString = string2.replace(
      regex,
      '<span style="background: #01ff7050">$1</span>',
    );

    // Return the modified string with <span>-wrapped matches
    return highlightedString;
  }
});
