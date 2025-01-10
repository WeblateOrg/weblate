# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy

from weblate.fonts.utils import get_font_name
from weblate.fonts.validators import validate_font
from weblate.lang.models import Language
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models import Project
from weblate.utils.data import data_dir

FONT_STORAGE = FileSystemStorage(location=data_dir("fonts"))


class Font(models.Model, UserDisplayMixin):
    family = models.CharField(
        verbose_name=gettext_lazy("Font family"),
        max_length=100,
        blank=True,
        db_index=False,
    )
    style = models.CharField(
        verbose_name=gettext_lazy("Font style"), max_length=100, blank=True
    )
    font = models.FileField(
        verbose_name=gettext_lazy("Font file"),
        validators=[validate_font],
        storage=FONT_STORAGE,
        help_text=gettext_lazy("OpenType and TrueType fonts are supported."),
    )
    project = models.ForeignKey(Project, on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.SET_NULL,
    )

    class Meta:
        unique_together = [("family", "style", "project")]
        verbose_name = "Font"
        verbose_name_plural = "Fonts"

    def __str__(self) -> str:
        return f"{self.family} {self.style}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.field_errors: dict[str, list[ValidationError]] = {}

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ) -> None:
        from weblate.fonts.tasks import update_fonts_cache

        self.clean()
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )
        update_fonts_cache.delay()

    def get_absolute_url(self) -> str:
        return reverse("font", kwargs={"pk": self.pk, "project": self.project.slug})

    def clean_fields(self, exclude=None) -> None:
        self.field_errors = {}
        try:
            super().clean_fields(exclude)
        except ValidationError as error:
            self.field_errors = error.error_dict
            raise

    def clean(self) -> None:
        # Try to parse file only if it passed validation
        if "font" not in self.field_errors and not self.family:
            self.family, self.style = get_font_name(self.font)

    def get_usage(self):
        related = FontGroup.objects.filter(
            models.Q(font=self) | models.Q(fontoverride__font=self)
        )
        return related.order().distinct()


class FontGroupQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("name")


class FontGroup(models.Model):
    name = models.SlugField(
        verbose_name=gettext_lazy("Font group name"),
        max_length=100,
        help_text=gettext_lazy(
            "Identifier you will use in checks to select this font group. "
            "Avoid whitespaces and special characters."
        ),
    )
    font = models.ForeignKey(
        Font,
        verbose_name=gettext_lazy("Default font"),
        on_delete=models.deletion.CASCADE,
        help_text=gettext_lazy(
            "Default font is used unless per language override matches."
        ),
    )
    project = models.ForeignKey(
        Project, on_delete=models.deletion.CASCADE, db_index=False
    )

    objects = FontGroupQuerySet.as_manager()

    class Meta:
        unique_together = [("project", "name")]
        verbose_name = "Font group"
        verbose_name_plural = "Font groups"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse(
            "font_group", kwargs={"pk": self.pk, "project": self.project.slug}
        )


class FontOverride(models.Model):
    group = models.ForeignKey(
        FontGroup, on_delete=models.deletion.CASCADE, db_index=False
    )
    font = models.ForeignKey(
        Font, on_delete=models.deletion.CASCADE, verbose_name=gettext_lazy("Font")
    )
    language = models.ForeignKey(
        Language,
        on_delete=models.deletion.CASCADE,
        verbose_name=gettext_lazy("Language"),
    )

    class Meta:
        unique_together = [("group", "language")]
        verbose_name = "Font override"
        verbose_name_plural = "Font overrides"

    def __str__(self) -> str:
        return f"{self.group}:{self.font}:{self.language}"
