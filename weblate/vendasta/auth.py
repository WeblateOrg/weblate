# -*- coding: utf-8 -*-
import requests
from social_core.backends.open_id_connect import OpenIdConnectAuth
from social_core.utils import cache

from weblate.logger import LOGGER
from weblate.utils import requests
from weblate.utils.requests import request


class VendastaOpenIdConnect(OpenIdConnectAuth):
    """Vendasta OpenID authentication Backend."""

    name = "Single-sign-on"
    ACCESS_TOKEN_METHOD = "POST"
    EXTRA_DATA = [("sub", "id"), "namespace", "roles"]
    USERNAME_KEY = "sub"

    @cache(ttl=86400)
    def oidc_config(self):
        oidc_endpoint = self.setting("OIDC_ENDPOINT", "https://iam-prod.apigateway.co")
        LOGGER.info("OIDC_ENDPOINT: %s", oidc_endpoint)
        return self.get_json(oidc_endpoint + "/.well-known/openid-configuration")

    def get_user_details(self, response):
        details = super(VendastaOpenIdConnect, self).get_user_details(response)
        details.update(
            {"roles": response.get("roles", []), "namespace": response.get("namespace")}
        )
        return details


def user_can_customize_text(user):
    if not user:
        return False
    social = user.social_auth.get(provider="Single-sign-on")
    LOGGER.info("SOCIAL: ", social.name)
    url = social.setting("OIDC_ENDPOINT")
    LOGGER.info("URL: ", url)
    access_token = social.extra_data["access_token"]
    LOGGER.info("T: ", access_token[:5])
    if user:
        return True
    response = request(
        "POST", url, headers={"Authentication": "Bearer %s".format(access_token)}
    )
    if response.status_code != requests.codes.ok:
        pass
