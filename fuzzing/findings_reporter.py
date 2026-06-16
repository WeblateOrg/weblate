# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from html import escape as html_escape
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Mapping

LOGGER = logging.getLogger(__name__)

DEFAULT_SARIF_PATH = Path("cifuzz-sarif/results.sarif")
DEFAULT_ARTIFACTS_PATH = Path("out/artifacts")
MAX_SUMMARY_LENGTH = 8000
MAX_CONTEXT_LENGTH = 512
MAX_REPORT_SUMMARY_LENGTH = 8000
MAX_REPORT_SUMMARY_LINES = 120
MAX_REPORT_ARTIFACT_FILES = 20
UNKNOWN = "unknown"

_ASAN_RE = re.compile(r"ERROR:\s*([^:\n]+):\s*([^\n]+)")
_SUMMARY_RE = re.compile(r"SUMMARY:\s*([^:\n]+):\s*([^\n]+)")
_PYTHON_EXCEPTION_RE = re.compile(
    r"^([A-Za-z_][\w.]*?(?:Error|Exception|Warning|Interrupt|Exit))(?:\s*:\s*(.*))?$",
    re.MULTILINE,
)
_PYTHON_EXCEPTION_RULE_IDS = frozenset(
    {
        "python-exception",
        "python_exception",
        "python exception",
    }
)


@dataclass(slots=True)
class CrashSummary:
    path: Path
    target: str
    text: str
    crash_type: str


@dataclass(slots=True)
class FuzzFinding:
    source: str
    rule_id: str
    target: str
    message: str
    crash_type: str
    location: str
    summary: CrashSummary | None = None


@dataclass(slots=True)
class ReportConfig:
    dsn: str
    mode: str
    sanitizer: str
    environment: str
    release: str
    workflow: str
    run_id: str
    run_attempt: str
    sha: str
    repository: str
    run_url: str
    artifact_names: tuple[str, ...]


@dataclass(slots=True)
class ParsedDsn:
    public_key: str
    endpoint: str


def truncate(value: str, limit: int = MAX_CONTEXT_LENGTH) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated]"


def clean_tag(value: str) -> str:
    return truncate(value or UNKNOWN, 200)


def extract_crash_type(text: str) -> str:
    for regex in (_ASAN_RE, _SUMMARY_RE, _PYTHON_EXCEPTION_RE):
        match = regex.search(text)
        if match:
            return truncate(": ".join(group for group in match.groups() if group))

    for line in text.splitlines():
        line = line.strip()
        if line:
            return truncate(line)

    return UNKNOWN


def is_python_exception_text(text: str) -> bool:
    return bool(_PYTHON_EXCEPTION_RE.search(text))


def is_python_exception_rule(rule_id: str) -> bool:
    normalized = rule_id.lower().replace("-", " ").replace("_", " ")
    return normalized in _PYTHON_EXCEPTION_RULE_IDS or (
        "python" in normalized and "exception" in normalized
    )


def is_directly_captured_python_exception(
    result: dict[str, Any], message: str, summary: CrashSummary | None
) -> bool:
    rule_id = result.get("ruleId", "")
    if isinstance(rule_id, str) and is_python_exception_rule(rule_id):
        return True

    text = message if summary is None else f"{message}\n{summary.text}"
    return is_python_exception_text(text)


def summary_target(path: Path, artifacts_path: Path) -> str:
    try:
        relative = path.relative_to(artifacts_path)
    except ValueError:
        return UNKNOWN
    return relative.parts[0] if relative.parts else UNKNOWN


def collect_crash_summaries(artifacts_path: Path) -> list[CrashSummary]:
    if not artifacts_path.exists():
        return []

    summaries = []
    for summary_path in sorted(artifacts_path.glob("**/*.summary")):
        text = summary_path.read_text(errors="replace")
        summaries.append(
            CrashSummary(
                path=summary_path,
                target=summary_target(summary_path, artifacts_path),
                text=text,
                crash_type=extract_crash_type(text),
            )
        )
    return summaries


def message_text(result: dict[str, Any]) -> str:
    message = result.get("message")
    if isinstance(message, dict):
        text = message.get("text") or message.get("markdown")
        if isinstance(text, str):
            return text
    return result.get("ruleId", UNKNOWN)


