from django.contrib.sitemaps import Sitemap
from django.urls import reverse_lazy
from django.utils.functional import cached_property

from weblate.trans.models import Change, Component, Project, Translation
from weblate.utils.stats import prefetch_stats


class PagesSitemap(Sitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return [
            ("/", 1.0),
            ("/about/", 0.4),
            ("/keys/", 0.4),
        ]

    def location(self, item):
        return item[0]


class WeblateSitemap(Sitemap):
    priority = 0.0
    changefreq = None

    def items(self):
        raise NotImplementedError

    @cached_property
    def lastmod(self):
        return self.get_last_modified_date()

    def get_last_modified_date(self):
        raise NotImplementedError


class ProjectSitemap(WeblateSitemap):
    priority = 0.8

    def items(self):
        projects = Project.objects.filter(
            access_control__lt=Project.ACCESS_PRIVATE
        ).order_by("id")
        return prefetch_stats(projects)

    def get_last_modified_date(self):
        try:
            return Change.objects.order_by("-timestamp").values_list(
                "timestamp", flat=True
            )[0]
        except IndexError:
            return None


class ComponentSitemap(WeblateSitemap):
    priority = 0.6

    def items(self):
        components = Component.objects.filter(
            project__access_control__lt=Project.ACCESS_PRIVATE
        ).order_by("id")
        return prefetch_stats(components)

    def get_last_modified_date(self):
        try:
            return Translation.objects.order_by("-timestamp").values_list(
                "timestamp", flat=True
            )[0]
        except IndexError:
            return None


class TranslationSitemap(WeblateSitemap):
    priority = 0.2

    def items(self):
        translations = Translation.objects.filter(
            component__project__access_control__lt=Project.ACCESS_PRIVATE
        ).order_by("id")
        return prefetch_stats(translations)

    def get_last_modified_date(self):
        try:
            return Translation.objects.order_by("-timestamp").values_list(
                "timestamp", flat=True
            )[0]
        except IndexError:
            return None


class EngageSitemap(ProjectSitemap):
    """Wrapper around ProjectSitemap to point to engage page."""

    priority = 1.0

    def location(self, item):
        project = item
        return reverse_lazy("engage", kwargs={"project": project.slug})


class EngageLangSitemap(Sitemap):
    """Wrapper to generate sitemap for all per language engage pages."""

    priority = 0.9

    def items(self):
        """Return list of existing project, language tuples."""
        projects = Project.objects.filter(
            access_control__lt=Project.ACCESS_PRIVATE
        ).order_by("id")
        return [(project, lang) for project in projects for lang in project.languages]

    def location(self, obj):
        return reverse("engage", kwargs={"project": obj[0].slug, "lang": obj[1].code})


class ManifestSitemap(WeblateSitemap):
    """Sitemap for PWA manifest."""

    priority = 1.0 / 10

    def items(self):
        return [(None, None)]

    def location(self, obj):
        return reverse("manifest")

    def lastmod(self, item):
        return None


SITEMAPS = {
    "project": ProjectSitemap(),
    "engage": EngageSitemap(),
    "engagelang": EngageLangSitemap(),
    "component": ComponentSitemap(),
    "translation": TranslationSitemap(),
    "manifest": ManifestSitemap(),
    "pages": PagesSitemap(),
}
