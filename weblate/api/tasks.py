# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from celery import Task

from weblate.utils.celery import app


class MessageNotDeliveredError(Exception):
    """Exception raised when a message could not be delivered."""


class MessageDeliveryBaseTask(Task):
    retry_backoff = True
    autoretry_for = (MessageNotDeliveredError,)
    max_retries = 5
    timeout = 15  # seconds

    def run(self, *args, **kwargs):
        result = self.send_message(*args, **kwargs)
        if not self.is_success(result):
            # TODO: complete error message
            msg = "Some error message"
            raise MessageNotDeliveredError(msg)

    def send_message(self, *args, **kwargs):
        """TODO: add docstring."""
        raise NotImplementedError

    def is_success(self, result) -> bool:
        """TODO: add docstring."""
        raise NotImplementedError


class WebhookDeliveryTask(MessageDeliveryBaseTask):
    name = "weblate.api.webhook_delivery"

    def send_message(
        self, *, url: str = "", headers: dict | None = None, data: dict | None = None
    ) -> requests.Response:
        headers = headers or {}
        data = data or {}
        try:
            return requests.post(url, json=data, headers=headers, timeout=self.timeout)
        except requests.exceptions.ConnectionError as error:
            raise MessageNotDeliveredError from error

    def is_success(self, result: requests.Response):
        return 200 <= result.status_code <= 299


webhook_delivery_task = app.register_task(
    WebhookDeliveryTask, autoretry_for=(MessageNotDeliveredError,)
)
