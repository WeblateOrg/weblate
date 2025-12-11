const ready = (callback) => {
  if (document.readyState !== "loading") {
    callback();
  } else {
    document.addEventListener("DOMContentLoaded", callback);
  }
};

const getCookie = (name) => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
};

const translateDocument = (data) => {
  document.querySelectorAll(weblate_selector).forEach((element) => {
    if (element.children.length === 0 && element.textContent in data) {
      element.textContent = data[element.textContent];
    }
  });
};

ready(() => {
  let languages = [getCookie(weblate_cookie_name)];
  languages = languages.concat(navigator.languages);
  languages = languages.concat(navigator.language);
  languages = languages.concat(navigator.userLanguage);

  let language;
  for (const i in languages) {
    const code = languages[i];
    if (code && weblate_supported.includes(code)) {
      language = code;
      break;
    }
  }

  if (language) {
    let stored = sessionStorage.getItem("WLCDN");
    if (stored !== null) {
      stored = JSON.parse(stored);
    }
    if (stored !== null && stored.language === language) {
      translateDocument(stored.data);
    } else {
      fetch(`${weblate_url}/${language}.json`)
        .then((response) => response.json())
        .then((data) => {
          sessionStorage.setItem(
            "WLCDN",
            JSON.stringify({ language: language, data: data }),
          );
          translateDocument(data);
        });
    }
  }
});
