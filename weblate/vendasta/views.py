# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from weblate.auth.models import Group
from weblate.lang.models import Language, Plural
from weblate.trans.forms import NewNamespacedLanguageForm
from weblate.trans.models import Change
from weblate.trans.util import render
from weblate.utils import messages
from weblate.utils.views import get_component
from weblate.vendasta.constants import ACCESS_NAMESPACE, NAMESPACE_SEPARATOR


@never_cache
@login_required
def new_namespaced_language(request, project, component):
    obj = get_component(request, project, component)

    namespace_query = request.user.groups.filter(roles__name=ACCESS_NAMESPACE).order_by(
        "name"
    )
    if namespace_query.count():
        namespace = namespace_query[0].name
    else:
        raise PermissionDenied()

    if request.method == "POST":
        form = NewNamespacedLanguageForm(obj, request.POST, namespace=namespace)

        if form.is_valid():
            langs = form.cleaned_data["lang"]
            kwargs = {
                "user": request.user,
                "author": request.user,
                "component": obj,
                "details": {},
            }
            for language in Language.objects.filter(code__in=langs):
                namespaced_language = Language.objects.create(
                    code=language.code + NAMESPACE_SEPARATOR + namespace,
                    name="{} ({})".format(language.name, namespace),
                    direction=language.direction,
                )
                baseplural = language.plural
                namespaced_language.plural_set.create(
                    source=Plural.SOURCE_DEFAULT,
                    number=baseplural.number,
                    equation=baseplural.equation,
                )

                namespace_group = Group.objects.get(name=namespace)
                namespace_group.languages.add(namespaced_language)

                kwargs["details"]["language"] = namespaced_language.code
                translation = obj.add_new_language(namespaced_language, request)
                if translation:
                    kwargs["translation"] = translation
                    if len(langs) == 1:
                        obj = translation
                    Change.objects.create(action=Change.ACTION_ADDED_LANGUAGE, **kwargs)
            return redirect(obj)
        messages.error(request, _("Please fix errors in the form."))
    else:
        form = NewNamespacedLanguageForm(obj, namespace=namespace)

    context = {
        "object": obj,
        "project": obj.project,
        "form": form,
        "namespace": namespace,
    }
    return render(request, "new-namespaced-language.html", context)
