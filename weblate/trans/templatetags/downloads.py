from django import template
from django.template import Template

register = template.Library()

@register.simple_tag(takes_context=True)
def download_translation_url(context):
    template = "{% url 'download_translation' project=project.slug "
    if context.get('component') != None:
        template += "component=component.slug"
        
    template += "%}"

    query_params = []
    if context.get('exporter') != None:
        query_params.append("format={{exporter.name}}")
        
    if context.get('language') != None:
        query_params.append("lang={{language.code}}")

    if query_params.__sizeof__ > 0:
        template += '?'
        template += "&".join(query_params)

    return Template(template).render(context)

@register.simple_tag(takes_context=True)
def translation_download_link(context, todo=False):
    before_link_text = '''
        {% load downloads %}
        {% load i18n %}

        <a href="{% download_translation_url  %}" 
        title="{% trans "Download for an offline translation." %}">
    '''

    closing_tag = "</a>"
    
    template = before_link_text + link_text(context) + closing_tag
    return Template(template).render(context)


def link_text(context):
    text = ""
    blocktrans(project.component_format_names)
    exporter = context.get('exporter')
    text += "Original" if exporter == None  else exporter['name']

    return Template(template).render(context)
