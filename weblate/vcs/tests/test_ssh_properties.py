# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import SimpleTestCase

from weblate.vcs.ssh import extract_url_host_port

HOSTS = st.one_of(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=24
    ).map(lambda label: f"{label}.example.com"),
    st.ip_addresses().map(str),
)


class SSHURLPropertyTest(SimpleTestCase):
    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(st.text(max_size=512))
    @example("")
    @example("ssh://[")
    @example("git@[::1:repo")
    @example("netlo[cbGF0ZSLmiBzZWV")
    @example("ssh://example.com:65536/repo")
    @example("ssh://example.com:invalid/repo")
    def test_arbitrary_urls_return_host_and_port(self, url: str) -> None:
        result = extract_url_host_port(url)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        host, port = result
        if host is None:
            self.assertIsNone(port)
        else:
            self.assertIsInstance(host, str)
            self.assertTrue(host)
        if port is not None:
            self.assertIsInstance(port, int)
            self.assertGreaterEqual(port, 0)
            self.assertLessEqual(port, 65535)

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(host=HOSTS, port=st.integers(min_value=1, max_value=65535))
    @example(host="example.com", port=2222)
    @example(host="::1", port=22)
    def test_ssh_urls_preserve_host_and_port(self, host: str, port: int) -> None:
        authority = f"[{host}]" if ":" in host else host
        self.assertEqual(
            extract_url_host_port(f"ssh://git@{authority}:{port}/owner/repo.git"),
            (host, port),
        )

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(host=HOSTS)
    @example(host="github.com")
    @example(host="::1")
    def test_scp_urls_preserve_host(self, host: str) -> None:
        authority = f"[{host}]" if ":" in host else host
        self.assertEqual(
            extract_url_host_port(f"git@{authority}:owner/repo.git"), (host, None)
        )
