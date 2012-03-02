from django.contrib import admin
from accounts.models import Profile

class ProfileAdmin(admin.ModelAdmin):
    search_fields = ['user__username']

admin.site.register(Profile, ProfileAdmin)

