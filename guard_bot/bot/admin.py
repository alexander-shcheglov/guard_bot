from django.contrib import admin

from guard_bot.bot.models import Spammers, ChatAdmins


# Register your models here.


@admin.register(Spammers)
class SpammersAdmin(admin.ModelAdmin):
    pass


@admin.register(ChatAdmins)
class ChatAdminsAdmin(admin.ModelAdmin):
    pass
