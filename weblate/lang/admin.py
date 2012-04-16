from django.contrib import admin
from weblate.lang.models import Language

class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'get_plural_form']
    search_fields = ['name', 'code']

admin.site.register(Language, LanguageAdmin)


