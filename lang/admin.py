from django.contrib import admin
from lang.models import Language

class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']

admin.site.register(Language, LanguageAdmin)


