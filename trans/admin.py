from django.contrib import admin
from trans.models import Project, SubProject, Translation, Unit, Suggestion

class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'web']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'web']

admin.site.register(Project, ProjectAdmin)

class SubProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'project', 'repo', 'branch']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'slug', 'repo', 'branch']
    list_filter = ['project']

admin.site.register(SubProject, SubProjectAdmin)

class TranslationAdmin(admin.ModelAdmin):
    list_display = ['subproject', 'language', 'translated', 'fuzzy', 'revision', 'filename']
    search_fields = ['subproject__slug', 'language__code', 'translated', 'fuzzy', 'revision', 'filename']
    list_filter = ['subproject__project', 'subproject', 'language']

admin.site.register(Translation, TranslationAdmin)

class UnitAdmin(admin.ModelAdmin):
    list_display = ['source', 'target']
    search_fields = ['source', 'target']

admin.site.register(Unit, UnitAdmin)

class SuggestionAdmin(admin.ModelAdmin):
    list_display = ['checksum', 'target']
    search_fields = ['checksum', 'target']

admin.site.register(Suggestion, SuggestionAdmin)

