var weblate_supported = {{ languages }}
var weblate_url = {{ url }};
var weblate_selector = {{ css_selector }};
var weblate_cookie_name = {{ cookie_name }};

{% include "addons/js/weblate-code.js" %}
