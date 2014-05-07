"""Whiteboard model."""

from django.db import models


class WhiteboardMessage(models.Model):
    message = models.TextField(blank=True)

    class Meta:
        app_label = 'trans'
