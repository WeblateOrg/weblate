# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

"""Whoosh based full text search."""

from __future__ import absolute_import, unicode_literals

from celery_batches import SimpleRequest
from django.conf import settings

from weblate.celery import app as celery_app


def extract_batch_kwargs(*args, **kwargs):
    """
    Wrapper to extract args from batch task.

    It can be either passed directly in eager mode or as requests in
    batch mode.
    """
    if args and isinstance(args[0], list) and isinstance(args[0][0], SimpleRequest):
        return [request.kwargs for request in args[0]]
    return [kwargs]


def extract_batch_args(*args):
    """
    Wrapper to extract args from batch task.

    It can be either passed directly in eager mode or as requests in
    batch mode.
    """
    if isinstance(args[0], list) and isinstance(args[0][0], SimpleRequest):
        return [request.args for request in args[0]]
    return [args]


def get_queue_length(queue='celery'):
    with celery_app.connection_or_acquire() as conn:
        return conn.default_channel.queue_declare(
            queue=queue, durable=True, auto_delete=False
        ).message_count


def get_queue_list():
    """List queues in Celery."""
    result = {'celery'}
    for route in settings.CELERY_TASK_ROUTES.values():
        if 'queue' in route:
            result.add(route['queue'])
    return result


def get_queue_stats():
    """Calculate queue stats."""
    return {queue: get_queue_length(queue) for queue in get_queue_list()}


def is_task_ready(task):
    """
    Workaround broken ready() for failed Celery results

    In case the task ends with an exception, the result tries to reconstruct
    that. It can fail in case the exception can not be reconstructed using
    data in args attribute.

    See https://github.com/celery/celery/issues/5057
    """
    try:
        return task.ready()
    except TypeError:
        return True


def get_task_progress(task):
    """Return progress of a Celery task."""
    # Completed task
    if is_task_ready(task):
        return 100
    # In progress
    if task.state == "PROGRESS" and task.result:
        return task.result["progress"]

    # Not yet started
    return 0
