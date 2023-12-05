from datetime import timedelta

from django.db import models, IntegrityError
from django.utils import timezone


class WarnType(models.IntegerChoices):
    WARN = 1, "Warn"
    UNWARN = 2, "Unwarn"
    BAN = 3, "Ban"
    UNBAN = 4, "Unban"
    MUTE = 5, "Mute"
    UNMUTE = 6, "Unmute"
    KICK = 7, "Kick"
    SPAM = 8, "SPAM"


class Spammers(models.Model):
    telegram_id = models.BigIntegerField(verbose_name="TelegramID", primary_key=True)
    from_cas = models.BooleanField(default=False, verbose_name="From CAS")

    class Meta:
        verbose_name = "Telegram ID"
        verbose_name_plural = "Telegram IDs"


class ChatAdmins(models.Model):
    chat_id = models.BigIntegerField(verbose_name="Telegram chat ID")
    user_id = models.BigIntegerField(verbose_name="Telegram user ID")
    shadow_admin = models.BooleanField(verbose_name="Shadow admin", default=False)
    can_delete = models.BooleanField(verbose_name="Can delete messages", default=False)
    can_ban = models.BooleanField(verbose_name="Can ban users", default=False)
    can_add_admin = models.BooleanField(verbose_name="Can add admins", default=False)

    class Meta:
        verbose_name = "Chat Admin"
        verbose_name_plural = "Chat Admins"
        indexes = [
            models.Index(fields=["chat_id", "user_id"]),
        ]

    def __str__(self):
        return f"{self.chat_id}:{self.user_id}:{self.shadow_admin}"

    @classmethod
    async def get_admins_by_chat(cls, chat_id=None):
        chats = {}
        qs = cls.objects.filter(shadow_admin=False)
        if chat_id:
            qs = qs.filter(chat_id=chat_id)
        async for admin in qs.order_by("chat_id").aiterator():
            chat = chats.setdefault(admin.chat_id, set())
            chat.add(admin.user_id)
        return chats


class UserWarn(models.Model):
    created = models.DateTimeField(verbose_name="Created", auto_now_add=True)
    user_id = models.BigIntegerField(verbose_name="User ID")
    chat_id = models.BigIntegerField(verbose_name="Chat ID")
    comment = models.TextField(verbose_name="Comment", null=True)
    warn_type = models.IntegerField(choices=WarnType.choices)

    def __str__(self):
        return f"{self.user_id}-{self.chat_id}-{self.comment}"

    class Meta:
        verbose_name = "User Warning"
        verbose_name_plural = "User Warnings"

        indexes = (
            models.Index(fields=("chat_id", "user_id", "-created", "warn_type")),
            models.Index(fields=("created",)),
        )

    @classmethod
    def get_warn_qs(cls, chat_id, user_id, warn_type=WarnType.WARN, warn_period=None):
        return cls.objects.filter(
            chat_id=chat_id,
            user_id=user_id,
            created__gt=timezone.now() - warn_period,
            warn_type=warn_type,
        )

    @classmethod
    async def set_warn(cls, chat_id, user_id, warn_type, comment: str = None):
        return await cls.objects.acreate(
            chat_id=chat_id, user_id=user_id, warn_type=warn_type, comment=comment
        )

    @classmethod
    async def check_warn_counter(cls, chat_id, user_id):
        settings = await ChatSettings.get_chat_settings(chat_id=chat_id)
        warn_count = await cls.get_warn_qs(
            chat_id=chat_id, user_id=user_id, warn_period=settings.warn_counter_period
        ).acount()
        return settings, warn_count

    @classmethod
    async def have_to_mute(cls, chat_id, user_id):
        settings, warn_count = await cls.check_warn_counter(
            chat_id=chat_id, user_id=user_id
        )
        if warn_count + 1 >= settings.warn_count:
            return settings.mute_period
        return None

    @classmethod
    async def delete_current_warnings(cls, chat_id, user_id):
        settings = await ChatSettings.get_chat_settings(chat_id=chat_id)
        qs = cls.get_warn_qs(
            chat_id=chat_id, user_id=user_id, warn_period=settings.warn_counter_period
        )
        await qs.adelete()
        return await qs.acount()


class ChatSettings(models.Model):
    chat_id = models.BigIntegerField(verbose_name="Chat ID", unique=True)
    warn_count = models.IntegerField(verbose_name="Warnings before action", default=3)
    warn_counter_period = models.DurationField(
        verbose_name="Time period for warning check", default=timedelta(days=3)
    )
    mute_period = models.DurationField(
        verbose_name="Mute period", default=timedelta(days=1)
    )

    class Meta:
        verbose_name = "Chat settings"
        verbose_name_plural = "Chats settings"

    def __str__(self):
        return f"{self.chat_id}"

    @classmethod
    async def get_chat_settings(cls, chat_id):
        settings = await cls.objects.filter(chat_id=chat_id).afirst()
        if not settings:
            try:
                settings = await cls.objects.acreate(chat_id=chat_id)
            except IntegrityError:
                return await cls.objects.filter(chat_id=chat_id).afirst()
        return settings
