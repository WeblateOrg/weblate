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
  // biome-ignore lint/complexity/noForEach: TODO
  // biome-ignore lint/correctness/noUndeclaredVariables: weblate_selector defined externally
  document.querySelectorAll(weblate_selector).forEach((element) => {
    if (element.children.length === 0 && element.textContent in data) {
      element.textContent = data[element.textContent];
    }
  });
};

ready(() => {
  // biome-ignore lint/correctness/noUndeclaredVariables: weblate_cookie_name defined externally
  let languages = [getCookie(weblate_cookie_name)];
  languages = languages.concat(navigator.languages);
  languages = languages.concat(navigator.language);
  languages = languages.concat(navigator.userLanguage);

  let language;
  for (const i in languages) {
    const code = languages[i];
    // biome-ignore lint/correctness/noUndeclaredVariables: weblate_supported defined externally
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
      // biome-ignore lint/correctness/noUndeclaredVariables: weblate_url defined externally
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
