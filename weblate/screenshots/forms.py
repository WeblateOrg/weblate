# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import io
from typing import Any
from urllib.parse import urlparse

import requests
from django import forms
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.http.request import validate_host
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.screenshots.models import Screenshot
from weblate.trans.forms import QueryField
from weblate.utils.forms import SortedSelect
from weblate.utils.validators import WeblateURLValidator


class ScreenshotImageValidationMixin:
    def clean_images(self, cleaned_data: dict[str, Any] | None) -> dict[str, Any]:
        if cleaned_data is None:
            cleaned_data = {}
        image = cleaned_data.get("image")
        image_url = cleaned_data.get("image_url")
        if not image and not image_url:
            raise forms.ValidationError(
                gettext_lazy("You need to provide either image file or image URL.")
            )

        if image_url and not image:
            cleaned_data["image"] = self.download_image(image_url)
            image_field = Screenshot._meta.get_field("image")  # noqa: SLF001
            image_field.run_validators(cleaned_data["image"])

        cleaned_data.pop("image_url", None)
        return cleaned_data

    def download_image(self, url: str) -> InMemoryUploadedFile:
        """Download image from the provided URL."""
        if not validate_host(
            urlparse(url).hostname or "", settings.ALLOWED_ASSET_DOMAINS
        ):
            raise forms.ValidationError(
                gettext_lazy("Image URL domain is not allowed.")
            )
        try:
            response = requests.get(url, timeout=2.0)
        except requests.RequestException as e:
            raise forms.ValidationError(
                gettext_lazy(
                    "Unable to download image from the provided URL (network error)."
                )
            ) from e
        if not (200 <= response.status_code < 300):
            raise forms.ValidationError(
                gettext_lazy(
                    "Unable to download image from the provided URL (HTTP status code: %(code)s)."
                )
                % {"code": response.status_code}
            )
        content = response.content
        content_type = response.headers.get("Content-Type")
        filename = url.rsplit("/", maxsplit=1)[-1] or "screenshot"
        return InMemoryUploadedFile(
            file=io.BytesIO(content),
            field_name="image",
            name=filename,
            content_type=content_type,
            size=len(content),
            charset=None,
        )


class ScreenshotInput(forms.FileInput):
    def render(self, name, value, attrs=None, renderer=None, **kwargs):
        rendered_input = super().render(name, value, attrs, renderer, **kwargs)
        paste_button = render_to_string("screenshots/snippets/paste-button.html")
        return format_html("{}{}", rendered_input, paste_button)


class ScreenshotEditForm(forms.ModelForm, ScreenshotImageValidationMixin):
    """Screenshot editing."""

    image_url = forms.URLField(required=False, label="Image URL")

    class Meta:
        model = Screenshot
        fields = ("name", "image", "repository_filename", "image_url")
        widgets = {  # noqa: RUF012
            "image": ScreenshotInput,
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            cleaned_data = {}
        return self.clean_images(cleaned_data)


class LanguageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.language


class ScreenshotForm(forms.ModelForm, ScreenshotImageValidationMixin):
    """Screenshot upload."""

    image_url = forms.URLField(
        required=False, label="Image URL", validators=[WeblateURLValidator()]
    )

    class Meta:
        model = Screenshot
        fields = ("name", "repository_filename", "image", "translation", "image_url")
        widgets = {  # noqa: RUF012
            "translation": SortedSelect,
            "image": ScreenshotInput,
        }
        field_classes = {  # noqa: RUF012
            "translation": LanguageChoiceField,
        }

    def __init__(
        self, component, data=None, files=None, instance=None, initial=None
    ) -> None:
        self.component = component
        super().__init__(data=data, files=files, instance=instance, initial=initial)

        translations = component.translation_set.prefetch_related("language")
        if initial and "translation" in initial:
            translations = translations.filter(
                pk__in=(initial["translation"].pk, component.source_translation.pk)
            )
        self.fields["translation"].queryset = translations
        # This is overridden from initial arg of the form
        self.fields["translation"].initial = component.source_translation
        self.fields["translation"].empty_label = None
        self.fields["image"].required = False

    def clean(self):
        cleaned_data = super().clean()
        return self.clean_images(cleaned_data)


class SearchForm(forms.Form):
    q = QueryField(required=False)
