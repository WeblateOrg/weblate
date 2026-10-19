# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Synthetic PostgreSQL experiments, separate from production search behavior.

Run in a checkout's isolated development container::

    ./scripts/devcontainer --backend compose up
    ./scripts/devcontainer --backend compose exec -- \
        python scripts/benchmark-search.py --prepare --profile smoke
    ./scripts/devcontainer --backend compose exec -- \
        python scripts/benchmark-search.py --prepare --profile representative

The profiles use separate test_search_benchmark_* databases, created through
Django's test database setup. Preparation refuses to overwrite fixture data.
Omit --prepare to repeat measurements without rebuilding. Results go to the
ignored reports/ directory; --cases selects named cases and --repetitions sets
the number of timed runs after one warm-up. Defaults are five timed runs and
all cases in both source scenarios. No cache flushing or planner overrides are
performed. The representative fixture has 6,700,260 units and all normal unit
indexes. Expect substantial disk, loading time, and query execution time.

Example of a shorter representative measurement::

    python scripts/benchmark-search.py --profile representative \
        --cases restricted-common --source-scenarios no-parents

Do not use this tool with production settings. Only the two dedicated test
database names are supported. It never changes production search code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q
from django.test.utils import setup_databases

from weblate.auth.models import Group, Role, User, UserBlock
from weblate.lang.models import Language, Plural
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.views.search import SEARCH_SUMMARY_MAX_STRINGS

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.trans.models.unit import UnitQuerySet


@dataclass(frozen=True)
class Profile:
    components: int
    strings: int


PROFILES = {
    "smoke": Profile(40, 32),
    "representative": Profile(8600, 371),
}


@dataclass(frozen=True)
class Case:
    name: str
    language: str
    term: str
    superuser: bool = False
    language_operator: Literal[":", ":="] = ":"


CASES = (
    Case("restricted-common", "pl", "test"),
    Case("superuser-common", "pl", "test", superuser=True),
    Case("restricted-rare", "pl", "rareword"),
    Case("restricted-absent", "pl", "nomatch"),
    Case("rare-language", "cs", "test"),
    Case("superuser-absent", "cs", "nomatch", superuser=True),
)
VARIANTS = tuple(product(("join", "ids"), ("join", "parent-in", "id-union")))
OPERATIONS = ("count", "sum", "page")
LOGGER = logging.getLogger(__name__)


def connect_database(profile: str, *, prepare: bool) -> None:
    """Select only the dedicated benchmark database."""
    if settings.SETTINGS_MODULE != "weblate.settings_test":
        msg = "Run with DJANGO_SETTINGS_MODULE=weblate.settings_test."
        raise ValueError(msg)
    if connection.vendor != "postgresql":
        msg = "The benchmark requires PostgreSQL."
        raise ValueError(msg)
    database = f"test_search_benchmark_{profile}"
    if prepare:
        settings.UPDATE_LANGUAGES = False
        connection.settings_dict.setdefault("TEST", {})["NAME"] = database
        setup_databases(
            verbosity=0,
            interactive=False,
            keepdb=True,
            aliases={"default": connection.settings_dict},
        )
    else:
        connection.close()
        connection.settings_dict["NAME"] = database
    if connection.settings_dict["NAME"] != database:
        msg = "Unexpected benchmark database."
        raise ValueError(msg)


