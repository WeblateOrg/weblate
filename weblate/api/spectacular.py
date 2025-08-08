# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Iterable, Set, Any
from urllib.parse import urlencode
from rest_framework.reverse import reverse
from urllib.parse import urlencode

from rest_framework.decorators import action
from drf_spectacular.plumbing import get_relative_url
from django.conf import settings
from django.urls import URLResolver, URLPattern, get_resolver
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

OAS_MAP = {"3.0": "3.0.3", "3.1": "3.1.0"}  # drf-spectacular supports both.  # noqa

LIGHT_EXCLUDE = {"users", "groups", "roles", "component-lists", "addons", "categories", "tasks" }  # your "admin-ish" bundle
SUCCESS_CODES = {"200", "201", "202", "204"}

def _first_seg(s: str) -> str:
    s = s.strip("^$").lstrip("/")
    return s.split("/", 1)[0] if s else ""

def _iter_leaf_patterns(resolver: URLResolver) -> Iterable[URLPattern]:
    # Walk into includes (important for: path("", include(router.urls)))
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _iter_leaf_patterns(p)
        else:
            yield p

def _filter_patterns(resolver: URLResolver,
                     include_tags: Set[str] | None,
                     exclude_tags: Set[str] | None) -> list[URLPattern | URLResolver]:
    leaves = list(_iter_leaf_patterns(resolver))
    out: list[URLPattern] = []
    for p in leaves:
        seg = _first_seg(str(p.pattern))
        if include_tags and seg not in include_tags:
            continue
        if exclude_tags and seg in exclude_tags:
            continue
        out.append(p)
    return out

