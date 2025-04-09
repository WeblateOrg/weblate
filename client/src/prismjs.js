// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import Prism from "prismjs";
// biome-ignore lint/correctness/noUndeclaredDependencies: manual import
import "prismjs/components/prism-markup";
// biome-ignore lint/correctness/noUndeclaredDependencies: manual import
import "prismjs/components/prism-rest";
// biome-ignore lint/correctness/noUndeclaredDependencies: manual import
import "prismjs/components/prism-markdown";
// biome-ignore lint/correctness/noUndeclaredDependencies: manual import
import "prismjs/components/prism-icu-message-format";

window.Prism = Prism;