def physical_location(location: dict[str, Any]) -> tuple[str, int | None]:
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return "", None

    artifact = physical.get("artifactLocation")
    uri = artifact.get("uri", "") if isinstance(artifact, dict) else ""

    region = physical.get("region")
    line = region.get("startLine") if isinstance(region, dict) else None
    return uri, line if isinstance(line, int) else None


def iter_result_locations(result: dict[str, Any]) -> list[tuple[str, int | None]]:
    locations = [
        physical_location(location)
        for location in result.get("locations", [])
        if isinstance(location, dict)
    ]

    for stack in result.get("stacks", []):
        if not isinstance(stack, dict):
            continue
        for frame in stack.get("frames", []):
            if not isinstance(frame, dict):
                continue
            location = frame.get("location")
            if isinstance(location, dict):
                locations.append(physical_location(location))

    return [(uri, line) for uri, line in locations if uri]


def format_location(result: dict[str, Any]) -> str:
    for uri, line in iter_result_locations(result):
        if line is None:
            return uri
        return f"{uri}:{line}"
    return UNKNOWN


def target_from_uri(uri: str) -> str:
    marker = "out/artifacts/"
    if marker not in uri:
        return UNKNOWN
    target = uri.split(marker, 1)[1].split("/", 1)[0]
    return target or UNKNOWN


def target_from_result(result: dict[str, Any]) -> str:
    properties = result.get("properties")
    if isinstance(properties, dict):
        for key in ("target", "fuzzTarget", "fuzz_target", "fuzzer"):
            value = properties.get(key)
            if isinstance(value, str) and value:
                return value

    for uri, _line in iter_result_locations(result):
        target = target_from_uri(uri)
        if target != UNKNOWN:
            return target

    return UNKNOWN


def normalized_location_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    path = parsed.path if parsed.scheme else uri
    return path.replace("\\", "/").strip("/")


def path_contains_segment(path: str, segment: str) -> bool:
    normalized_path = f"/{path.strip('/')}/"
    normalized_segment = f"/{segment.strip('/')}/"
    return normalized_segment in normalized_path


def summary_relative_path(summary: CrashSummary, artifacts_path: Path) -> str:
    try:
        return summary.path.relative_to(artifacts_path).as_posix()
    except ValueError:
        return summary.path.as_posix()


def summary_matches_result(
    summary: CrashSummary, result: dict[str, Any], artifacts_path: Path
) -> bool:
    relative_path = summary_relative_path(summary, artifacts_path)
    relative_parent = Path(relative_path).parent.as_posix()
    if relative_parent == "." or relative_parent.count("/") < 1:
        relative_parent = ""

    for uri, _line in iter_result_locations(result):
        normalized_uri = normalized_location_uri(uri)
        if path_contains_segment(normalized_uri, relative_path):
            return True
        if relative_parent and path_contains_segment(normalized_uri, relative_parent):
            return True
    return False


def matching_summary(
    result: dict[str, Any], summaries: list[CrashSummary], artifacts_path: Path
) -> CrashSummary | None:
    for summary in summaries:
        if summary_matches_result(summary, result, artifacts_path):
            return summary
    return None


def collect_sarif_findings(
    sarif_path: Path, summaries: list[CrashSummary], artifacts_path: Path
) -> list[FuzzFinding]:
    if not sarif_path.exists():
        return []

    with sarif_path.open(encoding="utf-8") as handle:
        sarif_data = json.load(handle)

    findings = []
    for run in sarif_data.get("runs", []):
        if not isinstance(run, dict):
            continue
        for result in run.get("results", []):
            if not isinstance(result, dict):
                continue
            target = target_from_result(result)
            matched_summary = matching_summary(result, summaries, artifacts_path)
            message = message_text(result)
            if is_directly_captured_python_exception(result, message, matched_summary):
                continue
            findings.append(
                FuzzFinding(
                    source="sarif",
                    rule_id=result.get("ruleId", UNKNOWN),
                    target=target,
                    message=message,
                    crash_type=extract_crash_type(
                        f"{message}\n{matched_summary.text if matched_summary else ''}"
                    ),
                    location=format_location(result),
                    summary=matched_summary,
                )
            )
    return findings


