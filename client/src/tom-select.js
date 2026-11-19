// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

import TomSelect from "tom-select/base";
import TomSelect_checkbox_options from "tom-select/dist/js/plugins/checkbox_options.js";
import TomSelect_remove_button from "tom-select/dist/js/plugins/remove_button.js";
import TomSelect_virtual_scroll from "tom-select/dist/js/plugins/virtual_scroll.js";
import "tom-select/dist/css/tom-select.bootstrap5.min.css";

TomSelect.define("checkbox_options", TomSelect_checkbox_options);
TomSelect.define("remove_button", TomSelect_remove_button);

TomSelect.define("virtual_scroll", TomSelect_virtual_scroll);

window.TomSelect = TomSelect;
