// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  searchPreview("#replace", "#id_replace_q");
  searchPreview("#bulk-edit", "#id_bulk_q");
  searchPreview("#addon-form", "#id_bulk_q");

  /**
   * Add preview to the search input search results.
   *
   * @param {string} searchForm The selector string of the parent element of the search input
   * @param {string} searchElement The selector string of the search input or textarea element
   *
   */
  function searchPreview(searchForm, searchElement) {
    const form = document.querySelector(searchForm);
    const searchInput = form?.querySelector(searchElement);

    if (!form || !searchInput) {
      return;
    }

    // Create the preview element
    const searchPreview = document.createElement("div");
    searchPreview.id = "search-preview";
    searchInput.parentElement?.parentElement?.parentElement?.after(
      searchPreview,
    );

    let debounceTimeout = null;

    // Update the preview while typing with a debounce of 300ms
    searchInput.addEventListener("input", () => {
      searchPreview.style.display = "block";
      const userSearchInput = searchInput.value;
      const searchQuery = buildSearchQuery(searchInput);

      // Clear the previous timeout to prevent the previous
      // request since the user is still typing
      clearTimeout(debounceTimeout);

      // fetch search results but not too often
      debounceTimeout = setTimeout(() => {
        if (userSearchInput) {
          const url = `/api/units/?${new URLSearchParams({
            q: searchQuery,
          }).toString()}`;
          fetch(url, {
            headers: {
              Accept: "application/json",
              "X-Requested-With": "XMLHttpRequest",
            },
          })
            .then((response) => {
              if (!response.ok) {
                return null;
              }
              return response.json();
            })
            .then((response) => {
              if (response === null) {
                return;
              }
              // Clear previous search results
              searchPreview.replaceChildren();
              searchPreview.querySelector("#results-num")?.remove();
              const results = response.results;
              if (!results || results.length === 0) {
                searchPreview.textContent = gettext("No results found");
              } else {
                showResults(results, response.count, searchQuery);
              }
            });
        }
      }, 300); // If the user stops typing for 300ms, the search results will be fetched
    });

    // Show the preview on focus
    searchInput.addEventListener("focus", () => {
      if (searchInput.value !== "" && searchPreview.innerHTML !== "") {
        searchPreview.style.display = "block";
        const resultsNumber = searchPreview.querySelector("#results-num");
        if (resultsNumber) {
          resultsNumber.style.display = "";
        }
      }
    });

    // Close the preview on form submit, form reset, and form clear
    // or if there is no search query
    form.addEventListener("input", () => {
      if (searchInput.value === "") {
        searchPreview.style.display = "none";
        searchPreview.querySelector("#results-num")?.remove();
      }
    });
    form.addEventListener("submit", () => {
      searchPreview.replaceChildren();
      searchPreview.style.display = "none";
      searchPreview.querySelector("#results-num")?.remove();
    });
    form.addEventListener("reset", () => {
      searchPreview.replaceChildren();
      searchPreview.style.display = "none";
      searchPreview.querySelector("#results-num")?.remove();
    });
    form.addEventListener("clear", () => {
      searchPreview.replaceChildren();
      searchPreview.querySelector("#results-num")?.remove();
      searchPreview.style.display = "none";
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
        const searchUrl = `/search/?${new URLSearchParams({
          q: searchQuery,
        }).toString()}`;
        const resultsNumber = document.createElement("a");
        resultsNumber.setAttribute("href", searchUrl);
        resultsNumber.target = "_blank";
        resultsNumber.rel = "noopener noreferrer";
        resultsNumber.id = "results-num";
        resultsNumber.textContent = t;
        searchPreview.append(resultsNumber);
      } else {
        searchPreview.querySelector("#results-num")?.remove();
      }

      for (const result of results) {
        const key = result.context;
        const source = result.source;
        const url = WLT.URLs.getLocalPath(result.web_url);

        if (url === null) {
          continue;
        }

        const resultElement = document.createElement("a");
        resultElement.setAttribute("href", url);
        resultElement.target = "_blank";
        resultElement.className = "search-result";
        resultElement.rel = "noopener noreferrer";

        const keyElement = document.createElement("small");
        keyElement.textContent = String(key);
        resultElement.append(keyElement);

        const sourceElement = document.createElement("div");
        sourceElement.textContent = String(source);
        resultElement.append(sourceElement);

        searchPreview.append(resultElement);
      }
    }
  }

  /**
   * Builds a search query string from the user input filters.
   * The search query is built by the user input filters.
   * The path lookup is also added to the search query.
   * Built in the following format: `path:proj/comp filters`.
   *
   * @param {HTMLInputElement|HTMLTextAreaElement} searchElement - The user input.
   * @returns {string} - The built search query string.
   *
   * */
  function buildSearchQuery(searchElement) {
    let builtSearchQuery = "";

    // Add path lookup to the search query
    const projectPath = searchElement
      .closest("form")
      ?.querySelector("input[name=path]")?.value;
    if (projectPath) {
      builtSearchQuery = `path:${projectPath}`;
    }

    // Add filters to the search query
    const filters = searchElement.value;
    if (filters) {
      builtSearchQuery = `${builtSearchQuery} ${filters}`;
    }
    return builtSearchQuery;
  }
});