def collect_findings(
    sarif_path: Path, artifacts_path: Path
) -> tuple[list[FuzzFinding], list[CrashSummary]]:
    summaries = collect_crash_summaries(artifacts_path)
    sarif_findings = collect_sarif_findings(sarif_path, summaries, artifacts_path)
    sarif_summary_paths = {
        finding.summary.path for finding in sarif_findings if finding.summary
    }

    summary_findings = [
        FuzzFinding(
            source="summary",
            rule_id=summary.path.stem,
            target=summary.target,
            message=summary.crash_type,
            crash_type=summary.crash_type,
            location=UNKNOWN,
            summary=summary,
        )
        for summary in summaries
        if summary.path not in sarif_summary_paths
        if not is_python_exception_text(summary.text)
    ]
    return deduplicate_findings([*sarif_findings, *summary_findings]), summaries


def deduplicate_findings(findings: list[FuzzFinding]) -> list[FuzzFinding]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduplicated = []
    for finding in findings:
        key = finding_key(finding)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(finding)
    return deduplicated


def finding_key(finding: FuzzFinding) -> tuple[str, str, str, str, str]:
    return (
        finding.source,
        finding.rule_id,
        finding.target,
        fingerprint_crash_type(finding.crash_type),
        fingerprint_location(finding.location),
    )


def fingerprint_crash_type(crash_type: str) -> str:
    if not crash_type or crash_type == UNKNOWN:
        return UNKNOWN
    return crash_type.split(":", 1)[0]


def fingerprint_location(location: str) -> str:
    if location.startswith("out/artifacts/"):
        return UNKNOWN
    return location or UNKNOWN


def count_sarif_results(sarif_path: Path) -> int | None:
    if not sarif_path.exists():
        return None

    with sarif_path.open(encoding="utf-8") as handle:
        sarif_data = json.load(handle)

    count = 0
    for run in sarif_data.get("runs", []):
        if not isinstance(run, dict):
            continue
        results = run.get("results", [])
        if isinstance(results, list):
            count += len(results)
    return count


def display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def display_value(value: str) -> str:
    return value if value and value != UNKNOWN else UNKNOWN


def report_source_label(finding: FuzzFinding) -> str:
    if finding.source == "sarif" and finding.summary:
        return "SARIF + crash summary"
    if finding.source == "sarif":
        return "SARIF"
    if finding.source == "summary":
        return "crash summary"
    return finding.source


def summary_excerpt_text(text: str) -> str:
    text = text.strip()
    if not text:
        return "(empty)"

    lines = text.splitlines()
    excerpt = "\n".join(lines[:MAX_REPORT_SUMMARY_LINES])
    truncated = len(lines) > MAX_REPORT_SUMMARY_LINES

    if len(excerpt) > MAX_REPORT_SUMMARY_LENGTH:
        excerpt = excerpt[:MAX_REPORT_SUMMARY_LENGTH]
        truncated = True

    if truncated:
        excerpt = f"{excerpt}\n... [truncated]"
    return excerpt


def format_summary_excerpt(text: str) -> list[str]:
    return [f"  {line}" for line in summary_excerpt_text(text).splitlines()]


def summary_artifact_files(summary: CrashSummary) -> list[Path]:
    directory = summary.path.parent
    if not directory.exists():
        return []

    return sorted(path for path in directory.iterdir() if path.is_file())


def append_summary_report(lines: list[str], summary: CrashSummary) -> None:
    lines.extend(
        (
            f"Summary file: {display_path(summary.path)}",
            f"Artifact directory: {display_path(summary.path.parent)}",
        )
    )

    artifact_files = summary_artifact_files(summary)
    if artifact_files:
        lines.append("Artifact files:")
        lines.extend(
            f"  - {artifact_file.name}"
            for artifact_file in artifact_files[:MAX_REPORT_ARTIFACT_FILES]
        )
        if len(artifact_files) > MAX_REPORT_ARTIFACT_FILES:
            lines.append(
                f"  - ... {len(artifact_files) - MAX_REPORT_ARTIFACT_FILES} more"
            )

    lines.append("Summary excerpt:")
    lines.extend(format_summary_excerpt(summary.text))


