from django import template


register = template.Library()


@register.simple_tag()
def replace(value, char, replace_char):
    return value.replace(char, replace_char)
