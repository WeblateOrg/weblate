# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cheap, application-aware anonymous proof of work, independent of authentication."""

from __future__ import annotations

import json
import logging
import random
import re
import time
from ipaddress import IPv4Network, IPv6Network, ip_address
from pathlib import Path
from typing import TYPE_CHECKING

from altcha import Payload, create_challenge, verify_solution
from django.conf import settings
from django.contrib import auth
from django.core import signing
from django.core.cache import caches
from django.core.cache.backends.memcached import BaseMemcachedCache
from django.core.cache.backends.redis import RedisCache
from django.core.exceptions import ImproperlyConfigured, RequestDataTooBig
from django.http import HttpResponse, HttpResponseBase, JsonResponse

# Django has no public validator for an alternate CSRF cookie.
from django.middleware import csrf
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.template.loader import get_template
from django.urls import Resolver404, resolve
from django.utils.crypto import salted_hmac
from django.utils.decorators import decorator_from_middleware
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.module_loading import import_string
from django.utils.translation import (
    get_language_bidi,
    get_language_from_request,
    gettext,
    gettext_noop,
    override,
)
from django_redis.cache import RedisCache as DjangoRedisCache

from weblate.trans.views.widgets import WidgetRedirectView
from weblate.utils.crawl_policy import crawl_allowed, deployment_prefix
from weblate.utils.crawlers import (
    CRAWLERS,
    MAX_DOWNLOAD,
    SNAPSHOT,
    public_network,
)
from weblate.utils.urls import GitPathConverter

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest

# These tips must stay independent of database and session state.
FEATURE_TIPS = (
    gettext_noop("Press ? in the translation editor to discover keyboard shortcuts."),
    gettext_noop(
        "Add secondary languages in your preferences to see translations you already understand alongside the source."
    ),
    gettext_noop(
        "Customize your special characters in your profile to keep frequently used characters within reach."
    ),
    gettext_noop(
        "Use the visual keyboard above the translation field to insert special characters."
    ),
    gettext_noop(
        "Save searches you use often so you can return to them from the search filters."
    ),
    gettext_noop(
        "Combine search conditions with AND, OR, and NOT to find exactly the strings you need."
    ),
    gettext_noop(
        "Search with regular expressions when a simple word search is not enough."
    ),
    gettext_noop("Use labels to organize strings and find related translation work."),
    gettext_noop(
        "Check a string’s screenshots to see where the text appears in the application."
    ),
    gettext_noop(
        "Link an existing screenshot to a string to give translators more context."
    ),
    gettext_noop(
        "Check nearby strings for context before translating a short or ambiguous message."
    ),
    gettext_noop("Explore a string’s history to see how its translation has changed."),
    gettext_noop(
        "Leave a comment on a source string to ask for context that can help every language."
    ),
    gettext_noop(
        "Suggest a translation when you want others to review your wording before it is accepted."
    ),
    gettext_noop("You can edit a translation suggestion before accepting it."),
    gettext_noop(
        "Add terms to a project glossary to help translators use consistent wording."
    ),
    gettext_noop(
        "Glossaries can mark terms as forbidden to help translators avoid unwanted wording."
    ),
    gettext_noop("Glossaries can mark names and other terms as untranslatable."),
    gettext_noop(
        "Watch projects you care about and choose which translation events notify you."
    ),
    gettext_noop(
        "Choose notification digests to receive translation updates together instead of one email at a time."
    ),
)

COOKIE = "weblate_pow"
VERIFY_PATH = "/-/pow/verify/"
CHECK_PATH = "/-/pow/check/"
LOGGER = logging.getLogger("weblate.bot_protection")
OUTCOMES = (
    "issued",
    "pow_required",
    "success",
    "expired_challenge",
    "invalid_solution",
    "replayed_challenge",
    "csrf_failed",
    "verification_unavailable",
)


class ExpiredChallengeError(ValueError):
    """The submitted challenge has expired."""


def record_outcome(reason: str, status: int) -> None:
    """Record bounded operational data without affecting verification."""
    LOGGER.info(
        "PoW verification: %s",
        reason,
        extra={
            "event": "pow_verification",
            "reason": reason,
            "status": status,
            "count": 1,
        },
    )
    record_counter(reason)