def format_findings_report(
    findings: list[FuzzFinding],
    summaries: list[CrashSummary],
    *,
    sarif_path: Path = DEFAULT_SARIF_PATH,
    artifacts_path: Path = DEFAULT_ARTIFACTS_PATH,
) -> str:
    sarif_results = count_sarif_results(sarif_path)
    lines = [
        "Fuzzing report",
        "==============",
        f"SARIF results: {sarif_results if sarif_results is not None else 'not generated'}",
        f"Artifact root: {display_path(artifacts_path)}",
        f"Crash summary files: {len(summaries)}",
        f"Findings: {len(findings)}",
    ]

    if not findings and not summaries:
        lines.extend(("", "No fuzz findings found."))
        return "\n".join(lines)

    for index, finding in enumerate(findings, start=1):
        source = report_source_label(finding)
        lines.extend(
            (
                "",
                f"Finding {index}",
                "-" * len(f"Finding {index}"),
                f"Target: {display_value(finding.target)}",
                f"Source: {source}",
                f"Rule: {display_value(finding.rule_id)}",
                f"Crash: {display_value(finding.crash_type)}",
                f"Likely location: {display_value(finding.location)}",
            )
        )
        if finding.message and finding.message != finding.crash_type:
            lines.append(f"Message: {truncate(finding.message, MAX_CONTEXT_LENGTH)}")
        if finding.summary:
            append_summary_report(lines, finding.summary)

    finding_summary_paths = {
        finding.summary.path for finding in findings if finding.summary is not None
    }
    additional_summaries = [
        summary for summary in summaries if summary.path not in finding_summary_paths
    ]
    if additional_summaries:
        lines.extend(("", "Additional crash summaries", "--------------------------"))
        for index, summary in enumerate(additional_summaries, start=1):
            lines.extend(
                ("", f"Summary {index}", f"Target: {display_value(summary.target)}")
            )
            lines.append(f"Crash: {display_value(summary.crash_type)}")
            append_summary_report(lines, summary)

    return "\n".join(lines)


def markdown_text(value: str) -> str:
    return html_escape(display_value(value))


def markdown_code(value: str) -> str:
    value = display_value(value).replace("\n", " ")
    if value == UNKNOWN:
        return UNKNOWN
    if "`" in value:
        return f"`` {html_escape(value)} ``"
    return f"`{html_escape(value)}`"


def markdown_code_block(value: str) -> str:
    value = summary_excerpt_text(value)
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", value)),
        default=0,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    return f"{fence}text\n{value}\n{fence}"


def append_summary_markdown(lines: list[str], summary: CrashSummary) -> None:
    lines.extend(
        (
            f"- Summary file: {markdown_code(display_path(summary.path))}",
            f"- Artifact directory: {markdown_code(display_path(summary.path.parent))}",
        )
    )

    artifact_files = summary_artifact_files(summary)
    if artifact_files:
        lines.extend(("", "Artifact files:"))
        lines.extend(
            f"- {markdown_code(artifact_file.name)}"
            for artifact_file in artifact_files[:MAX_REPORT_ARTIFACT_FILES]
        )
        if len(artifact_files) > MAX_REPORT_ARTIFACT_FILES:
            lines.append(
                f"- ... {len(artifact_files) - MAX_REPORT_ARTIFACT_FILES} more"
            )

    lines.extend(
        (
            "",
            "<details>",
            "<summary>Summary excerpt</summary>",
            "",
            markdown_code_block(summary.text),
            "",
            "</details>",
        )
    )


def format_findings_step_summary(
    findings: list[FuzzFinding],
    summaries: list[CrashSummary],
    *,
    sarif_path: Path = DEFAULT_SARIF_PATH,
    artifacts_path: Path = DEFAULT_ARTIFACTS_PATH,
) -> str:
    sarif_results = count_sarif_results(sarif_path)
    lines = [
        "## Fuzzing report",
        "",
        f"- SARIF results: {sarif_results if sarif_results is not None else 'not generated'}",
        f"- Artifact root: {markdown_code(display_path(artifacts_path))}",
        f"- Crash summary files: {len(summaries)}",
        f"- Findings: {len(findings)}",
    ]

    if not findings and not summaries:
        lines.extend(("", "No fuzz findings found."))
        return "\n".join(lines)

    for index, finding in enumerate(findings, start=1):
        lines.extend(
            (
                "",
                f"### Finding {index}",
                "",
                f"- Target: {markdown_code(finding.target)}",
                f"- Source: {markdown_text(report_source_label(finding))}",
                f"- Rule: {markdown_code(finding.rule_id)}",
                f"- Crash: {markdown_text(finding.crash_type)}",
                f"- Likely location: {markdown_code(finding.location)}",
            )
        )
        if finding.message and finding.message != finding.crash_type:
            lines.append(
                f"- Message: {markdown_text(truncate(finding.message, MAX_CONTEXT_LENGTH))}"
            )
        if finding.summary:
            append_summary_markdown(lines, finding.summary)

    finding_summary_paths = {
        finding.summary.path for finding in findings if finding.summary is not None
    }
    additional_summaries = [
        summary for summary in summaries if summary.path not in finding_summary_paths
    ]
    if additional_summaries:
        lines.extend(("", "### Additional crash summaries"))
        for index, summary in enumerate(additional_summaries, start=1):
            lines.extend(
                (
                    "",
                    f"#### Summary {index}",
                    "",
                    f"- Target: {markdown_code(summary.target)}",
                    f"- Crash: {markdown_text(summary.crash_type)}",
                )
            )
            append_summary_markdown(lines, summary)

    return "\n".join(lines)


