# -*- coding: utf-8 -*-
import os
import requests

from weblate.logger import LOGGER
from weblate.utils.requests import request

WEBLATE_AA_HOST = os.environ.get("WEBLATE_AA_HOST")
WEBLATE_AA_API_USER = os.environ.get("WEBLATE_AA_API_USER")
WEBLATE_AA_API_KEY = os.environ.get("WEBLATE_AA_API_KEY")

SUBSCRIPTION_TIERS_WITH_CUSTOMIZE_RESTRICTIONS = [
    "FREE",
    "STARTER",
    "vbp2_startup_subscription",
]


def partner_has_customize_permissions(partner_id):
    """Check if partner subscription tier has customize restrictions"""
    try:
        subscription_tier = get_partner_subscription_tier(partner_id)
        return (
            subscription_tier
            and subscription_tier not in SUBSCRIPTION_TIERS_WITH_CUSTOMIZE_RESTRICTIONS
        )
    except requests.HTTPError as e:
        LOGGER.error("Failed to get partner subscription tier: %s", e)
        return False


def get_partner_subscription_tier(partner_id):
    """Get partner from AA and return subscription tier"""
    get_partner_url = (
        WEBLATE_AA_HOST
        + "/internalApi/v3/partner/get/?apiUser={0}&apiKey={1}&partnerId={2}".format(
            WEBLATE_AA_API_USER, WEBLATE_AA_API_KEY, partner_id
        )
    )
    response = request("get", get_partner_url)
    if response.status_code != requests.codes.ok:
        return False
    LOGGER.info("AA RESPONSE: %s", str(response.json()))
    return response.json().get("data", {}).get("subscription_tier")
