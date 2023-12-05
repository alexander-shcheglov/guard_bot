import asyncio

import pytest
import pytest_asyncio
from telethon.errors import ChannelPrivateError, ChatWriteForbiddenError

from guard_bot.bot.models import ChatAdmins, UserWarn, WarnType, ChatSettings
from tests.guard_bot.bot.management.commands.integration.conftest import PatchedTelegramClient

from django.conf import settings
if settings.TESTING and not settings.TEST_SERVER:
    pytest.skip(f'Integration tests skipped. TEST_SERVER is {settings.TEST_SERVER}', allow_module_level=True)

pytestmark = pytest.mark.django_db()


def check_command_execution(admin: PatchedTelegramClient, as_bot: PatchedTelegramClient):
    old_send_message = admin.send_message

    async def _send_message(*args, **kwargs):
        message = kwargs.pop('message', None)
        await old_send_message(*args, message=message, **kwargs)
        await as_bot.run_until_command_complete(message)

    admin.send_message = _send_message


@pytest_asyncio.fixture(scope="module")
async def setup(event_loop, chat, admin, user_one, user_two, as_bot):
    await user_one.join_to_channel(admin, chat)
    await user_two.join_to_channel(admin, chat)
    await as_bot.join_to_channel(admin, chat)

    check_command_execution(admin, as_bot)

    coro = as_bot.run_until_disconnected()
    task = as_bot.loop.create_task(coro=coro)
    # caching
    async for u in admin.iter_participants(chat):
        pass


@pytest.mark.asyncio
async def test_refresh_admins(setup, event_loop, chat, admin, user_one, user_two,
                              as_bot: PatchedTelegramClient):
    message = '!refresh_admins'
    await admin.edit_admin(
        chat,
        as_bot._self_id,
        post_messages=True, delete_messages=True, ban_users=True
    )
    await admin.send_message(chat, message=message)
    assert set([x async for x in ChatAdmins.objects.filter(chat_id=chat.id).values_list('user_id', flat=True)]) == \
           {admin._self_id, as_bot._self_id}


@pytest.mark.asyncio
async def test_ban_unban(setup, event_loop, chat, admin, user_one, user_two: PatchedTelegramClient, as_bot):
    await user_two.send_message(chat.id, message='message from user two')
    message = await admin.get_last_message(chat)

    # ban by reply
    await admin.send_message(chat.id, message='!ban', reply_to=message.id)
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) banned'

    # check user banned
    with pytest.raises(ChannelPrivateError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')

    # unban user
    await admin.send_message(chat.id, message=f'!unban #{user_two._self_id}')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) unbanned'

    # join again
    await user_two.join_to_channel(admin, chat)

    # ban by username and #id
    await admin.send_message(chat, message=f'!ban @{user_one.username} #{user_two._self_id}')

    # check user banned
    with pytest.raises(ChannelPrivateError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')
    with pytest.raises(ChannelPrivateError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} banned\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) banned'

    # unban users
    await admin.send_message(chat.id, message=f'!unban @{user_one.username} #{user_two._self_id}')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} unbanned\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) unbanned'

    # join again
    await user_two.join_to_channel(admin, chat)
    await user_one.join_to_channel(admin, chat)

    # sban user, ban without notification, delete "sban" message too
    await admin.send_message(chat, message=f'!sban @{user_one.username}')

    # check user banned
    with pytest.raises(ChannelPrivateError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # empty notification check
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} unbanned\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) unbanned'

    # unban user one
    await admin.send_message(chat, message=f'!unban @{user_one.username}')
    # join again
    await user_one.join_to_channel(admin, chat)

    await user_one.send_message(chat.id, message='user one can send message')
    assert await admin.get_last_message_text(chat=chat) == 'user one can send message'

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.BAN).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.BAN).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.UNBAN).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.UNBAN).acount() == 2


@pytest.mark.asyncio
async def test_mute_unmute(setup, event_loop, chat, admin, user_one, user_two: PatchedTelegramClient, as_bot):
    await user_two.send_message(chat.id, message='message from user two')
    message = await admin.get_last_message(chat)

    # mute by reply
    await admin.send_message(chat.id, message='!mute', reply_to=message.id)
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) muted'

    # check user muted
    with pytest.raises(ChatWriteForbiddenError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')

    # unmute user
    await admin.send_message(chat.id, message=f'!unmute #{user_two._self_id}')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) unmuted'

    # mute by username and #id
    await admin.send_message(chat, message=f'!mute @{user_one.username} #{user_two._self_id}')

    # check user banned
    with pytest.raises(ChatWriteForbiddenError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')
    with pytest.raises(ChatWriteForbiddenError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} muted\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) muted'

    # unmute users
    await admin.send_message(chat.id, message=f'!unmute @{user_one.username} #{user_two._self_id}')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} unmuted\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) unmuted'

    # smute user, ban without notification, delete "smute" message too
    await admin.send_message(chat, message=f'!smute @{user_one.username} 1d 1h 1m')

    # check user muted
    with pytest.raises(ChatWriteForbiddenError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # empty notification check
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} unmuted\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) unmuted'

    # unmute user one
    await admin.send_message(chat, message=f'!unmute @{user_one.username}')

    await user_one.send_message(chat.id, message='user one can send message')
    assert await admin.get_last_message_text(chat=chat) == 'user one can send message'

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.MUTE).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.MUTE).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.UNMUTE).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.UNMUTE).acount() == 2


