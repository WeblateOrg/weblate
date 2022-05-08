import $ from "./vendor/jquery.js";
import "./vendor/multi.js";

// TODO don't import `multi` if there are no such elements.

/* Override all multiple selects */
$("select[multiple]").multi({
  enable_search: true,
  search_placeholder: gettext("Search…"),
  non_selected_header: gettext("Available:"),
  selected_header: gettext("Chosen:"),
});