def record_counter(reason: str) -> None:
    """Increment a best-effort hourly counter."""
    try:
        backend = caches[option("CACHE_ALIAS", "default")]
        key = f"pow:stats:hour:{int(time.time()) // 3600}:{reason}"
        if not backend.add(key, 1, timeout=26 * 3600):
            backend.incr(key)
    except Exception:
        LOGGER.warning(
            "PoW counter unavailable",
            extra={"event": "pow_counter_unavailable", "reason": reason},
        )


def verification_stats() -> dict[str, dict[str, int]] | None:
    """Return current-hour and previous 24 completed hours, or None on failure."""
    hour = int(time.time()) // 3600
    keys = {
        f"pow:stats:hour:{bucket}:{reason}": (
            "current_hour" if bucket == hour else "previous_24_hours",
            reason,
        )
        for bucket in range(hour - 24, hour + 1)
        for reason in OUTCOMES
    }
    try:
        values = caches[option("CACHE_ALIAS", "default")].get_many(keys)
    except Exception:
        return None
    totals = {
        window: dict.fromkeys(OUTCOMES, 0)
        for window in ("current_hour", "previous_24_hours")
    }
    for key, value in values.items():
        window, reason = keys[key]
        totals[window][reason] += value
    return totals


def verification_error(reason: str, status: int) -> HttpResponse:
    record_outcome(reason, status)
    return headers(JsonResponse({"error": reason}, status=status))


def check_clearance(request: HttpRequest) -> HttpResponse:
    """Check only the cookie, without invoking destination views."""
    if not option("ENABLED", False):
        return HttpResponse(status=404)
    if request.method not in {"GET", "HEAD"}:
        response = headers(HttpResponse(status=405))
        response["Allow"] = "GET, HEAD"
        return response
    return headers(HttpResponse(status=204 if clearance(request) else 403))


