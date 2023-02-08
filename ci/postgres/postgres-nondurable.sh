#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# setting non-durable options
# https://www.postgresql.org/docs/current/static/non-durability.html
echo "Configuring postgres non-durable options."
{
  # no need to flush data to disk.
  echo "fsync = off"
  # no need to force WAL writes to disk on every commit.
  echo "synchronous_commit = off"
  # no need to guard against partial page writes.
  echo "full_page_writes = off"
  # increase checkpoint interval
  echo "checkpoint_timeout = 3600"
  echo "max_wal_size = 128"
} >> /var/lib/postgresql/data/postgresql.conf
