# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from copy import copy
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, QueryDict
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.settings import oauth2_settings
from oauth2_provider.views import (
    AuthorizationView,
    ConnectDiscoveryInfoView,
)
from oauthlib.openid.connect.core.exceptions import LoginRequired

from weblate.accounts.oidc import (
    OIDC_ATTEMPT_PARAMETER,
    OIDC_ATTEMPTS_SESSION_KEY,
    InvalidOidcAttempt,
    create_oidc_attempt,
    finish_oidc_attempt,
    get_oidc_attempt,
    get_oidc_attempts,
    oidc_login_error,
)
from weblate.oidc.forms import AuthorizationForm
from weblate.oidc.settings import AUTH_TIME_SESSION_KEY
from weblate.oidc.validator import can_authenticate, requires_authentication

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse
    from oauth2_provider.models import Application

    from weblate.auth.models import AuthenticatedHttpRequest


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_not_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class WeblateAuthorizationView(AuthorizationView):
    form_class = AuthorizationForm

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        try:
            return self.dispatch_authorization(request, *args, **kwargs)
        except InvalidOidcAttempt:
            return oidc_login_error()

    def dispatch_authorization(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        self.oauth2_data: dict[str, Any] = {}
        if request.user.is_authenticated and not can_authenticate(request.user):
            raise PermissionDenied
        if request.method == "POST" and (
            "weblate_consent" not in request.POST or not request.user.is_authenticated
        ):
            # An initial protocol POST carries no Weblate CSRF token. It can
            # start authorization, but must never approve or deny consent.
            params = request.POST.copy()
            params.pop("allow", None)
            params.pop("csrfmiddlewaretoken", None)
            params.pop(OIDC_ATTEMPT_PARAMETER, None)
            if "weblate_consent" in params:
                params.pop("weblate_consent")
                for field in ("max_age", "prompt", "claims", "resource", "nonce"):
                    if not params.get(field):
                        params.pop(field, None)
                resource = params.get("resource")
                if resource:
                    params.setlist("resource", resource.split())
            # Validate in the GET flow before any login intent is recorded.
            target = urlsplit(request.get_full_path())._replace(
                query=params.urlencode()
            )
            return HttpResponseRedirect(target.geturl(), status=303)
        if request.method in {"GET", "HEAD"}:
            # LoginRequiredMixin otherwise redirects before validating the request.
            # Invalid probes must not change the user's session or its expiry.
            try:
                _scopes, credentials = self.validate_authorization_request(request)
            except OAuthToolkitError as error:
                return self.error_response(error, application=None)

            selected = get_oidc_attempt(request)
            if (
                request.user.is_authenticated
                and selected is not None
                and selected[1]["require_fresh"]
                and selected[1]["login_completed"]
                and request.session.get(AUTH_TIME_SESSION_KEY) is None
            ):
                return self.error_response(
                    OAuthToolkitError(
                        LoginRequired(
                            description="Fresh authentication could not be established.",
                            state=credentials.get("state"),
                        ),
                        redirect_uri=credentials["redirect_uri"],
                    ),
                    application=None,
                )
            max_age = int(request.GET["max_age"]) if "max_age" in request.GET else None
            if requires_authentication(request, max_age):
                return self.handle_prompt_login()
        return super().dispatch(request, *args, **kwargs)

    @method_decorator(csrf_protect)
    def post(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        # Only marked consent submissions reach this method. Protect both the
        # approval and denial actions after exempting initial protocol POSTs.
        return super().post(request, *args, **kwargs)

    def error_response(
        self,
        error: OAuthToolkitError,
        application: Application | None,
        **kwargs: object,
    ) -> HttpResponse:
        finish_oidc_attempt(self.request)
        response = super().error_response(error, application, **kwargs)
        if (
            "Location" in response
            and oauth2_settings.COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS
        ):
            # The toolkit only adds iss to successful authorization responses.
            # Include it on error redirects too, replacing any callback value.
            target = urlsplit(response["Location"])
            params = QueryDict(target.query, mutable=True)
            params["iss"] = oauth2_settings.oauth2_authorization_server_issuer(
                self.request
            )
            response["Location"] = target._replace(query=params.urlencode()).geturl()
        return response

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        # The toolkit serializes absent claims as JSON null in the consent form.
        if initial.get("claims") in {"null", '""'}:
            initial["claims"] = ""
        initial["max_age"] = self.request.GET.get("max_age")
        selected = get_oidc_attempt(self.request)
        initial[OIDC_ATTEMPT_PARAMETER] = selected[0] if selected else ""
        initial["prompt"] = "login" if selected and selected[1]["require_fresh"] else ""
        return initial

    def form_valid(self, form: AuthorizationForm) -> HttpResponse:
        params = QueryDict(mutable=True)
        params.update(
            {
                name: str(value)
                for name, value in form.cleaned_data.items()
                if name not in {"allow", "weblate_consent"}
                and value is not None
                and str(value)
            }
        )
        resource = form.cleaned_data.get("resource")
        if resource:
            params.setlist("resource", resource.split())
        # Revalidate protocol parameters before binding consent to an attempt or
        # changing authentication state. No submitted approval survives a login.
        request = copy(self.request)
        request.method = "GET"
        request.GET = params
        request.META = {**self.request.META, "QUERY_STRING": params.urlencode()}
        request.POST = QueryDict()
        try:
            self.validate_authorization_request(request)
        except OAuthToolkitError as error:
            return self.error_response(error, application=None)
        if form.cleaned_data["allow"] and requires_authentication(
            self.request, form.cleaned_data["max_age"]
        ):
            return self.handle_prompt_login(params)
        get_oidc_attempt(self.request)
        return super().form_valid(form)

    def create_authorization_response(
        self,
        request: AuthenticatedHttpRequest,
        scopes: str,
        credentials: dict[str, Any],
        allow: bool,
    ) -> tuple[str, dict[str, str], str, int]:
        credentials["weblate_auth_time"] = request.session[AUTH_TIME_SESSION_KEY]
        result = super().create_authorization_response(
            request, scopes, credentials, allow
        )
        finish_oidc_attempt(request)
        return result

    def handle_prompt_login(self, params: QueryDict | None = None) -> HttpResponse:
        params = (self.request.GET if params is None else params).copy()
        selected = get_oidc_attempt(self.request)
        require_fresh = (
            bool(selected and selected[1]["require_fresh"])
            or "max_age" in params
            or "login" in params.get("prompt", "").split()
        )
        # Weblate's login view redirects authenticated users to their profile.
        # End the existing session before asking for fresh authentication.
        if self.request.user.is_authenticated:
            attempts = get_oidc_attempts(self.request).copy()
            logout(self.request)
            self.request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
        # Social-auth callbacks do not carry the authorization URL in `next`.
        self.request.session["oidc_only"] = True
        # max_age=0 is equivalent to prompt=login and must be consumed once.
        # Positive limits still apply if the user spends time on the consent page.
        max_age = params.get("max_age")
        if max_age is not None and int(max_age) == 0:
            params.pop("max_age")
        prompts = [
            value for value in params.get("prompt", "").split() if value != "login"
        ]
        params.pop("prompt", None)
        if prompts:
            params["prompt"] = " ".join(prompts)
        params.pop(OIDC_ATTEMPT_PARAMETER, None)
        target = urlsplit(self.request.get_full_path())._replace(
            query=params.urlencode()
        )
        if selected is None:
            identifier = create_oidc_attempt(
                self.request, target.geturl(), require_fresh=require_fresh
            )
        else:
            identifier, attempt = selected
            attempts = get_oidc_attempts(self.request).copy()
            attempts[identifier] = {
                **attempt,
                "target": target.geturl(),
                "require_fresh": require_fresh,
                "login_completed": False,
            }
            self.request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
        params[OIDC_ATTEMPT_PARAMETER] = identifier
        target = target._replace(query=params.urlencode())
        return redirect_to_login(
            target.geturl(), self.get_login_url(), self.get_redirect_field_name()
        )


class WeblateDiscoveryView(ConnectDiscoveryInfoView):
    def get(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        response = super().get(request, *args, **kwargs)
        # Only RS256 code clients are accepted by our validator.
        data = json.loads(response.content)
        data["id_token_signing_alg_values_supported"] = ["RS256"]
        data["grant_types_supported"] = ["authorization_code", "refresh_token"]
        response.content = json.dumps(data)
        return response