def write_github_step_summary(
    markdown_report: str, environ: Mapping[str, str] | None = None
) -> bool:
    environ = os.environ if environ is None else environ
    summary_path = environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        LOGGER.info("GITHUB_STEP_SUMMARY is not configured; skipping step summary.")
        return False

    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write(markdown_report.rstrip())
        handle.write("\n")
    return True


def build_run_url(environ: Mapping[str, str]) -> str:
    repository = environ.get("GITHUB_REPOSITORY", "")
    run_id = environ.get("GITHUB_RUN_ID", "")
    if not repository or not run_id:
        return ""
    server_url = environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def build_report_config(
    environ: Mapping[str, str],
    *,
    mode: str,
    sanitizer: str,
    environment: str,
) -> ReportConfig:
    artifact_prefix = f"cflite-{mode}"
    return ReportConfig(
        dsn=environ.get("SENTRY_DSN", ""),
        mode=mode,
        sanitizer=sanitizer,
        environment=environment,
        release=environ.get("GITHUB_SHA", ""),
        workflow=environ.get("GITHUB_WORKFLOW", ""),
        run_id=environ.get("GITHUB_RUN_ID", ""),
        run_attempt=environ.get("GITHUB_RUN_ATTEMPT", ""),
        sha=environ.get("GITHUB_SHA", ""),
        repository=environ.get("GITHUB_REPOSITORY", ""),
        run_url=build_run_url(environ),
        artifact_names=(f"{artifact_prefix}-crash-summaries-{sanitizer}",),
    )


def event_message(finding: FuzzFinding, config: ReportConfig) -> str:
    target = f" in {finding.target}" if finding.target != UNKNOWN else ""
    detail = finding.crash_type if finding.crash_type != UNKNOWN else finding.message
    return truncate(
        f"ClusterFuzzLite {config.mode} finding{target}: {detail}",
        MAX_CONTEXT_LENGTH,
    )


def build_event(finding: FuzzFinding, config: ReportConfig) -> dict[str, Any]:
    tags = {
        "source": "clusterfuzzlite",
        "mode": config.mode,
        "sanitizer": config.sanitizer,
        "target": finding.target,
        "workflow": config.workflow,
        "run_id": config.run_id,
        "run_attempt": config.run_attempt,
        "sha": config.sha,
    }
    clean_tags = {key: clean_tag(value) for key, value in tags.items() if value}

    extra: dict[str, Any] = {
        "sarif_message": truncate(finding.message),
        "artifact_names": list(config.artifact_names),
    }
    if finding.summary:
        extra.update(
            {
                "summary_path": str(finding.summary.path),
                "summary": truncate(finding.summary.text, MAX_SUMMARY_LENGTH),
            }
        )

    return {
        "level": "error",
        "event_id": uuid.uuid4().hex,
        "timestamp": time.time(),
        "message": event_message(finding, config),
        "release": config.release or None,
        "environment": config.environment,
        "fingerprint": [
            "clusterfuzzlite",
            config.sanitizer or UNKNOWN,
            finding.target or UNKNOWN,
            fingerprint_crash_type(finding.crash_type) or finding.rule_id or UNKNOWN,
            fingerprint_location(finding.location),
        ],
        "tags": clean_tags,
        "contexts": {
            "clusterfuzzlite": {
                "source": finding.source,
                "mode": config.mode,
                "sanitizer": config.sanitizer,
                "target": finding.target,
                "rule_id": finding.rule_id,
                "crash_type": finding.crash_type,
                "location": finding.location,
            },
            "github_actions": {
                "repository": config.repository,
                "workflow": config.workflow,
                "run_id": config.run_id,
                "run_attempt": config.run_attempt,
                "sha": config.sha,
                "run_url": config.run_url,
            },
        },
        "extra": extra,
    }