# Prefixes end in '/' so similarly named application routes are not exempt.
EXEMPT = (
    "/static/",
    # Authentication flows and login redirects must work without clearance.
    "/accounts/",
    "/hooks/",
    "/oidc/",
    "/widget/",
    "/exports/rss/",
    "/changes/rss/",
    "/.well-known/",
    "/machinery/etranslation/callback/",
)
EXACT = {
    "/healthz/",
    "/robots.txt",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/css/custom.css",
    "/site.webmanifest",
    "/browserconfig.xml",
    "/security.txt",
    "/exports/og.png",
    *(
        f"/{name}-{size}x{size}.png"
        for name in ("android-chrome", "favicon")
        for size in (192, 512)
    ),
    "/manage/discovery/callback/",
    "/js/i18n/",
}
GIT_PROTOCOL_PATH = re.compile(rf"/(?:git|projects)/.+/{GitPathConverter.regex}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def option[T](name: str, default: T) -> T:
    return getattr(settings, f"BOT_PROTECTION_{name}", default)


def prefix() -> str:
    return deployment_prefix()


def binding(request: HttpRequest) -> str:
    # Never consume forwarding headers here: ProxyMiddleware is the trust boundary.
    address = str(ip_address(request.META["REMOTE_ADDR"]))
    return salted_hmac("weblate.pow.ip", address).hexdigest()


def secret(request: HttpRequest) -> str:
    return salted_hmac(
        "weblate.pow.challenge", request.get_host() + prefix()
    ).hexdigest()


def safe_target(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 2048
        and value.startswith(prefix() + "/")
        and not value.startswith("//")
        and "\\" not in value
        and not any(ord(char) < 32 for char in value)
        and url_has_allowed_host_and_scheme(value, allowed_hosts=set())
    )


def clearance(request: HttpRequest) -> bool:
    value = request.COOKIES.get(COOKIE, "")
    if len(value) > 1024:
        return False
    try:
        data = signing.loads(
            value, salt="weblate.pow.clearance", max_age=option("COOKIE_AGE", 3600)
        )
        return data == {
            "ip": binding(request),
            "host": request.get_host(),
            "prefix": prefix(),
            "v": 1,
        }
    except (signing.BadSignature, ValueError, KeyError):
        return False


def headers(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    response["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


class ProofCSRF(CsrfViewMiddleware):
    """Standard Django CSRF validation with a separate cookie, avoiding sessions."""

    def _reject(self, request: HttpRequest, reason: str) -> HttpResponse:
        # The normal failure template loads application context processors.
        return verification_error("csrf_failed", 403)

    def _get_secret(self, request: HttpRequest) -> str | None:
        value = request.COOKIES.get("weblate_pow_csrf")
        if value is not None:
            vars(csrf)["_check_token_format"](value)
        return value

    def _set_csrf_cookie(self, request: HttpRequest, response: HttpResponse) -> None:
        response.set_cookie(
            "weblate_pow_csrf",
            request.META["CSRF_COOKIE"],
            secure=True,
            httponly=True,
            samesite="Lax",
            path=prefix() + "/",
            max_age=option("CHALLENGE_AGE", 300),
        )


proof_csrf = decorator_from_middleware(ProofCSRF)


@proof_csrf
def challenge_page(request: HttpRequest) -> HttpResponse:
    target = request.get_full_path()
    if not safe_target(target):
        return headers(JsonResponse({"error": "invalid_target"}, status=400))
    expires_at = int(time.time()) + option("CHALLENGE_AGE", 300)
    challenge = create_challenge(
        "SHA-256",
        1,
        key_prefix="0" * option("DIFFICULTY", 4),
        expires_at=expires_at,
        data={"ip": binding(request), "target": target, "v": 1},
        hmac_secret=secret(request),
    )
    # No request context processors: these can query models and load a session.
    language = get_language_from_request(request)
    with override(language):
        content = get_template("bot-challenge.html").render(
            {
                "challenge": challenge.to_dict(),
                "challenge_timeout": max(0, int((expires_at - time.time()) * 1000)),
                "verify_url": prefix() + VERIFY_PATH,
                "check_url": prefix() + CHECK_PATH,
                "csrf_token": get_token(request),
                "language": language,
                "language_bidi": get_language_bidi(),
                # Randomness only chooses display text, not proof material.
                "feature_tip": gettext(random.choice(FEATURE_TIPS)),  # ruff: ignore[suspicious-non-cryptographic-random-usage]
                "home_url": prefix() + "/",
                "login_url": prefix() + "/accounts/login/",
            }
        )
    record_counter("issued")
    return headers(HttpResponse(content, status=403))


# The flat checks make the accepted protocol explicit before library dispatch.
def validated_payload(request: HttpRequest) -> dict:
    """Bound the input before invoking the fixed-cost ALTCHA verifier."""
    if int(request.headers.get("content-length") or 0) > 8192:
        raise ValueError
    # Bounded read also covers absent/incorrect Content-Length.
    body = request.read(8193)
    if len(body) > 8192:
        raise ValueError
    raw = json.loads(body)
    p = raw["challenge"]["parameters"]
    s = raw["solution"]
    if (
        p["algorithm"] != "SHA-256"
        or not isinstance(p["cost"], int)
        or isinstance(p["cost"], bool)
        or p["cost"] != 1
        or p["keyLength"] != 32
        or p["keyPrefix"] != "0" * option("DIFFICULTY", 4)
        or set(p)
        != {
            "algorithm",
            "cost",
            "keyLength",
            "keyPrefix",
            "nonce",
            "salt",
            "expiresAt",
            "data",
        }
    ):
        raise ValueError
    if (
        not HEX32.fullmatch(p["nonce"])
        or not HEX32.fullmatch(p["salt"])
        or not HEX64.fullmatch(raw["challenge"]["signature"])
        or not HEX64.fullmatch(s["derivedKey"])
    ):
        raise ValueError
    if (
        not isinstance(s["counter"], int)
        or isinstance(s["counter"], bool)
        or not 0 <= s["counter"] <= 0xFFFFFFFF
        or not isinstance(p["expiresAt"], int)
        or isinstance(p["expiresAt"], bool)
        or p["expiresAt"] > time.time() + option("CHALLENGE_AGE", 300)
        or p["data"] != {"ip": binding(request), "target": p["data"]["target"], "v": 1}
        or not safe_target(p["data"]["target"])
    ):
        raise ValueError
    if p["expiresAt"] <= time.time():
        raise ExpiredChallengeError
    payload = Payload.from_dict(raw)
    if not verify_solution(payload, secret(request)).verified:
        raise ValueError
    return raw


@proof_csrf
def verify(request: HttpRequest) -> HttpResponse:
    if not option("ENABLED", False):
        return HttpResponse(status=404)
    if request.method != "POST":
        return headers(JsonResponse({"error": "method_not_allowed"}, status=405))
    try:
        raw = validated_payload(request)
        p = raw["challenge"]["parameters"]
    except ExpiredChallengeError:
        return verification_error("expired_challenge", 400)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        RequestDataTooBig,
    ):
        return verification_error("invalid_solution", 400)
    try:
        consumed = caches[option("CACHE_ALIAS", "default")].add(
            "pow:" + raw["challenge"]["signature"],
            True,
            timeout=max(1, int(p["expiresAt"] - time.time()) + 1),
        )
    except Exception:
        return verification_error("verification_unavailable", 503)
    if not consumed:
        return verification_error("replayed_challenge", 409)
    record_outcome("success", 200)
    response = JsonResponse({"redirect": p["data"]["target"]})
    response.set_cookie(
        COOKIE,
        signing.dumps(
            {
                "ip": binding(request),
                "host": request.get_host(),
                "prefix": prefix(),
                "v": 1,
            },
            salt="weblate.pow.clearance",
        ),
        max_age=option("COOKIE_AGE", 3600),
        secure=True,
        httponly=True,
        samesite="Lax",
        path=prefix() + "/",
    )
    return headers(response)


class CrawlerRanges:
    """Process-local snapshot loaded once before serving requests."""

    def __init__(self) -> None:
        self.ranges: dict[str, list[IPv4Network | IPv6Network]] = {}
        self.rules = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in {
                **{name: crawler.agent for name, crawler in CRAWLERS.items()},
                **option("CRAWLER_RULES", dict[str, str]()),
            }.items()
        }

        self.load()

    def load(self) -> None:
        self.ranges = {
            name: [public_network(value) for value in crawler.ranges]
            for name, crawler in CRAWLERS.items()
            if crawler.format == "bundled"
        }
        filename = (
            Path(option("CRAWLER_FILE", "")) if option("CRAWLER_FILE", "") else SNAPSHOT
        )
        try:
            with filename.open("rb") as source:
                raw = source.read(MAX_DOWNLOAD + 1)
            if len(raw) > MAX_DOWNLOAD:
                return
            data = json.loads(raw)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RecursionError,
        ):
            return
        if not isinstance(data, dict) or not isinstance(data.get("ranges"), dict):
            return
        for name, values in data["ranges"].items():
            try:
                self.ranges[name] = [public_network(value) for value in values]
            except (ValueError, KeyError, TypeError):
                continue

    def verified(self, request: HttpRequest) -> bool:
        ua = request.headers.get("user-agent", "")[:1024]
        try:
            address = ip_address(request.META["REMOTE_ADDR"])
        except (KeyError, ValueError):
            return False
        return any(
            pattern.search(ua)
            and any(address in network for network in self.ranges.get(name, ()))
            for name, pattern in self.rules.items()
        )


