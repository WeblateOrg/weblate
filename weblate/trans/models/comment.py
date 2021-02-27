#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from django.conf import settings
from django.db import models

from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.change import Change
from weblate.utils.antispam import report_spam
from weblate.utils.fields import JSONField
from weblate.utils.request import get_ip_address, get_user_agent_raw


class CommentManager(models.Manager):
    # pylint: disable=no-init

    def add(self, unit, request, text):
        """Add comment to this unit."""
        user = request.user
        new_comment = self.create(
            user=user,
            unit=unit,
            comment=text,
            userdetails={
                "address": get_ip_address(request),
                "agent": get_user_agent_raw(request),
            },
        )
        user.profile.increase_count("commented")
        Change.objects.create(
            unit=unit,
            comment=new_comment,
            action=Change.ACTION_COMMENT,
            user=user,
            author=user,
            details={"comment": text},
        )


class CommentQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("timestamp")


class Comment(models.Model, UserDisplayMixin):
    unit = models.ForeignKey("trans.Unit", on_delete=models.deletion.CASCADE)
    comment = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved = models.BooleanField(default=False, db_index=True)
    userdetails = JSONField()

    objects = CommentManager.from_queryset(CommentQuerySet)()

    class Meta:
        app_label = "trans"
        verbose_name = "string comment"
        verbose_name_plural = "string comments"

    def __str__(self):
        return "comment for {} by {}".format(
            self.unit, self.user.username if self.user else "unknown"
        )

    def report_spam(self):
        report_spam(
            self.userdetails["address"], self.userdetails["agent"], self.comment
        )
