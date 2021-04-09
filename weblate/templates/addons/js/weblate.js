var weblate_supported = ["{{ languages|safe }}"];
var weblate_url = "{{ url }}";
var weblate_selector = "{{ css_selector }}";
var weblate_cookie_name = "{{ cookie_name }}";

var ready = (callback) => {
  if (document.readyState != "loading") {
    callback();
  } else {
    document.addEventListener("DOMContentLoaded", callback);
  }
};

var getCookie = (name) => {
  var value = "; " + document.cookie;
  var parts = value.split("; " + name + "=");
  if (parts.length == 2) return parts.pop().split(";").shift();
};

ready(() => {
  var languages = [getCookie(weblate_cookie_name)];
  languages = languages.concat(navigator.languages);
  languages = languages.concat(navigator.language);
  languages = languages.concat(navigator.userLanguage);

  var language;
  for (const i in languages) {
    let code = languages[i];
    if (code && weblate_supported.includes(code)) {
      language = code;
      break;
    }
  }

  if (language) {
    fetch(weblate_url + "/" + language + ".json")
      .then((response) => response.json())
      .then((data) => {
        document.querySelectorAll(weblate_selector).forEach((element) => {
          if (element.children.length === 0 && element.textContent in data) {
            element.textContent = data[element.textContent];
          }
        });
      });
  }
});
