// Copyright © Michal Čihař <michal@weblate.org>
// SPDX-License-Identifier: GPL-3.0-or-later

// This script runs in a dedicated Worker, not a Window. Only its creator can
// send messages through this worker's private channel; window.postMessage cannot
// reach this handler. Worker message events have an empty origin, so checking
// against the page's origin would reject legitimate challenges.
// https://html.spec.whatwg.org/multipage/workers.html#dom-worker-postmessage
// ALTCHA v2 SHA-256 cost=1: SHA256(salt || nonce || uint32be(counter)).
self.onmessage = async ({ data: challenge }) => {
  const p = challenge.parameters;
  const bytes = new Uint8Array(36);
  bytes.set(
    Uint8Array.from((p.salt + p.nonce).match(/../g), (x) =>
      Number.parseInt(x, 16),
    ),
  );
  const view = new DataView(bytes.buffer);
  for (let counter = 0; counter <= 0xffffffff; counter++) {
    view.setUint32(32, counter);
    const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const derivedKey = Array.from(hash, (x) =>
      x.toString(16).padStart(2, "0"),
    ).join("");
    if (derivedKey.startsWith(p.keyPrefix)) {
      self.postMessage({ challenge, solution: { counter, derivedKey } });
      return;
    }
    if (counter % 4096 === 0) self.postMessage({ progress: counter });
  }
  throw new Error("counter exhausted");
};
