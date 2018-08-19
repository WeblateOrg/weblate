from django import template
from django.template import Template

register = template.Library()

@register.simple_tag(takes_context=True)
def download_translation_url(context):
    template = "{% url 'download_translation' project=project.slug "
    if context.get('component') != None:
        template += "component=component.slug"
        
    template += "%}"
    if context.get('exporter') != None:
        template += "?format={{exporter.name}}"
        
    if context.get('language') != None:
        template += "&lang={{language.code}}"

    return Template(template).render(context)

@register.simple_tag(takes_context=True)
def translation_download_link(context):
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
    template = '''
        {% load i18n %}

        {% blocktrans with project.component_format_names as format %}
        '''
    exporter = context.get('exporter')
    template += "Original" if exporter == None  else exporter['name']
    
    template += '''
        {% endblocktrans %}
    '''

    return Template(template).render(context)