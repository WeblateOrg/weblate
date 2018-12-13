from django import template
from django.utils.translation import gettext as _
from django.urls import reverse

register = template.Library()

@register.simple_tag(takes_context=True)
def translation_download_url(context):
    #import pdb; pdb.set_trace()

    project = context.get('project')

    kwargs = {}
    kwargs['project'] = project.slug
    component = context.get('component')
    if component != None:
        kwargs['component'] = component['slug']
        
    url = reverse('download_translation', kwargs=kwargs) 

    query_params = []
    exporter = context.get('exporter')
    if exporter != None:
        query_params.append(f'format={exporter["name"]}')
        
    language = context.get('language')
    if language != None:
        query_params.append(f'lang={language["code"]}')

    if len(query_params) > 0:
        url += '?'
        url += "&".join(query_params)

    return url;

@register.simple_tag(takes_context=True)
def translation_download_link_todo(context, todo=False):
    translation_download_link(context, True)

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
