// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: MIT

Prism.languages.weblatesearch = {
  string: {
    pattern: /r?("[^"]*"|'[^']*')/,
  },
  important: {
    pattern: /\b[a-z_]+:=?[<>]?/i,
    inside: {
      punctuation: /[:=<>]+$/,
    },
  },
  operator: /\b(and|not|or)\b/i,
};
