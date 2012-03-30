from django.contrib import admin
from accounts.models import Profile

class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'language', 'suggested', 'translated']
    search_fields = ['user__username', 'user__email']
    list_filter = ['language']

admin.site.register(Profile, ProfileAdmin)

