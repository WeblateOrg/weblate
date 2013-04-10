{% if apertium_api_key %}
var APERTIUM_API_KEY = '{{ apertium_api_key }}';
{% endif %}
{% if apertium_langs %}
var APERTIUM_LANGS = ['{{ apertium_langs|join:"','" }}'];
{% endif %}
{% if microsoft_api_key %}
var MICROSOFT_API_KEY = '{{ microsoft_api_key }}';
{% endif %}
{% if microsoft_langs %}
var MICROSOFT_LANGS = ['{{ microsoft_langs|join:"','" }}'];
{% endif %}
var MACHINE_TRANSLATION_SERVICES = [{% if machine_services %}'{{ machine_services|join:"','" }}'{% endif %}];
