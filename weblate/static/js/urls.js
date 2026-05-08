// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// biome-ignore lint/correctness/noInvalidUseBeforeDeclaration: Shared Weblate namespace.
var WLT = WLT || {};

WLT.URLs = (() => {
  function parse(url, base) {
    try {
      return new URL(String(url), base);
    } catch {
      return null;
    }
  }

  function getLocalPath(url) {
    const urlString = String(url).trim();
    if (
      urlString.startsWith("//") ||
      (!urlString.startsWith("/") && !/^https?:\/\//i.test(urlString))
    ) {
      return null;
    }
    const parsedUrl = parse(urlString, window.location.origin);
    if (
      parsedUrl === null ||
      (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:")
    ) {
      return null;
    }
    const path = parsedUrl.pathname.replace(/^\/+/, "/");
    return `${path}${parsedUrl.search}${parsedUrl.hash}`;
  }

  function getHttpUrl(url) {
    const parsedUrl = parse(url, window.location.href);
    if (
      parsedUrl === null ||
      (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:")
    ) {
      return null;
    }
    return parsedUrl.href;
  }

  return {
    getHttpUrl,
    getLocalPath,
  };
})();