def seed_fixture(profile: Profile, *, rebuild_indexes: bool = True) -> dict[str, int]:
    """Insert synthetic rows without model save hooks, repositories, or workers."""
    if Project.objects.exists() or Unit.objects.exists():
        msg = "Fixture already exists; omit --prepare to reuse it."
        raise ValueError(msg)

    codes = ["en", "pl", "cs", *(f"q{index:03d}" for index in range(797))]
    Language.objects.bulk_create(
        [Language(code=code, name=f"Benchmark {code}") for code in codes],
        ignore_conflicts=True,
    )
    Language.objects.exclude(code__in=codes).delete()
    languages = dict(Language.objects.values_list("code", "pk"))
    plurals = Plural.objects.bulk_create(
        [
            Plural(language_id=pk, number=1, formula="0", type=0)
            for pk in languages.values()
        ]
    )
    plural_ids = {plural.language_id: plural.pk for plural in plurals}
    projects = Project.objects.bulk_create(
        [
            Project(
                name=f"Benchmark {name}", slug=f"benchmark-{name}", access_control=acl
            )
            for name, acl in (
                ("public", Project.ACCESS_PUBLIC),
                ("protected", Project.ACCESS_PROTECTED),
                ("granted", Project.ACCESS_PRIVATE),
                ("denied", Project.ACCESS_PRIVATE),
                ("blocked", Project.ACCESS_PUBLIC),
            )
        ]
    )
    components = Component.objects.bulk_create(
        [
            Component(
                name=f"Benchmark {index}",
                slug=f"benchmark-{index}",
                project=projects[index % len(projects)],
                source_language_id=languages["en"],
                restricted=index % 13 == 0,
                vcs="local",
                repo="local:",
                filemask="*.po",
                file_format="po",
            )
            for index in range(profile.components)
        ],
        batch_size=500,
    )
    translations: list[Translation] = []
    for index, component in enumerate(components):
        translations.extend(
            Translation(
                component=component,
                language_id=languages[code],
                plural_id=plural_ids[languages[code]],
                filename=f"{code}.po",
                language_code=code,
            )
            for code in (("en", "pl", "cs") if index % 10 == 0 else ("en", "pl"))
        )
    Translation.objects.bulk_create(translations, batch_size=500)

    restricted = User.objects.create_user(
        "benchmark-restricted", email="benchmark@example.org", password=None
    )
    User.objects.create_user(
        "benchmark-superuser",
        email="benchmark-root@example.org",
        password=None,
        is_superuser=True,
    )
    role = Role.objects.get(name="Translate")
    project_group = Group.objects.create(name="Benchmark project grant")
    project_group.roles.add(role)
    project_group.projects.add(projects[2])
    component_group = Group.objects.create(name="Benchmark component grant")
    component_group.roles.add(role)
    component_group.components.add(
        *(
            component
            for index, component in enumerate(components)
            if index % 26 == 0 and index % len(projects) < 3
        )
    )
    restricted.groups.add(project_group, component_group)
    UserBlock.objects.create(user=restricted, project=projects[4])

    with connection.cursor() as cursor:
        # Retain constraints while loading; rebuild every ordinary production
        # index afterwards rather than maintaining several GIN indexes per row.
        cursor.execute(
            """SELECT index.relname, pg_get_indexdef(index.oid)
                 FROM pg_index idx JOIN pg_class index ON index.oid = idx.indexrelid
                WHERE idx.indrelid = 'trans_unit'::regclass
                  AND NOT EXISTS (SELECT FROM pg_constraint c
                                   WHERE c.conindid = index.oid)"""
        )
        indexes = cursor.fetchall() if rebuild_indexes else []
        for name, _definition in indexes:
            cursor.execute(f"DROP INDEX {connection.ops.quote_name(name)}")
        cursor.execute(
            """CREATE TEMP TABLE benchmark_translations AS
               SELECT t.id, t.component_id, l.code,
                      row_number() OVER (ORDER BY t.id) AS ordinal,
                      dense_rank() OVER (ORDER BY t.component_id) AS component_ordinal
                 FROM trans_translation t JOIN lang_language l ON l.id = t.language_id"""
        )
        # Explicit IDs let source-unit foreign keys be populated in one INSERT.
        # Source text varies by component and position, with independently
        # selective markers in source, target, context, and custom-source target.
        cursor.execute(
            """INSERT INTO trans_unit
               (id, translation_id, id_hash, source, target, context, location,
                note, flags, previous_source, state, original_state, details,
                position, num_words, priority, timestamp, last_updated,
                extra_flags, explanation, automatically_translated, source_unit_id,
                translation_parent_id, variant_id)
               SELECT (t.ordinal-1)*%(strings)s+s.pos+1, t.id, s.pos+1,
                      CASE WHEN k.key %% 719 = 0 THEN 'test source '
                           WHEN k.key = 3 THEN 'rareword source ' ELSE 'source ' END
                          || md5(k.key::text) || ' ' || md5((k.key+1)::text),
                      CASE WHEN t.code = 'cs' AND k.key %% 181 = 0 THEN 'test parent '
                           WHEN (t.ordinal*%(strings)s+s.pos) %% 911 = 0 THEN 'test target '
                           WHEN k.key = 7 THEN 'rareword target ' ELSE 'target ' END
                          || md5((k.key+2)::text),
                      CASE WHEN (t.ordinal*%(strings)s+s.pos) %% 1093 = 0
                           THEN 'test context ' ELSE 'context ' END || k.key::text,
                      '', '', '', '', 20, 20,
                      CASE WHEN k.key %% 211 = 0
                           THEN '{"translation_parent":{"missing":true}}'::jsonb
                           ELSE '{}'::jsonb END,
                      s.pos+1, 12, 100, now(), now(), '', '', false,
                      (src.ordinal-1)*%(strings)s+s.pos+1, NULL, NULL
                 FROM benchmark_translations t
                 JOIN benchmark_translations src
                   ON src.component_id = t.component_id AND src.code = 'en'
                CROSS JOIN generate_series(0, %(strings)s-1) s(pos)
                CROSS JOIN LATERAL (SELECT (t.component_ordinal-1)*%(strings)s+s.pos AS key) k""",
            {"strings": profile.strings},
        )
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('trans_unit', 'id'), max(id)) FROM trans_unit"
        )
        for name, definition in indexes:
            LOGGER.info("Building %s", name)
            cursor.execute(definition)
    analyze()
    return {
        "languages": Language.objects.count(),
        "components": Component.objects.count(),
        "translations": Translation.objects.count(),
        "units": Unit.objects.count(),
    }


