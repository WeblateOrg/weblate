import trans
from django.conf import settings

def version(request):
    return {'version': trans.VERSION}

def title(request):
    return {'site_title': settings.SITE_TITLE}
