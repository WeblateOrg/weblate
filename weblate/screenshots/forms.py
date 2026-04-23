# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import io
from typing import Any, cast

import requests
from django import forms
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.forms.forms import BaseForm
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy

from weblate.screenshots.models import Screenshot
from weblate.trans.forms import QueryField
from weblate.utils.forms import AssetImageField, SortedSelect
from weblate.utils.requests import open_asset_url
from weblate.utils.validators import ALLOWED_IMAGES, WeblateURLValidator


class ScreenshotImageValidationMixin(BaseForm):
    def raise_image_url_error(self, message) -> None:
        raise forms.ValidationError({"image_url": message})

    def clean_images(
        self, cleaned_data: dict[str, Any], edit: bool = False
    ) -> dict[str, Any]:
        image = cleaned_data.get("image")
        image_url = cleaned_data.get("image_url")
        image_submitted = "image" in self.files
        if not image and not image_url and not image_submitted:
            raise forms.ValidationError(
                gettext("You need to provide either image file or image URL.")
            )

        if (edit and ("image" not in self.changed_data) and image_url) or (
            not edit and image_url and not image
        ):
            # download from image_url only if image is not provided and not updated
            cleaned_data["image"] = self.download_image(image_url)
            image_field = Screenshot._meta.get_field("image")  # noqa: SLF001
            image_field.run_validators(cleaned_data["image"])

        cleaned_data.pop("image_url", None)
        return cleaned_data

    def download_image(self, url: str) -> InMemoryUploadedFile:
        """Download image from the provided URL."""
        try:
            with open_asset_url("get", url) as response:
                content = b""
                for chunk in response.iter_content(
                    chunk_size=settings.ALLOWED_ASSET_SIZE + 1
                ):
                    if not content:
                        content = chunk
                    else:
                        # This can be slow, but it typically won't happen
                        content += chunk
                    if len(content) > settings.ALLOWED_ASSET_SIZE:
                        break
                if len(content) > settings.ALLOWED_ASSET_SIZE:
                    self.raise_image_url_error(gettext("Image is too big."))
                content_type = response.headers.get("Content-Type")
                if not content_type or content_type not in ALLOWED_IMAGES:
                    self.raise_image_url_error(
                        gettext("Unsupported image type: %s") % content_type
                    )
        except forms.ValidationError as error:
            if hasattr(error, "error_dict"):
                raise
            if error.code == "download_failed" and error.params is not None:
                self.raise_image_url_error(
                    gettext(
                        "Unable to download image from the provided URL (HTTP status code: %(code)s)."
                    )
                    % error.params
                )
            self.raise_image_url_error(error.messages[0])
        except requests.RequestException as e:
            raise forms.ValidationError(
                {
                    "image_url": gettext(
                        "Unable to download image from the provided URL."
                    )
                }
            ) from e
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

    image_url = forms.URLField(
        required=False,
        label=gettext_lazy("Image URL"),
        help_text=gettext_lazy("The image will be downloaded and stored."),
        validators=[WeblateURLValidator()],
    )

    class Meta:
        model = Screenshot
        fields = ("name", "image", "image_url", "repository_filename")
        widgets = {  # noqa: RUF012
            "image": ScreenshotInput,
        }
        field_classes = {"image": AssetImageField}  # noqa: RUF012

    def clean(self):
        cleaned_data = super().clean()
        return self.clean_images(cleaned_data or {}, edit=True)


class LanguageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.language


class ScreenshotForm(forms.ModelForm, ScreenshotImageValidationMixin):
    """Screenshot upload."""

    image_url = forms.URLField(
        required=False,
        label=gettext_lazy("Image URL"),
        help_text=gettext_lazy("The image will be downloaded and stored."),
        validators=[WeblateURLValidator()],
    )

    class Meta:
        model = Screenshot
        fields = ("name", "repository_filename", "image", "image_url", "translation")
        widgets = {  # noqa: RUF012
            "translation": SortedSelect,
            "image": ScreenshotInput,
        }
        field_classes = {  # noqa: RUF012
            "image": AssetImageField,
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
        translation_field = cast("LanguageChoiceField", self.fields["translation"])
        translation_field.queryset = translations
        # This is overridden from initial arg of the form
        translation_field.initial = component.source_translation
        translation_field.empty_label = None
        self.fields["image"].required = False

    def clean(self):
        cleaned_data = super().clean()
        return self.clean_images(cleaned_data or {})


class SearchForm(forms.Form):
    q = QueryField(required=False)
