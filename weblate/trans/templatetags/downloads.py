from django import template
from django.template import Template
from django.utils.translation import gettext as _
from django.urls import reverse

register = template.Library()

@register.simple_tag(takes_context=True)
def translation_download_url(context):
    project = context.get('project')
    url = reverse('download_translation', kwargs={'project': project['slug']}) 


    #if context.get('component') != None:
    #    template += "component=component.slug"
    #    
    #template += "%}"

    #query_params = []
    #if context.get('exporter') != None:
    #    query_params.append("format={{exporter.name}}")
    #    
    #if context.get('language') != None:
    #    query_params.append("lang={{language.code}}")

    #if query_params.__sizeof__() > 0:
    #    template += '?'
    #    template += "&".join(query_params)

    #return Template(template).render(context)
    return url;

@register.simple_tag(takes_context=True)
def translation_download_link(context, todo=False):
    translation_download_url_variable = translation_download_url(context)
    title_tag = _('title="Download for an offline translation."')
    opening_tag = f'<a {title_tag} href="{translation_download_url_variable}">'

    closing_tag = "</a>"
    
    return opening_tag + link_text(context) + closing_tag


def link_text(context):
    exporter = context.get('exporter')

    return _("Original" if exporter == None  else exporter['name'])
