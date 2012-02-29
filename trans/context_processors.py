import trans
from django.conf import settings

def version(request):
    return {'version': trans.VERSION}

def title(request):
    return {'fallbacktitle': settings.SITE_TITLE}