def analyze() -> None:
    with connection.cursor() as cursor:
        for table in (
            "lang_language",
            "trans_project",
            "trans_component",
            "trans_translation",
            "trans_unit",
        ):
            cursor.execute(f"ANALYZE {table}")


def set_source_scenario(scenario: str) -> None:
    """Link Polish strings to available Czech source strings, or remove links."""
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE trans_unit SET translation_parent_id = NULL
                WHERE translation_parent_id IS NOT NULL"""
        )
        if scenario == "mixed":
            cursor.execute(
                """UPDATE trans_unit child SET translation_parent_id = parent.id
                     FROM trans_translation ct, lang_language cl,
                          trans_translation pt, lang_language pl, trans_unit parent
                    WHERE child.translation_id = ct.id AND ct.language_id = cl.id
                      AND cl.code = 'pl' AND pt.component_id = ct.component_id
                      AND pt.language_id = pl.id AND pl.code = 'cs'
                      AND parent.translation_id = pt.id AND parent.id_hash = child.id_hash
                      AND mod(child.position, 2) = 0"""
            )
    analyze()


def matching_units(
    user: User,
    language: str,
    term: str,
    language_shape: str,
    source_shape: str,
    *,
    language_operator: Literal[":", ":="] = ":",
) -> UnitQuerySet:
    """Construct one experiment without modifying production parsing."""
    units = Unit.objects.filter_access(user)
    suffix = "__exact" if language_operator == ":=" else "__iexact"
    if language_shape == "join":
        units = units.filter(**{f"translation__language__code{suffix}": language})
    else:
        language_ids = list(
            Language.objects.filter(**{f"code{suffix}": language}).values_list(
                "pk", flat=True
            )
        )
        units = units.filter(translation__language_id__in=language_ids)
    canonical = Q(
        translation_parent__isnull=True,
        details__translation_parent__missing__isnull=True,
        source__substring=term,
    )
    local = canonical | Q(target__substring=term) | Q(context__substring=term)
    if source_shape == "join":
        parent = Q(
            translation_parent__isnull=False, translation_parent__target__substring=term
        )
        return units.filter(local | parent)
    if source_shape == "parent-in":
        parents = Unit.objects.filter(target__substring=term).order_by().values("pk")
        return units.filter(local | Q(translation_parent_id__in=parents))
    local_ids = Unit.objects.filter(local).order_by().values("pk")
    parent_ids = (
        Unit.objects.filter(translation_parent__target__substring=term)
        .order_by()
        .values("pk")
    )
    return units.filter(pk__in=local_ids.union(parent_ids))


def operation_sql(units: UnitQuerySet, operation: str) -> tuple[str, tuple]:
    if operation == "page":
        return units.order_by("-priority", "position", "pk")[
            :22
        ].query.sql_with_params()
    field = "pk" if operation == "count" else "num_words"
    sql, params = units.order_by().values(field).query.sql_with_params()
    aggregate = "COUNT(*)" if operation == "count" else 'SUM("num_words")'
    # Both fragments are compiler-generated or fixed; values remain bound.
    return f"SELECT {aggregate} FROM ({sql}) search_matches", params  # ruff: ignore[hardcoded-sql-expression]


def correctness(user: User, case: Case, output: Path) -> dict[str, Any]:
    """Compare all variants against the actual production parser."""
    production = Unit.objects.filter_access(user).search(
        f"{case.term} language{case.language_operator}{case.language}"
    )
    expected = list(production.order_by("pk").values_list("pk", "num_words"))
    expected_page = list(
        production.order_by("-priority", "position", "pk").values_list("pk", flat=True)[
            :22
        ]
    )
    if len(expected) != len({pk for pk, _words in expected}):
        msg = "Production query unexpectedly returned duplicate units."
        raise AssertionError(msg)
    for language_shape, source_shape in VARIANTS:
        units = matching_units(
            user,
            case.language,
            case.term,
            language_shape,
            source_shape,
            language_operator=case.language_operator,
        )
        actual = list(units.order_by("pk").values_list("pk", "num_words"))
        actual_page = list(
            units.order_by("-priority", "position", "pk").values_list("pk", flat=True)[
                :22
            ]
        )
        if actual != expected or actual_page != expected_page:
            msg = f"Different results for {case.name}: {language_shape}/{source_shape}"
            raise AssertionError(msg)
    result = {
        "count": len(expected),
        "words": sum(words for _pk, words in expected) if expected else None,
        "ids_sha256": hashlib.sha256(json.dumps(expected).encode()).hexdigest(),
        "page_ids": expected_page,
        "word_summary_used": len(expected) <= SEARCH_SUMMARY_MAX_STRINGS,
    }
    (output / "correctness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def plan_nodes(node: dict) -> Iterator[dict]:
    yield node
    for child in node.get("Plans", []):
        yield from plan_nodes(child)


def explain(sql: str, params: tuple, timeout: int) -> dict[str, Any]:
    # A timeout rolls back only this measurement. All planner settings remain
    # at their server defaults, and the fixture is never changed by EXPLAIN.
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, true)", [str(timeout * 1000)]
        )
        cursor.execute(
            "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SETTINGS, FORMAT JSON) " + sql,
            params,
        )
        return cursor.fetchone()[0][0]


def metadata(profile: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        cursor.execute(
            """SELECT name, setting, unit FROM pg_settings WHERE name IN
               ('shared_buffers', 'work_mem', 'effective_cache_size', 'random_page_cost',
                'seq_page_cost', 'default_statistics_target', 'max_parallel_workers_per_gather')"""
        )
        server_settings = cursor.fetchall()
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'trans_unit'"
        )
        indexes = cursor.fetchall()
    return {
        "profile": profile,
        "fixture": asdict(PROFILES[profile]),
        "postgresql": version,
        "settings": server_settings,
        "indexes": indexes,
        "rows": {
            "languages": Language.objects.count(),
            "translations": Translation.objects.count(),
            "units": Unit.objects.count(),
        },
        "language_distribution": list(
            Translation.objects.values("language_code")
            .annotate(count=Count("pk"))
            .order_by("language_code")
        ),
        "cache": "one warm-up; no cache flushing; five timed runs by default",
    }


def benchmark(args: argparse.Namespace) -> None:
    output = Path(
        args.output
        or f"reports/search-benchmark-{args.profile}-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True, exist_ok=True)
    if (output / "results.jsonl").exists():
        msg = "Output already contains measurements; choose a new --output directory."
        raise ValueError(msg)
    connect_database(args.profile, prepare=args.prepare)
    if args.prepare:
        started = time.perf_counter()
        fixture = seed_fixture(PROFILES[args.profile])
        LOGGER.info("Loaded %s in %.1fs", fixture, time.perf_counter() - started)
    (output / "metadata.json").write_text(
        json.dumps(metadata(args.profile), indent=2) + "\n"
    )
    users = {
        False: User.objects.get(username="benchmark-restricted"),
        True: User.objects.get(username="benchmark-superuser"),
    }
    for user in users.values():
        # Warm permission caches once; all variants share the resulting ACLs.
        Unit.objects.filter_access(user)
    cases = [case for case in CASES if not args.cases or case.name in args.cases]
    records = []
    for scenario in args.source_scenarios:
        set_source_scenario(scenario)
        for case in cases:
            case_output = output / scenario / case.name
            case_output.mkdir(parents=True, exist_ok=True)
            LOGGER.info("Validating %s/%s", scenario, case.name)
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    [str(args.timeout * 1000)],
                )
                reference = correctness(users[case.superuser], case, case_output)
            for repetition in range(args.repetitions + 1):
                # Rotate the order rather than giving the same variant the
                # first position on every pass through the shared buffer cache.
                shift = repetition % len(VARIANTS)
                variants = VARIANTS[shift:] + VARIANTS[:shift]
                for language_shape, source_shape in variants:
                    label = f"{language_shape}-{source_shape}"
                    for operation in OPERATIONS:
                        started = time.perf_counter()
                        units = matching_units(
                            users[case.superuser],
                            case.language,
                            case.term,
                            language_shape,
                            source_shape,
                            language_operator=case.language_operator,
                        )
                        sql, params = operation_sql(units, operation)
                        lookup_ms = (time.perf_counter() - started) * 1000
                        record = {
                            "scenario": scenario,
                            "case": case.name,
                            "variant": label,
                            "operation": operation,
                            "repetition": repetition,
                            "warmup": repetition == 0,
                            "build_and_lookup_ms": lookup_ms,
                            "word_summary_used": reference["word_summary_used"],
                            "page_used": reference["count"] > 0,
                        }
                        try:
                            plan = explain(sql, params, args.timeout)
                            filename = f"{label}-{operation}-{repetition}.json"
                            (case_output / filename).write_text(
                                json.dumps(
                                    {"sql": sql, "params": params, "explain": plan},
                                    indent=2,
                                    default=str,
                                )
                                + "\n"
                            )
                            nodes = list(plan_nodes(plan["Plan"]))
                            record.update(
                                execution_ms=plan["Execution Time"],
                                planning_ms=plan["Planning Time"],
                                total_ms=lookup_ms
                                + plan["Execution Time"]
                                + plan["Planning Time"],
                                shared_hit_blocks=plan["Plan"].get(
                                    "Shared Hit Blocks", 0
                                ),
                                shared_read_blocks=plan["Plan"].get(
                                    "Shared Read Blocks", 0
                                ),
                                indexes=sorted(
                                    {
                                        node["Index Name"]
                                        for node in nodes
                                        if "Index Name" in node
                                    }
                                ),
                                scans=[
                                    {
                                        key: node[key]
                                        for key in (
                                            "Node Type",
                                            "Relation Name",
                                            "Alias",
                                            "Plan Rows",
                                            "Actual Rows",
                                            "Actual Loops",
                                            "Rows Removed by Filter",
                                            "Index Name",
                                        )
                                        if key in node
                                    }
                                    for node in nodes
                                    if "Relation Name" in node
                                ],
                            )
                        except DatabaseError as error:
                            record.update(
                                error=str(error),
                                sqlstate=getattr(error.__cause__, "sqlstate", None),
                                total_ms=(time.perf_counter() - started) * 1000,
                            )
                            (
                                case_output / f"{label}-{operation}-{repetition}.json"
                            ).write_text(
                                json.dumps(
                                    {"sql": sql, "params": params, "error": str(error)},
                                    indent=2,
                                    default=str,
                                )
                                + "\n"
                            )
                        with (output / "results.jsonl").open("a") as stream:
                            stream.write(json.dumps(record, default=str) + "\n")
                        records.append(record)
                LOGGER.info(
                    "%s/%s: pass %s/%s",
                    scenario,
                    case.name,
                    repetition,
                    args.repetitions,
                )
    write_summary(records, output)


def write_summary(records: list[dict], output: Path) -> None:
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for record in records:
        if not record["warmup"]:
            key = tuple(
                record[field] for field in ("scenario", "case", "variant", "operation")
            )
            groups.setdefault(key, []).append(record)
    lines = [
        "# Search benchmark measurements",
        "",
        (
            "Times include query construction and language lookup, server planning, and execution. "
            "Measurements use warm caches. Sum is diagnostic where the UI skips its word summary."
        ),
        "",
        "| Source scenario | Case | Variant | Operation | Median ms | Range ms | Errors |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for key, samples in sorted(groups.items()):
        times = [sample["total_ms"] for sample in samples if "error" not in sample]
        median = f"{statistics.median(times):.2f}" if times else "—"
        spread = f"{min(times):.2f}–{max(times):.2f}" if times else "—"
        lines.append(
            f"| {' | '.join(key)} | {median} | {spread} | {len(samples) - len(times)} |"
        )
    # The real view uses one result queryset. The paginator skips empty pages; the
    # word summary runs only for small results. Include construction/lookup
    # once, rather than charging the independently benchmarked lookup 3 times.
    requests: dict[tuple, dict[str, dict]] = {}
    for record in records:
        if record["warmup"]:
            continue
        key = tuple(
            record[field] for field in ("scenario", "case", "variant", "repetition")
        )
        requests.setdefault(key, {})[record["operation"]] = record
    request_groups: dict[tuple, list[float | None]] = {}
    for key, operations in requests.items():
        page_used = operations["count"].get("page_used")
        if page_used is None:
            # Also support reports from an earlier invocation of this tool.
            reference = output / key[0] / key[1] / "correctness.json"
            page_used = (
                not reference.exists() or json.loads(reference.read_text())["count"] > 0
            )
        needed = ["count", "page"] if page_used else ["count"]
        if operations["count"]["word_summary_used"]:
            needed.append("sum")
        if any("error" in operations[operation] for operation in needed):
            elapsed = None
        else:
            elapsed = operations["count"]["build_and_lookup_ms"] + sum(
                operations[operation]["execution_ms"]
                + operations[operation]["planning_ms"]
                for operation in needed
            )
        request_groups.setdefault(key[:3], []).append(elapsed)
    lines.extend(
        [
            "",
            "## Estimated search database cost",
            "",
            (
                "Includes count, nonempty page, conditional word summary, and one query build/lookup. "
                "Excludes rendering, result transfer, prefetches, and other request work."
            ),
            "",
            "| Source scenario | Case | Variant | Median ms | Range ms | Errors |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for key, request_samples in sorted(request_groups.items()):
        times = [value for value in request_samples if value is not None]
        median = f"{statistics.median(times):.2f}" if times else "—"
        spread = f"{min(times):.2f}–{max(times):.2f}" if times else "—"
        lines.append(
            f"| {' | '.join(key)} | {median} | {spread} | {len(request_samples) - len(times)} |"
        )
    (output / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    LOGGER.setLevel(logging.INFO)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile", choices=PROFILES, default="smoke")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="create/migrate and populate the dedicated database",
    )
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--timeout", type=int, default=120, help="statement timeout in seconds"
    )
    parser.add_argument("--cases", nargs="+", choices=[case.name for case in CASES])
    parser.add_argument(
        "--source-scenarios",
        nargs="+",
        choices=("no-parents", "mixed"),
        default=("no-parents", "mixed"),
    )
    parser.add_argument(
        "--output", help="directory for SQL, plans, measurements, and summary"
    )
    args = parser.parse_args()
    if args.repetitions < 1 or args.timeout < 1:
        parser.error("--repetitions and --timeout must be positive")
    benchmark(args)
