# -*- coding: utf-8 -*-
from social_core.backends.open_id_connect import OpenIdConnectAuth
from social_core.utils import cache

from weblate.logger import LOGGER


class VendastaOpenIdConnect(OpenIdConnectAuth):
    """Vendasta OpenID authentication Backend."""

    name = "vendasta"
    ACCESS_TOKEN_METHOD = "POST"
    EXTRA_DATA = [("sub", "id"), "namespace", "roles"]
    USERNAME_KEY = "sub"

    @cache(ttl=86400)
    def oidc_config(self):
        oidc_endpoint = self.setting(
            "OIDC_ENDPOINT", "http://iam-prod.vendasta-internal.com"
        )
        LOGGER.info("OIDC_ENDPOINT: %s", oidc_endpoint)
        return self.get_json(oidc_endpoint + "/.well-known/openid-configuration")

    def get_user_details(self, response):
        details = super(VendastaOpenIdConnect, self).get_user_details(response)
        details.update(
            {"roles": response.get("roles", []), "namespace": response.get("namespace")}
        )
        return details
