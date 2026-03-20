from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'user_type', 'is_active']
    list_filter = ['user_type', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('user_type',)}),
    )