def report_findings(findings: list[FuzzFinding], config: ReportConfig) -> int:
    if not findings:
        LOGGER.info("No fuzz findings to report to Sentry.")
        return 0

    if not config.dsn:
        LOGGER.info("SENTRY_DSN is not configured; skipping Sentry fuzz reporting.")
        return 0

    reported = 0
    for finding in findings:
        try:
            send_sentry_event(build_event(finding, config), config.dsn)
        except (OSError, ValueError) as error:
            LOGGER.warning("Could not report fuzz finding to Sentry: %s", error)
            continue
        reported += 1

    return reported


def parse_dsn(dsn: str) -> ParsedDsn:
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported Sentry DSN scheme: {parsed.scheme}"
        raise ValueError(msg)
    if not parsed.username:
        msg = "Sentry DSN is missing the public key."
        raise ValueError(msg)

    path = parsed.path.rstrip("/")
    project_id = path.rsplit("/", 1)[-1]
    path_prefix = path[: -len(project_id)].rstrip("/")
    endpoint = (
        f"{parsed.scheme}://{parsed.hostname}"
        f"{f':{parsed.port}' if parsed.port else ''}"
        f"{path_prefix}/api/{project_id}/envelope/"
    )
    return ParsedDsn(public_key=parsed.username, endpoint=endpoint)


def build_envelope(event: dict[str, Any], dsn: str) -> tuple[str, bytes]:
    parsed = parse_dsn(dsn)
    envelope = "\n".join(
        (
            json.dumps({"event_id": event["event_id"]}),
            json.dumps({"type": "event"}),
            json.dumps(event),
        )
    ).encode()
    return parsed.public_key, envelope


def send_sentry_event(event: dict[str, Any], dsn: str) -> None:
    parsed = parse_dsn(dsn)
    _public_key, envelope = build_envelope(event, dsn)
    # ruff: ignore[suspicious-url-open-usage]
    request = Request(
        parsed.endpoint,
        data=envelope,
        headers={
            "Content-Type": "application/x-sentry-envelope",
            "User-Agent": "weblate-fuzzing-sentry-reporter",
            "X-Sentry-Auth": (
                "Sentry sentry_version=7, "
                "sentry_client=weblate-fuzzing-sentry-reporter, "
                f"sentry_key={parsed.public_key}"
            ),
        },
        method="POST",
    )
    # ruff: ignore[suspicious-url-open-usage]
    with urlopen(request, timeout=10) as response:
        response.read()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report ClusterFuzzLite findings to the console and Sentry."
    )
    parser.add_argument("--sarif", type=Path, default=DEFAULT_SARIF_PATH)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS_PATH)
    parser.add_argument("--mode", default=os.environ.get("CFLITE_MODE", "batch"))
    parser.add_argument("--sanitizer", default=os.environ.get("SANITIZER", "address"))
    parser.add_argument("--environment", default="")
    parser.add_argument(
        "--print-report",
        action="store_true",
        help="Print a human-readable findings report to stdout.",
    )
    parser.add_argument(
        "--github-step-summary",
        action="store_true",
        help="Append a Markdown findings report to GITHUB_STEP_SUMMARY.",
    )
    parser.add_argument(
        "--no-sentry",
        action="store_true",
        help="Skip reporting findings to Sentry.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level)

    environment = args.environment or f"fuzzing-{args.mode}"
    config = build_report_config(
        os.environ,
        mode=args.mode,
        sanitizer=args.sanitizer,
        environment=environment,
    )
    findings, summaries = collect_findings(args.sarif, args.artifacts)
    if args.print_report:
        sys.stdout.write(
            format_findings_report(
                findings,
                summaries,
                sarif_path=args.sarif,
                artifacts_path=args.artifacts,
            )
            + "\n"
        )
    if args.github_step_summary:
        write_github_step_summary(
            format_findings_step_summary(
                findings,
                summaries,
                sarif_path=args.sarif,
                artifacts_path=args.artifacts,
            )
        )
    reported = 0 if args.no_sentry else report_findings(findings, config)
    LOGGER.info(
        "Processed %d crash summary file(s), %d finding(s), reported %d event(s).",
        len(summaries),
        len(findings),
        reported,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