def is_git_protocol(request: HttpRequest, path: str) -> bool:
    """Let exporter requests and clone redirects reach their own authentication."""
    if (
        "weblate.gitexport" not in settings.INSTALLED_APPS
        or not GIT_PROTOCOL_PATH.fullmatch(path)
    ):
        return False
    try:
        match = resolve(request.path_info, getattr(request, "urlconf", None))
    except Resolver404:
        return False
    # Resolve only candidate transport URLs: project routes can otherwise overlap
    # with clone aliases. Browser-facing redirects to project pages stay protected.
    return (
        match.url_name == "git-export"
        or getattr(match.func, "view_initkwargs", {}).get("pattern_name")
        == "git-export"
    )


def is_legacy_widget(request: HttpRequest, path: str) -> bool:
    if not path.startswith("/widgets/"):
        return False
    try:
        match = resolve(request.path_info, getattr(request, "urlconf", None))
    except Resolver404:
        return False
    return getattr(match.func, "view_class", None) is WidgetRedirectView


def accepts_html(request: HttpRequest) -> bool:
    """Require an explicit positive HTML preference, not a wildcard Accept."""
    return any(
        media.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}
        and not re.search(r";\s*q=0(?:\.0*)?\s*(?:;|$)", media.lower())
        for media in request.headers.get("accept", "").split(",")
    )


