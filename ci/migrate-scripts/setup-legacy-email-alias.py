# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from social_django.models import UserSocialAuth

from weblate.accounts.models import VerifiedEmail
from weblate.auth.models import User

victim = User.objects.create_user("legacy-email-victim", "victim@github.com", "secret")
social = UserSocialAuth.objects.create(
    user=victim, provider="email", uid="victim@gıthub.com"
)
VerifiedEmail.objects.create(social=social, email="victim@gıthub.com")
other = User.objects.create_user("legacy-email-benign", "benign@example.net", "secret")
social = UserSocialAuth.objects.create(
    user=other, provider="email", uid="BENIGN@example.net"
)
VerifiedEmail.objects.create(social=social, email="BENIGN@example.net")
