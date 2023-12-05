from datetime import timedelta

import pytest
from unittest.mock import patch
from django.db import IntegrityError


from guard_bot.bot.models import WarnType, Spammers, ChatAdmins, UserWarn, ChatSettings

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.django_db
class TestModels:
    pytestmark = pytest.mark.django_db(transaction=True)

    def test_warntype(self):
        assert WarnType.choices == [
            (1, 'Warn'),
            (2, 'Unwarn'),
            (3, 'Ban'),
            (4, 'Unban'),
            (5, 'Mute'),
            (6, 'Unmute'),
            (7, 'Kick'),
            (8, 'SPAM'),
        ]

    def test_spammers(self):
        kwargs = {'telegram_id': 1}
        Spammers.objects.create(**kwargs)
        with pytest.raises(IntegrityError):
            Spammers.objects.create(**kwargs)
        spammer = Spammers.objects.get(telegram_id=1)
        assert spammer.telegram_id == 1
        assert spammer.from_cas is False

    def test_chat_admins(self):
        kwargs = {
            'chat_id': 1,
            'user_id': 1,
        }

        ChatAdmins.objects.create(**kwargs)
        admin = ChatAdmins.objects.get(**kwargs)
        assert admin.chat_id == 1
        assert admin.user_id == 1
        assert admin.shadow_admin is False
        assert admin.can_delete is False
        assert admin.can_ban is False
        assert admin.can_add_admin is False

        assert str(admin) == '1:1:False'

    @pytest.mark.asyncio
    async def test_chat_admin_get_admins(self, not_shadow_chat_admin, shadow_chat_admin):
        assert await ChatAdmins.get_admins_by_chat(chat_id=2) == {}
        assert await ChatAdmins.get_admins_by_chat(chat_id=1) == {1: {1}}
        assert await ChatAdmins.get_admins_by_chat() == {1: {1}}

    def test_user_warn(self, user_warn_mute):
        assert user_warn_mute.user_id == 1
        assert user_warn_mute.chat_id == 1
        assert user_warn_mute.warn_type == WarnType.WARN
        assert user_warn_mute.comment is None

        assert str(user_warn_mute) == '1-1-None'

    def test_user_warn_qs(self, user_warn_mute, chat_default_settings):
        period = chat_default_settings.warn_counter_period
        assert UserWarn.get_warn_qs(
            chat_id=1, user_id=1, warn_type=WarnType.MUTE, warn_period=period).exists() is False
        assert UserWarn.get_warn_qs(
            chat_id=1, user_id=1, warn_type=WarnType.WARN, warn_period=period).exists() is True
        assert UserWarn.get_warn_qs(
            chat_id=1, user_id=1, warn_type=WarnType.WARN, warn_period=period).count() == 1
        assert UserWarn.get_warn_qs(
            chat_id=1, user_id=2, warn_type=WarnType.WARN, warn_period=period).count() == 0
        assert UserWarn.get_warn_qs(
            chat_id=2, user_id=1, warn_type=WarnType.WARN, warn_period=period).count() == 0

    @pytest.mark.asyncio
    async def test_user_warn_async(self, chat_default_settings):
        await UserWarn.set_warn(chat_id=1, user_id=1, warn_type=WarnType.WARN)
        assert await UserWarn.have_to_mute(chat_id=1, user_id=1) is None
        await UserWarn.set_warn(chat_id=1, user_id=1, warn_type=WarnType.WARN)

        _, warn_count = await UserWarn.check_warn_counter(chat_id=1, user_id=1)
        assert warn_count == 2

        assert await UserWarn.have_to_mute(user_id=1, chat_id=1) == chat_default_settings.mute_period

        assert await UserWarn.delete_current_warnings(chat_id=1, user_id=1) == 0

    def test_chat_settings(self, chat_default_settings):
        assert chat_default_settings.chat_id == 0
        assert chat_default_settings.mute_period == timedelta(days=1)
        assert chat_default_settings.warn_counter_period == timedelta(days=3)
        assert chat_default_settings.warn_count == 3
        assert str(chat_default_settings) == '0'

    @pytest.mark.asyncio
    async def test_chat_settings_get_default(self):
        assert await ChatSettings.objects.acount() == 0
        assert (await ChatSettings.get_chat_settings(chat_id=1)).id == (await ChatSettings.objects.aget(chat_id=1)).id
        assert await ChatSettings.objects.acount() == 1
        with pytest.raises(IntegrityError):
            await ChatSettings.objects.acreate(chat_id=1)
        assert (await ChatSettings.get_chat_settings(chat_id=1)).id == (await ChatSettings.objects.aget(chat_id=1)).id
        await ChatSettings.objects.filter(chat_id=1).adelete()

        with patch(
                'guard_bot.bot.models.ChatSettings.objects.acreate',
                side_effect=IntegrityError('Patched acreate exception')
        ):
            assert await ChatSettings.get_chat_settings(chat_id=1) is None

