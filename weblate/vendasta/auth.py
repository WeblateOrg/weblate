# -*- coding: utf-8 -*-
import os

from social_core.backends.open_id_connect import OpenIdConnectAuth


class VendastaOpenIdConnect(OpenIdConnectAuth):
    """Vendasta OpenID authentication Backend."""

    name = "vendasta"
    OIDC_ENDPOINT = os.environ.get("WEBLATE_SOCIAL_AUTH_VENDASTA_OIDC_URL", "http://iam-prod.vendasta-internal.com")
    ACCESS_TOKEN_METHOD = "POST"
    EXTRA_DATA = [("sub", "id"), "namespace", "roles"]
    USERNAME_KEY = "sub"

    def get_user_details(self, response)    :
        details = super(VendastaOpenIdConnect, self).get_user_details(response)
        details.update({
            'roles': response.get('roles', []),
            'namespace': response.get('namespace')
        })
        return details
