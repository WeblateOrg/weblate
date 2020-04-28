# -*- coding: utf-8 -*-
import os
from social_core.backends.open_id_connect import OpenIdConnectAuth


class VendastaOpenIdConnect(OpenIdConnectAuth):
    """ Vendasta OpenID authentication Backend """

    name = "vendasta"
    OIDC_ENDPOINT = os.environ.get("WEBLATE_SOCIAL_AUTH_VENDASTA_OIDC_URL", "")
    ACCESS_TOKEN_METHOD = "POST"
    EXTRA_DATA = [("sub", "id"), "namespace", "roles"]