class BotProtectionMiddleware(MiddlewareMixin):
    """Early gate; real Django authentication always takes precedence over bot rules."""

    def __init__(self, get_response: Callable) -> None:
        super().__init__(get_response)
        self.enabled = option("ENABLED", False)
        if not self.enabled:
            return
        try:
            self.exempt_agents = tuple(
                re.compile(pattern, re.IGNORECASE)
                for pattern in option("EXEMPT_AGENTS", list[str]())
            )
        except re.error as error:
            msg = "Invalid BOT_PROTECTION_EXEMPT_AGENTS regular expression"
            raise ImproperlyConfigured(msg) from error
        self.crawlers = CrawlerRanges()
        for name, default, maximum in (
            ("DIFFICULTY", 4, 6),
            ("CHALLENGE_AGE", 300, 3600),
            ("COOKIE_AGE", 3600, 86400),
        ):
            value = option(name, default)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 1 <= value <= maximum
            ):
                msg = f"Invalid BOT_PROTECTION_{name}"
                raise ImproperlyConfigured(msg)
        backend = settings.CACHES[option("CACHE_ALIAS", "default")]["BACKEND"]
        if not issubclass(
            import_string(str(backend)),
            (RedisCache, DjangoRedisCache, BaseMemcachedCache),
        ):
            msg = "Bot protection requires a shared Redis or Memcached cache"
            raise ImproperlyConfigured(msg)
        if option("UNWANTED_ACTION", "challenge") not in {"challenge", "deny"}:
            msg = "Invalid BOT_PROTECTION_UNWANTED_ACTION"
            raise ImproperlyConfigured(msg)
        for path in option("EXEMPT_PATHS", list[str]()):
            if not path.startswith("/") or "?" in path or "\\" in path:
                msg = "Invalid BOT_PROTECTION_EXEMPT_PATHS"
                raise ImproperlyConfigured(msg)
        for pattern in [
            *option("CRAWLER_RULES", dict[str, str]()).values(),
            *option("UNWANTED_AGENTS", list[str]()),
        ]:
            re.compile(pattern)

    def classify(self, request: HttpRequest) -> str:
        """Policy seam for future behavioral signals; never changes authentication."""
        if (
            request.method in {"GET", "HEAD"}
            and crawl_allowed(request.path_info.removeprefix(prefix()))
            and self.crawlers.verified(request)
        ):
            return "allow"
        if option("UNWANTED_ACTION", "challenge") == "deny" and any(
            re.search(
                pattern, request.headers.get("user-agent", "")[:1024], re.IGNORECASE
            )
            for pattern in option("UNWANTED_AGENTS", list[str]())
        ):
            return "deny"
        return "challenge"

    def process_request(self, request: HttpRequest) -> HttpResponseBase | None:
        if not self.enabled:
            return None
        path = request.path_info.removeprefix(prefix())
        if path == CHECK_PATH:
            return check_clearance(request)
        if path == VERIFY_PATH:
            return verify(request)
        exempt_path = (
            path in EXACT
            or is_git_protocol(request, path)
            or is_legacy_widget(request, path)
            or path.startswith(EXEMPT)
            or any(
                path == item or (item.endswith("/") and path.startswith(item))
                for item in option("EXEMPT_PATHS", list[str]())
            )
            or (path.startswith("/api/") and not accepts_html(request))
        )
        if (
            exempt_path
            or any(
                pattern.search(request.headers.get("user-agent", "")[:1024])
                for pattern in self.exempt_agents
            )
            or clearance(request)
        ):
            return None
        if settings.SESSION_COOKIE_NAME in request.COOKIES:
            user = auth.get_user(request)
            request.__dict__["pow_authenticated_user"] = user
            if user.is_authenticated:
                return None
        decision = self.classify(request)
        if decision == "allow":
            return None
        denied = decision == "deny"
        if not denied and request.method == "GET" and accepts_html(request):
            return challenge_page(request)
        if not denied:
            record_counter("pow_required")
        response = JsonResponse(
            {
                "error": "bot_denied" if denied else "pow_required",
                "verification_url": prefix() + VERIFY_PATH,
            },
            status=403,
        )
        if request.method == "HEAD":
            response.content = b""
        return headers(response)