@pytest.mark.asyncio
async def test_kick_unkick(setup, event_loop, chat, admin, user_one, user_two: PatchedTelegramClient, as_bot):

    await user_two.send_message(chat.id, message='message from user two before kick')
    message = await admin.get_last_message(chat)

    # kick by reply
    await admin.send_message(chat.id, message='!kick why not', reply_to=message.id)
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) kicked\nReason: why not'

    # check user kicked
    with pytest.raises(ChannelPrivateError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')

    # join again
    await user_two.join_to_channel(admin, chat)

    # kick by username and #id
    await admin.send_message(chat, message=f'!kick @{user_one.username} #{user_two._self_id}')

    # check user kicked
    with pytest.raises(ChannelPrivateError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')
    with pytest.raises(ChannelPrivateError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} kicked\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) kicked'

    # join again
    await user_one.join_to_channel(admin, chat)
    await user_two.join_to_channel(admin, chat)
    # skick user, ban without notification, delete "skick" message too
    await admin.send_message(chat, message=f'!skick @{user_one.username}')

    # check user kicked
    with pytest.raises(ChannelPrivateError):
        await user_one.send_message(chat.id, message='Try to send message, exception awaiting...')

    # empty notification check
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} kicked\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) kicked'

    #join again
    await user_one.join_to_channel(admin, chat)

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.KICK).acount() == 2

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.KICK).acount() == 2


@pytest.mark.asyncio
async def test_warn_unwarn(setup, event_loop, chat, admin, user_one, user_two: PatchedTelegramClient, as_bot):
    await UserWarn.objects.all().adelete()

    await user_two.send_message(chat.id, message='message from user two to warn')
    message = await admin.get_last_message(chat)

    # warn by reply
    await admin.send_message(chat.id, message='!warn why not', reply_to=message.id)
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) warned\nReason: why not'

    # warn by username and #id
    await admin.send_message(chat, message=f'!warn @{user_one.username} #{user_two._self_id}')

    # check bot message
    assert await admin.get_last_message_text(chat) == \
           f'User @{user_one.username} warned\nUser [{user_two._self_id}](tg://user?id={user_two._self_id}) warned'

    message = await user_two.send_message(chat.id, message='message from user two to warn third time and mute')

    # dwarn user, mute, delete user message too
    await admin.send_message(chat, message=f'!dwarn some reason', reply_to=message.id)

    # check for message was deleted
    assert await admin.get_messages(chat.id, ids=[message.id]) == [None]
    # check for mute for user two
    chat_settings = await ChatSettings.get_chat_settings(chat.id)
    assert await admin.get_last_message_text(chat) == \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) warned\n' \
           f'User [{user_two._self_id}](tg://user?id={user_two._self_id}) muted for {chat_settings.mute_period}\n' \
           f'Reason: some reason'

    # check user muted
    with pytest.raises(ChatWriteForbiddenError):
        await user_two.send_message(chat.id, message='Try to send message, exception awaiting...')

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_one._self_id, warn_type=WarnType.WARN).acount() == 1

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.WARN).acount() == 3

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id, warn_type=WarnType.MUTE).acount() == 1

    # check unwarn. Delete all history for period warn_counter_period
    await admin.send_message(chat, message=f'!unwarn #{user_two._self_id}', reply_to=message.id)

    assert await UserWarn.objects.filter(
        chat_id=chat.id, user_id=user_two._self_id).acount() == 1


@pytest.mark.asyncio
async def test_freeze_unfreeze(
        setup, event_loop, chat, admin: PatchedTelegramClient, user_one, user_two: PatchedTelegramClient, as_bot):
    await user_one.send_message(chat.id, 'Test message from user two')
    await admin.send_message(chat, message='!freeze 1m')
    assert await admin.get_last_message_text(chat) == 'Slow mode on.'
    with pytest.raises(ChatWriteForbiddenError):
        await user_two.send_message(chat.id, message='Test message for exception')

    await admin.send_message(chat, message='!unfreeze')
    assert await admin.get_last_message_text(chat) == 'Slow mode off.'
    await user_one.send_message(chat.id, message='Can I')
    await asyncio.sleep(5)
    await user_one.send_message(chat.id, message='Done')