def _strip_examples(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("example", None)
        node.pop("examples", None)
        for v in node.values(): _strip_examples(v)
    elif isinstance(node, list):
        for v in node: _strip_examples(v)

def _collect_used_security_schemes(schema: dict) -> set[str]:
    """Names of schemes referenced by top-level or per-operation `security`."""
    used: set[str] = set()

    def collect(sec_reqs):
        if isinstance(sec_reqs, list):
            for obj in sec_reqs:
                if isinstance(obj, dict):
                    used.update(obj.keys())

    collect(schema.get("security"))
    paths = schema.get("paths") or {}
    for _p, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for _m, op in methods.items():
            if isinstance(op, dict):
                collect(op.get("security"))

    return used


def _prune_unused_components(schema: dict) -> None:
    """
    Remove unreferenced entries under components by graph reachability.
    - Roots: paths (and webhooks). We also preserve securitySchemes used via
      security requirements (they are not $ref'd).
    """
    comps = schema.get("components")
    if not isinstance(comps, dict):
        return

    # --- special-case securitySchemes: keep referenced; if none referenced, keep all ---
    used_schemes = _collect_used_security_schemes(schema)
    sec_schemes = comps.get("securitySchemes")
    if isinstance(sec_schemes, dict):
        if used_schemes:
            for name in list(sec_schemes.keys()):
                if name not in used_schemes:
                    sec_schemes.pop(name, None)
        # If no schemes referenced, KEEP them all (don’t erase auth info)

    # Standard reachability for the rest (schemas, parameters, responses, headers, etc.)
    def get_component(section: str, name: str):
        sec = comps.get(section)
        if isinstance(sec, dict):
            return sec.get(name)
        return None

    reachable: set[str] = set()
    from collections import deque
    q = deque()

    # roots
    paths = schema.get("paths") or {}
    q.append(paths)
    if "webhooks" in schema:
        q.append(schema["webhooks"])

    def enqueue_component(key: str):
        if key in reachable:
            return
        reachable.add(key)
        try:
            section, name = key.split("/", 1)
        except ValueError:
            return
        node = get_component(section, name)
        if node is not None:
            q.append(node)

    def ref_to_key(ref: str) -> str | None:
        p = "#/components/"
        if isinstance(ref, str) and ref.startswith(p):
            return ref[len(p):]
        return None

    while q:
        node = q.popleft()
        if isinstance(node, dict):
            # $ref
            if "$ref" in node:
                key = ref_to_key(node["$ref"])
                if key:
                    enqueue_component(key)
            # discriminator.mapping
            disc = node.get("discriminator")
            if isinstance(disc, dict):
                mapping = disc.get("mapping")
                if isinstance(mapping, dict):
                    for v in mapping.values():
                        key = ref_to_key(v)
                        if key:
                            enqueue_component(key)
            # descend
            for v in node.values():
                q.append(v)
        elif isinstance(node, list):
            for v in node:
                q.append(v)

    # prune everything EXCEPT securitySchemes (already handled)
    for section, items in list(comps.items()):
        if section == "securitySchemes":
            continue
        if not isinstance(items, dict):
            continue
        for name in list(items.keys()):
            if f"{section}/{name}" not in reachable:
                items.pop(name, None)


def _prune_unused_tags(schema: dict) -> None:
    paths = schema.get("paths") or {}
    used = set()
    for _p, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for _m, op in methods.items():
            if not isinstance(op, dict):
                continue
            for t in op.get("tags") or []:
                used.add(t)

    # If operations were not tagged, fall back to first path segment
    if not used:
        for p in paths.keys():
            seg = p.lstrip("/").split("/", 1)[0]
            if seg:
                used.add(seg)

    if "tags" in schema and isinstance(schema["tags"], list):
        schema["tags"] = [t for t in schema["tags"] if t.get("name") in used]


class DynamicSchemaView(SpectacularAPIView):
    """
    /api/schema/                                      # 3.1 (default)
    /api/schema/?oav=3.0                              # 3.0
    /api/schema/?oav=3.1                              # 3.1
    /api/schema/?oav=3.0&light=true                   # light preset
    /api/schema/?oav=3.1&tags=projects,components     # include only
    /api/schema/?oav=3.0&exclude=users,groups,addons  # exclude tags
    /api/schema/?errors=false&examples=false          # doc-only trimming
    """

    exclude_from_schema = False
    oa_request_version = "3.1"

    @extend_schema(
        operation_id="getOpenAPISchema",
        tags=["root"],
        summary="Download the OpenAPI Description",
        description="Returns the OpenAPI document. Supports per-request filtering and OAS version selection.",
        parameters=[
            OpenApiParameter(name="oav", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.STR, enum=["3.0", "3.1"], default="3.1",
                             description="OpenAPI version to generate."),
            OpenApiParameter(name="light", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.BOOL, default=False,
                             description="Exclude predefined admin-ish tags."),
            OpenApiParameter(name="tags", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.STR,
                             description="Comma-separated list of tags to include (first path segments)."),
            OpenApiParameter(name="exclude", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.STR,
                             description="Comma-separated list of tags to exclude."),
            OpenApiParameter(name="errors", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.BOOL, default=True,
                             description="Include non-2xx error responses in operations."),
            OpenApiParameter(name="examples", location=OpenApiParameter.QUERY,
                             type=OpenApiTypes.BOOL, default=True,
                             description="Include example/example(s) objects."),
        ],
        responses={
            200: OpenApiResponse(
                description="OpenAPI document (filtered)",
                response=OpenApiTypes.OBJECT,  # the JSON/YAML document
            ),
        },
    )
    @action(
        detail=True,
        methods=["get"]
    )
    def get(self, request, *args, **kwargs):
        # --- params ---
        ver = request.query_params.get("oav", "3.1")
        oas = OAS_MAP.get(ver, OAS_MAP["3.1"])
        title_suffix = ""

        if oas.startswith("3.0"):
            oa_request_version = "3.0"
        else:
            oa_request_version = "3.1"

        drop_errors = request.query_params.get("errors", "true").lower() == "false"
        drop_examples = request.query_params.get("examples", "true").lower() == "false"

        include_tags = ({t.strip() for t in request.query_params.get("tags", "").split(",") if t.strip()}
                        or None)

        exclude_tags: Set[str] = {t.strip() for t in request.query_params.get("exclude", "").split(",") if t.strip()}

        if (drop_errors or drop_examples or include_tags or exclude_tags):
            title_suffix = " Subset"

        if request.query_params.get("light", "false").lower() == "true":
            exclude_tags = LIGHT_EXCLUDE
            include_tags = None
            drop_errors = True
            drop_examples = True
            title_suffix = " Light"

        # --- lock to your API urlconf (already set globally) ---
        # self.urlconf = settings.SPECTACULAR_SETTINGS.get("SERVE_URLCONF", settings.ROOT_URLCONF)

        # --- PRE-GENERATION filtering (walk into the router include) ---
        resolver = get_resolver(self.urlconf)
        self.patterns = _filter_patterns(resolver, include_tags, exclude_tags or None)

        # --- OAS version per request ---
        self.custom_settings = {**(getattr(self, "custom_settings", {}) or {}), "OAS_VERSION": oas}

        title = settings.SPECTACULAR_SETTINGS.get("TITLE", "REST API");
                                                  
        self.custom_settings = {**(getattr(self, "custom_settings", {}) or {}), "TITLE": f"{title}{title_suffix} (OAS {oa_request_version})"}

        # generate
        resp = super().get(request, *args, **kwargs)
        schema = resp.data

        # --- doc-only edits ---
        if drop_examples:
            _strip_examples(schema)

        if drop_errors:
            paths = schema.get("paths") or {}
            for _, methods in paths.items():
                if not isinstance(methods, dict): continue
                for _, op in methods.items():
                    if not isinstance(op, dict): continue
                    rs = op.get("responses")
                    if isinstance(rs, dict):
                        for code in list(rs.keys()):
                            if code not in SUCCESS_CODES and code != "default":
                                rs.pop(code, None)

        if oas.startswith("3.0"):
            schema.pop("webhooks", None)

        _prune_unused_tags(schema)
        _prune_unused_components(schema)
        resp.data = schema
        return resp


class DynamicRedocView(SpectacularRedocView):
    def _get_schema_url(self, request):
        base = get_relative_url(reverse(self.url_name, request=request))
        qs = urlencode(list(request.GET.lists()), doseq=True, safe="./?&,")
        return f"{base}?{qs}" if qs else base

class DynamicSwaggerView(SpectacularSwaggerSplitView):
    def _get_schema_url(self, request):
        base = get_relative_url(reverse(self.url_name, request=request))
        qs = urlencode(list(request.GET.lists()), doseq=True, safe="./?&,")
        return f"{base}?{qs}" if qs else base

