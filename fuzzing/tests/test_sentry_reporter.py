# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fuzzing.sentry_reporter import (
    MAX_SUMMARY_LENGTH,
    CrashSummary,
    FuzzFinding,
    ReportConfig,
    build_envelope,
    build_event,
    build_report_config,
    collect_findings,
    parse_dsn,
    report_findings,
)


class FuzzingSentryReporterTest(TestCase):
    def test_collect_sarif_findings(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sarif_path = root / "results.sarif"
            artifacts_path = root / "artifacts"
            summary_path = artifacts_path / "backups" / "crash" / "crash.summary"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                "==1==ERROR: AddressSanitizer: heap-use-after-free\n",
                encoding="utf-8",
            )
            sarif_path.write_text(
                json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "results": [
                                    {
                                        "ruleId": "asan-crash",
                                        "message": {
                                            "text": "AddressSanitizer: heap-use-after-free"
                                        },
                                        "properties": {"target": "backups"},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "weblate/trans/backups.py"
                                                    },
                                                    "region": {"startLine": 42},
                                                }
                                            },
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": (
                                                            "out/artifacts/backups/"
                                                            "crash/crash.summary"
                                                        )
                                                    }
                                                }
                                            },
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            findings, summaries = collect_findings(sarif_path, artifacts_path)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].source, "sarif")
        self.assertEqual(findings[0].target, "backups")
        self.assertEqual(findings[0].location, "weblate/trans/backups.py:42")
        self.assertEqual(
            findings[0].crash_type, "AddressSanitizer: heap-use-after-free"
        )
        self.assertIsNotNone(findings[0].summary)

    def test_collect_findings_skips_directly_captured_python_sarif(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sarif_path = root / "results.sarif"
            artifacts_path = root / "artifacts"
            summary_path = artifacts_path / "backups" / "crash" / "crash.summary"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                "Traceback (most recent call last):\n"
                "ValueError: unexpected backup failure\n",
                encoding="utf-8",
            )
            sarif_path.write_text(
                json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "results": [
                                    {
                                        "ruleId": "python-exception",
                                        "message": {
                                            "text": "ValueError: unexpected backup failure"
                                        },
                                        "properties": {"target": "backups"},
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            findings, summaries = collect_findings(sarif_path, artifacts_path)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(findings, [])

    def test_collect_findings_includes_summary_only_crashes_with_sarif(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sarif_path = root / "results.sarif"
            artifacts_path = root / "artifacts"
            sarif_summary_path = artifacts_path / "backups" / "crash" / "crash.summary"
            summary_only_path = artifacts_path / "webhooks" / "oom" / "oom.summary"
            sarif_summary_path.parent.mkdir(parents=True)
            summary_only_path.parent.mkdir(parents=True)
            sarif_summary_path.write_text(
                "==1==ERROR: AddressSanitizer: heap-use-after-free\n",
                encoding="utf-8",
            )
            summary_only_path.write_text(
                "SUMMARY: libFuzzer: out-of-memory\n",
                encoding="utf-8",
            )
            sarif_path.write_text(
                json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "results": [
                                    {
                                        "ruleId": "asan-crash",
                                        "message": {
                                            "text": "AddressSanitizer: heap-use-after-free"
                                        },
                                        "properties": {"target": "backups"},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": (
                                                            "out/artifacts/backups/"
                                                            "crash/crash.summary"
                                                        )
                                                    }
                                                }
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            findings, summaries = collect_findings(sarif_path, artifacts_path)

        self.assertEqual(len(summaries), 2)
        self.assertEqual(len(findings), 2)
        self.assertEqual([finding.source for finding in findings], ["sarif", "summary"])
        self.assertEqual(findings[0].target, "backups")
        self.assertEqual(findings[1].target, "webhooks")
        self.assertEqual(findings[1].crash_type, "libFuzzer: out-of-memory")

    def test_collect_findings_does_not_match_unrelated_target_summary(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sarif_path = root / "results.sarif"
            artifacts_path = root / "artifacts"
            python_summary_path = (
                artifacts_path / "backups" / "python" / "crash.summary"
            )
            asan_summary_path = artifacts_path / "backups" / "asan" / "crash.summary"
            python_summary_path.parent.mkdir(parents=True)
            asan_summary_path.parent.mkdir(parents=True)
            python_summary_path.write_text(
                "Traceback (most recent call last):\n"
                "ValueError: unexpected backup failure\n",
                encoding="utf-8",
            )
            asan_summary_path.write_text(
                "==1==ERROR: AddressSanitizer: heap-use-after-free\n",
                encoding="utf-8",
            )
            sarif_path.write_text(
                json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "results": [
                                    {
                                        "ruleId": "asan-crash",
                                        "message": {
                                            "text": "AddressSanitizer: heap-use-after-free"
                                        },
                                        "properties": {"target": "backups"},
                                        "locations": [
                                            {
                                                "physicalLocation": {
                                                    "artifactLocation": {
                                                        "uri": "weblate/trans/backups.py"
                                                    },
                                                    "region": {"startLine": 42},
                                                }
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            findings, summaries = collect_findings(sarif_path, artifacts_path)

        self.assertEqual(len(summaries), 2)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0].source, "sarif")
        self.assertIsNone(findings[0].summary)
        self.assertEqual(findings[0].target, "backups")
        self.assertEqual(findings[1].source, "summary")
        self.assertEqual(findings[1].target, "backups")

    def test_collect_summary_findings_skips_directly_captured_python_exception(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_path = root / "artifacts"
            summary_path = artifacts_path / "backups" / "crash" / "crash.summary"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                "Traceback (most recent call last):\n"
                "ValueError: unexpected backup failure\n",
                encoding="utf-8",
            )

            findings, summaries = collect_findings(
                root / "missing.sarif", artifacts_path
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(findings, [])

    def test_collect_summary_findings_skips_bare_python_exception(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_path = root / "artifacts"
            summary_path = artifacts_path / "markup" / "crash" / "crash.summary"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                "Traceback (most recent call last):\n"
                "  File fuzzing/targets.py, line 1, in fuzz_markup\n"
                "AssertionError\n",
                encoding="utf-8",
            )

            findings, summaries = collect_findings(
                root / "missing.sarif", artifacts_path
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(findings, [])

    def test_collect_summary_findings_without_sarif(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_path = root / "artifacts"
            summary_path = artifacts_path / "webhooks" / "crash" / "crash.summary"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                "==1==ERROR: AddressSanitizer: heap-use-after-free\n",
                encoding="utf-8",
            )

            findings, summaries = collect_findings(
                root / "missing.sarif", artifacts_path
            )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].source, "summary")
        self.assertEqual(findings[0].target, "webhooks")
        self.assertEqual(
            findings[0].crash_type, "AddressSanitizer: heap-use-after-free"
        )

    def test_build_event_uses_stable_fingerprint_and_metadata(self) -> None:
        config = build_report_config(
            {
                "SENTRY_DSN": "https://public@example.invalid/1",
                "GITHUB_REPOSITORY": "WeblateOrg/weblate",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_SHA": "abc123",
                "GITHUB_WORKFLOW": "ClusterFuzzLite Batch Fuzzing",
            },
            mode="batch",
            sanitizer="address",
            environment="fuzzing-batch",
        )
        finding = FuzzFinding(
            source="sarif",
            rule_id="python-exception",
            target="backups",
            message="ValueError: unexpected backup failure",
            crash_type="ValueError: unexpected backup failure",
            location="weblate/trans/backups.py:42",
        )

        event = build_event(finding, config)

        self.assertEqual(event["environment"], "fuzzing-batch")
        self.assertEqual(event["release"], "abc123")
        self.assertEqual(
            event["fingerprint"],
            [
                "clusterfuzzlite",
                "address",
                "backups",
                "ValueError",
                "weblate/trans/backups.py:42",
            ],
        )
        self.assertEqual(event["tags"]["source"], "clusterfuzzlite")
        self.assertEqual(event["tags"]["mode"], "batch")
        self.assertEqual(event["tags"]["sha"], "abc123")
        self.assertEqual(
            event["contexts"]["github_actions"]["run_url"],
            "https://github.com/WeblateOrg/weblate/actions/runs/123",
        )

    def test_build_event_truncates_summary(self) -> None:
        config = ReportConfig(
            dsn="https://public@example.invalid/1",
            mode="batch",
            sanitizer="address",
            environment="fuzzing-batch",
            release="abc123",
            workflow="workflow",
            run_id="123",
            run_attempt="1",
            sha="abc123",
            repository="WeblateOrg/weblate",
            run_url="https://github.com/WeblateOrg/weblate/actions/runs/123",
            artifact_names=("summaries", "sarif"),
        )
        finding = FuzzFinding(
            source="summary",
            rule_id="crash",
            target="backups",
            message="ValueError: unexpected backup failure",
            crash_type="ValueError: unexpected backup failure",
            location="unknown",
            summary=CrashSummary(
                path=Path("out/artifacts/backups/crash.summary"),
                target="backups",
                text="x" * (MAX_SUMMARY_LENGTH + 10),
                crash_type="ValueError: unexpected backup failure",
            ),
        )

        event = build_event(finding, config)

        self.assertLessEqual(len(event["extra"]["summary"]), MAX_SUMMARY_LENGTH + 15)
        self.assertTrue(event["extra"]["summary"].endswith("... [truncated]"))

    def test_parse_dsn_supports_path_prefix(self) -> None:
        parsed = parse_dsn("https://public@sentry.example.com/prefix/42")

        self.assertEqual(parsed.public_key, "public")
        self.assertEqual(
            parsed.endpoint,
            "https://sentry.example.com/prefix/api/42/envelope/",
        )

    def test_build_envelope(self) -> None:
        event = {"event_id": "a" * 32, "message": "test"}

        public_key, envelope = build_envelope(
            event, "https://public@sentry.example.com/42"
        )

        self.assertEqual(public_key, "public")
        self.assertIn(b'"type": "event"', envelope)
        self.assertIn(b'"message": "test"', envelope)

    @patch("fuzzing.sentry_reporter.send_sentry_event")
    def test_report_findings_sends_sentry_events(self, send_sentry_event_mock) -> None:
        config = ReportConfig(
            dsn="https://public@example.invalid/1",
            mode="batch",
            sanitizer="address",
            environment="fuzzing-batch",
            release="abc123",
            workflow="workflow",
            run_id="123",
            run_attempt="1",
            sha="abc123",
            repository="WeblateOrg/weblate",
            run_url="https://github.com/WeblateOrg/weblate/actions/runs/123",
            artifact_names=("summaries", "sarif"),
        )
        findings = [
            FuzzFinding(
                source="summary",
                rule_id="crash",
                target="backups",
                message="ValueError: unexpected backup failure",
                crash_type="ValueError: unexpected backup failure",
                location="unknown",
            )
        ]

        reported = report_findings(findings, config)

        self.assertEqual(reported, 1)
        send_sentry_event_mock.assert_called_once()

    @patch("fuzzing.sentry_reporter.send_sentry_event")
    def test_report_findings_ignores_sentry_transport_errors(
        self, send_sentry_event_mock
    ) -> None:
        config = ReportConfig(
            dsn="https://public@example.invalid/1",
            mode="batch",
            sanitizer="address",
            environment="fuzzing-batch",
            release="abc123",
            workflow="workflow",
            run_id="123",
            run_attempt="1",
            sha="abc123",
            repository="WeblateOrg/weblate",
            run_url="https://github.com/WeblateOrg/weblate/actions/runs/123",
            artifact_names=("summaries", "sarif"),
        )
        findings = [
            FuzzFinding(
                source="summary",
                rule_id="first-crash",
                target="backups",
                message="AddressSanitizer: heap-use-after-free",
                crash_type="AddressSanitizer: heap-use-after-free",
                location="unknown",
            ),
            FuzzFinding(
                source="summary",
                rule_id="second-crash",
                target="webhooks",
                message="AddressSanitizer: stack-buffer-overflow",
                crash_type="AddressSanitizer: stack-buffer-overflow",
                location="unknown",
            ),
        ]
        send_sentry_event_mock.side_effect = [OSError("network down"), None]

        reported = report_findings(findings, config)

        self.assertEqual(reported, 1)
        self.assertEqual(send_sentry_event_mock.call_count, 2)
