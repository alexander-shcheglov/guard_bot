import re
import unittest.mock
from collections import OrderedDict
from unittest.mock import MagicMock, AsyncMock, call
import pytest
from telethon import types
from telethon.errors import UserAdminInvalidError, ChatAdminRequiredError, UserIdInvalidError, SecondsInvalidError

from guard_bot.bot.management.commands.start_bot import TG_USER, DOG_USER, SHARP_USER, COMMAND, HOURS, MINUTES, DAYS, \
    USERS_LIST, PERIOD, USERS, USERS_AND_PERIOD, SLOW_MODE_VALUES, attr_setter, admin_check, Command, get_command, \
    get_user_name, get_id_from_entity, Lock
from guard_bot.bot.models import ChatAdmins, UserWarn, WarnType, ChatSettings

USERS_TXT_TEST = '@dog_user1 #12345678 [tg_user](tg://user?id=34535433) 1111112333 1233456gt comment'
COMMAND_TXT_TEST = '!command ' + USERS_TXT_TEST
HOURS_TXT_TEST = '6h 7hr'
MINUTES_TXT_TEST = '34m 45min'
DAYS_TXT_TEST = '4d 5days'
USERS_LIST_TEST = [
        re.compile(r'\[[^\]]*\]\(tg\:\/+\w+\?id=(\d+)\)', re.I),
        re.compile(r'(@\w+)', re.I),
        re.compile(r'#(\d+)', re.I)
    ]
PERIOD_TEST = [
        ('hours', re.compile(r'(\d+)(hr|h)+', re.I)),
        ('minutes', re.compile(r'(\d+)(min|m)+', re.I)),
        ('days', re.compile(r'(\d+)(days|d)+', re.I)),
    ]
COMMAND_TEST = re.compile(r'!(\w+)', re.I)

USERS_AND_PERIOD_TEST = OrderedDict({
        'command': COMMAND_TEST,
        'users': USERS_LIST_TEST,
        'period': PERIOD_TEST
        })

pytestmark = pytest.mark.django_db(transaction=True)


def test_tg_user():
    assert TG_USER.findall(USERS_TXT_TEST) == ['34535433']


def test_dog_user():
    assert DOG_USER.findall(USERS_TXT_TEST) == ['@dog_user1']


def test_sharp_user():
    assert SHARP_USER.findall(USERS_TXT_TEST) == ['12345678']


def test_command():
    assert COMMAND.findall(COMMAND_TXT_TEST) == ['command']


def test_hours():
    assert HOURS.findall(HOURS_TXT_TEST) == [('6', 'h'), ('7', 'hr')]


def test_minutes():
    assert MINUTES.findall(MINUTES_TXT_TEST) == [('34', 'm'), ('45', 'min')]


def test_days():
    assert DAYS.findall(DAYS_TXT_TEST) == [('4', 'd'), ('5', 'days')]


def test_users_list():
    assert USERS_LIST == USERS_LIST_TEST


def test_period():
    assert PERIOD == PERIOD_TEST


def test_users():
    assert USERS == OrderedDict({
        'command': COMMAND_TEST,
        'users': USERS_LIST_TEST
        }
    )


def test_users_and_period():
    assert USERS_AND_PERIOD == USERS_AND_PERIOD_TEST


def test_slow_mode_values():
    assert SLOW_MODE_VALUES == [0, 10, 30, 60, 300, 900, 3600]


@pytest.mark.asyncio
async def test_attr_setter():
    message_text = '!command @dog_user1 #12345678 [tg_user](tg://user?id=34535433)' \
                   ' 1d 2h 3m 1111112333 1233456gt comment'

    @attr_setter(attrs=USERS_AND_PERIOD_TEST)
    async def test_async_function(self, *args, **kwargs):
        assert self.self == 'self'
        assert args[0].message.chat.id == 1
        assert kwargs['chat_id'] == 1
        assert kwargs['command'] == 'command'
        assert kwargs['users'] == ['@dog_user1', '12345678', '34535433']
        assert kwargs['days'] == '1'
        assert kwargs['minutes'] == '3'
        assert kwargs['hours'] == '2'

    dummy_self = MagicMock()
    dummy_self.self = 'self'

    event = MagicMock()
    event.message.text = message_text
    event.message.chat.id = 1
    await test_async_function(dummy_self, event)


@pytest.mark.asyncio
async def test_admin_check(chat_admin_can_ban, chat_admin_cant_ban):

    @admin_check('can_ban')
    async def test_async_function(self, *args, **kwargs):
        return True
    dummy_self = MagicMock()
    dummy_self.self = 'self'
    event = MagicMock()
    event.message.chat.id = 1
    event.message.sender.id = 1
    another_event = MagicMock()
    another_event.message.chat.id = 2
    another_event.message.sender.id = 2

    assert await test_async_function(dummy_self, event) is True
    assert await test_async_function(dummy_self, another_event) is None


@pytest.mark.asyncio
async def test_admin_check_for_first_sync(iter_participants):

    @admin_check('can_add_admin')
    async def test_async_function(self, *args, **kwargs):
        return True
    dummy_self = MagicMock()
    dummy_self.self = 'self'
    dummy_self.client = AsyncMock()
    dummy_self.client.iter_participants = iter_participants
    dummy_self.groups_memset = set()

    creator_event = MagicMock()
    creator_event.message.chat.id = 1
    creator_event.message.sender.id = 7

    assert await test_async_function(dummy_self, creator_event) is True


@pytest.mark.asyncio
async def test_handle(event_loop):
    original_handle = Command.handle
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Command') as patched_command:
        patched_object = patched_command()
        patched_object.handle = original_handle
        patched_object.handle(patched_object)
        assert patched_object.loop.create_task.call_count == 2
        assert patched_object.loop.create_task.call_args_list == [
            call(patched_object.get_me(), name='get_me'),
            call(patched_object.refresh_admins_task(), name='refresh_admins'),
        ]
        assert patched_object.refresh_admins_task.call_count == 2
        assert patched_object.refresh_admins_task.call_args_list == [call(), call()]
        assert patched_object.set_events.call_count == 1
        assert patched_object.client.run_until_disconnected.call_count == 1


@pytest.mark.asyncio
async def test_get_me(event_loop):
    original_get_me = Command.get_me
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Command', new=AsyncMock) as patched_command:
        patched_object = patched_command()
        patched_object.get_me = original_get_me
        await patched_object.get_me(patched_object)
        assert patched_object.client.get_me.call_count == 1
        assert patched_object.me == await patched_object.client.get_me()


@pytest.mark.asyncio
async def test_refresh_admins_for_chat(chat_admin_can_ban, chat_admin_cant_ban, iter_participants, caplog):
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Command.__init__', return_value=None):
        com = Command()
        com.client = AsyncMock()
        com.client.iter_participants = iter_participants
        com.groups_memset = set()

        chat_id = 1
        chat_admins = await ChatAdmins.get_admins_by_chat(chat_id=chat_id)
        await com.refresh_admins_for_chat(chat_id=1, db_admins=chat_admins[chat_id])
        qs = ChatAdmins.objects.filter(chat_id=chat_id)
        assert await qs.acount() == 5
        assert [x async for x in qs.values_list('user_id', flat=True)] == [3, 4, 5, 6, 7]
        assert [x async for x in qs.filter(can_ban=True).values_list('user_id', flat=True)] == [4, 5, 7]
        assert [x async for x in qs.filter(can_delete=True).values_list('user_id', flat=True)] == [3, 4, 7]
        assert [x async for x in qs.filter(can_add_admin=True).values_list('user_id', flat=True)] == [7]

        class PatchedLock(Lock):
            async def __aenter__(self):
                locked = await self._acquire_lock()
                if locked:
                    return self
                raise Exception("Patched for test")

        with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Lock', PatchedLock):
            async with Lock(com.groups_memset, obj_id=chat_id):
                with pytest.raises(Exception, match='Patched for test'):
                    await com.refresh_admins_for_chat(chat_id=1, db_admins=chat_admins[chat_id])
        async with Lock(com.groups_memset, obj_id=chat_id):
            await com.refresh_admins_for_chat(chat_id=1, db_admins=chat_admins[chat_id])
            assert f"Reloading admins for chat {chat_id}. Already locked by another coroutine" in caplog.messages


@pytest.mark.asyncio
async def test__refresh_admins_task(chat_admin_can_ban, chat_admin_cant_ban, another_chat_admin_cant_ban, settings):
    settings.ADMIN_GROUPS_REFRESH_PERIOD = 0
    settings.BETWEEN_GROUPS_REFRESH_COOLDOWN = 0
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Command.__init__', return_value=None):
        with unittest.mock.patch(
                'guard_bot.bot.management.commands.start_bot.Command.refresh_admins_for_chat') as mock:
            com = Command()
            await com._refresh_admins_task()
            assert mock.call_count == 2
            assert mock.call_args_list == [call(1, {1, 2}), call(2, {3})]


@pytest.mark.asyncio
async def test_refresh_admins_task():
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.Command.__init__', return_value=None):
        with unittest.mock.patch(
                'guard_bot.bot.management.commands.start_bot.Command._refresh_admins_task',
                side_effect=Exception('Done')) as mock:
            com = Command()
            with pytest.raises(Exception, match='Done'):
                await com.refresh_admins_task()


def test__init__(settings):
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.TelegramClient') as client:
        com = Command()
        assert com.me is None
        assert client.call_count == 1
        assert client.mock_calls[:2] == [
            call(settings.BOT_DB, settings.API_ID, settings.API_HASH), call().start(bot_token=settings.BOT_TOKEN)]
        assert com.loop == com.client.loop


@pytest.mark.asyncio
async def test_get_me(patched_command):
    patched_command.client = AsyncMock()
    assert patched_command.me is None
    await patched_command.get_me()
    assert patched_command.client.get_me.call_count == 1
    assert patched_command.me == await patched_command.client.get_me()


def test_set_events(patched_command):
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.events'):
        from guard_bot.bot.management.commands.start_bot import events
        patched_command = Command()
        patched_command.client = MagicMock()
        patched_command.set_events()
        assert patched_command.client.add_event_handler.call_count == 2
        assert patched_command.client.add_event_handler.call_args_list == [
            call(patched_command.on_new_message, events.NewMessage(incoming=True)),
            call(patched_command.on_edit_message, events.MessageEdited(incoming=True)),
        ]


def test_get_command():
    assert get_command('!run baby run') == 'run'
    assert get_command('! run baby run') == ''
    assert get_command('run baby run') == 'un'


@pytest.mark.asyncio
async def test_run_command(message_event, patched_command):
    patched_command.test_command = AsyncMock()
    await patched_command.run_command(message_event)
    assert patched_command.test_command.call_count == 1
    assert patched_command.test_command.call_args_list == [call(message_event)]

    message_event.message.text = '!not_existing_command'
    await patched_command.run_command(message_event)
    assert message_event.message.reply.call_count == 1
    assert message_event.message.reply.call_args_list == [call('wat?')]


@pytest.mark.asyncio
async def test_spam_check(patched_command):
    assert await patched_command.spam_check(None) is None


@pytest.mark.asyncio
async def test_on_new_message(message_event, patched_command):
    patched_command.run_command, patched_command.spam_check = AsyncMock(), AsyncMock()
    await patched_command.on_new_message(message_event)
    assert patched_command.run_command.call_count == 1
    assert patched_command.run_command.call_args_list == [call(message_event)]

    message_event.message.text = 'not command'
    await patched_command.on_new_message(message_event)
    assert patched_command.spam_check.call_count == 1
    assert patched_command.spam_check.call_args_list == [call(message_event)]


@pytest.mark.asyncio
async def test_on_edit_message(message_event, patched_command):
    patched_command.spam_check = AsyncMock()
    await patched_command.on_edit_message(message_event)
    assert patched_command.spam_check.call_count == 1
    assert patched_command.spam_check.call_args_list == [call(message_event)]


def test_get_user_name():
    user_id = 123
    user = types.PeerUser(user_id=user_id)
    assert get_user_name(user) == f'[{user_id}](tg://user?id={user_id})'
    assert get_user_name('123') == f'[{123}](tg://user?id={123})'
    assert get_user_name('@123') == '@123'


@pytest.mark.asyncio
async def test__get_users(message_event, reply_event, patched_command):
    async def get_messages(chat_id, ids: int = None):
        message = MagicMock()
        message.from_id = 3
        return message
    patched_command.client.get_messages = get_messages
    assert await patched_command._get_users(message_event, ['123', '@dummy_user']) == ['123', '@dummy_user']
    assert await patched_command._get_users(message_event, '123') == ['123']
    assert await patched_command._get_users(reply_event, None) == [3]


def test_get_id_from_entity(patched_command):
    assert get_id_from_entity('1') == 1
    assert get_id_from_entity(types.InputPeerChat(chat_id=2)) == 2
    assert get_id_from_entity(types.InputPeerChannel(channel_id=3, access_hash=0)) == 3
    assert get_id_from_entity(types.InputPeerUser(user_id=4, access_hash=0)) == 4
    with pytest.raises(ValueError, match='Can`t find entity ID'):
        get_id_from_entity(0)


@pytest.mark.asyncio
async def test_get_user_id(patched_command):
    async def get_input_entity(entity):
        return entity
    patched_command.client.get_input_entity = get_input_entity
    assert await patched_command.get_user_id('123') == 123
    assert await patched_command.get_user_id(types.InputPeerChat(chat_id=4)) == 4


def exc():
    exceptions = (UserAdminInvalidError, ChatAdminRequiredError, UserIdInvalidError)
    for exception in exceptions:
        yield exception


@pytest.mark.asyncio
async def test__mute_or_ban(patched_command, message_event, parsed_message):

    assert await patched_command._mute_or_ban(message_event, **parsed_message) == ''
    parsed_message['users'] = ['123', '456']
    assert await patched_command._mute_or_ban(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) muted on 1 day, 2:03:00\n' \
           'User [456](tg://user?id=456) muted on 1 day, 2:03:00\n' \
           'Reason: comment'
    parsed_message['mute'] = False
    assert await patched_command._mute_or_ban(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) banned on 1 day, 2:03:00\n' \
           'User [456](tg://user?id=456) banned on 1 day, 2:03:00\n' \
           'Reason: comment'
    parsed_message['undo'] = True
    assert await patched_command._mute_or_ban(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) unbanned on 1 day, 2:03:00\n' \
           'User [456](tg://user?id=456) unbanned on 1 day, 2:03:00\n' \
           'Reason: comment'

    parsed_message['mute'] = True
    assert await patched_command._mute_or_ban(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) unmuted on 1 day, 2:03:00\n' \
           'User [456](tg://user?id=456) unmuted on 1 day, 2:03:00\n' \
           'Reason: comment'

    assert message_event.message.delete.call_count == 4



    exc_generator = exc()

    async def raise_exceptions(*args, **kwargs):
        raise next(exc_generator)('')

    parsed_message['users'].append('789')
    patched_command.client.edit_permissions = raise_exceptions
    assert await patched_command._mute_or_ban(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) not unmuted\n' \
           'User [456](tg://user?id=456) not unmuted\n' \
           'User [789](tg://user?id=789) not unmuted\n' \
           'Reason: comment'


@pytest.mark.asyncio
async def test_ban(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!ban #123 #456 comment'
    await patched_command.ban(message_event)
    result = 'User [123](tg://user?id=123) banned\n' \
             'User [456](tg://user?id=456) banned\n' \
             'Reason: comment'
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message=result)


@pytest.mark.asyncio
async def test_sban(patched_command, message_event, chat_admin_can_ban, parsed_ban_message):
    message_event.message.text = '!sban #123 #456 comment'
    patched_command._mute_or_ban = AsyncMock()
    await patched_command.sban(message_event)
    parsed_ban_message['command'] = 'sban'
    assert patched_command._mute_or_ban.call_args == call(message_event, **parsed_ban_message)


@pytest.mark.asyncio
async def test_unban(patched_command, message_event, chat_admin_can_ban, parsed_ban_message):
    message_event.message.text = '!unban #123 #456 comment'
    patched_command._mute_or_ban = AsyncMock()
    await patched_command.unban(message_event)
    parsed_ban_message['command'] = 'unban'
    parsed_ban_message['undo'] = True
    assert patched_command._mute_or_ban.call_args == call(message_event, **parsed_ban_message)


@pytest.mark.asyncio
async def test_mute(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!mute #123 #456 1d 2h 3m comment'
    await patched_command.mute(message_event)
    result = 'User [123](tg://user?id=123) muted on 1 day, 2:03:00\n' \
             'User [456](tg://user?id=456) muted on 1 day, 2:03:00\n' \
             'Reason: comment'
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message=result)


@pytest.mark.asyncio
async def test_smute(patched_command, message_event, chat_admin_can_ban, parsed_mute_message):
    message_event.message.text = '!smute #123 #456 1d 2h 3m comment'
    patched_command._mute_or_ban = AsyncMock()
    await patched_command.smute(message_event)
    parsed_mute_message['command'] = 'smute'
    assert patched_command._mute_or_ban.call_args == call(message_event, **parsed_mute_message)


@pytest.mark.asyncio
async def test_unmute(patched_command, message_event, chat_admin_can_ban, parsed_mute_message):
    message_event.message.text = '!unmute #123 #456 comment'
    await patched_command.unmute(message_event)
    result = 'User [123](tg://user?id=123) unmuted\n' \
             'User [456](tg://user?id=456) unmuted\n' \
             'Reason: comment'
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message=result)


@pytest.mark.asyncio
async def test__kick(patched_command, parsed_message, message_event):
    assert await patched_command._kick(message_event, **parsed_message) == ''

    parsed_message['users'] = ['123', '456']

    assert await patched_command._kick(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) kicked\nUser [456](tg://user?id=456) kicked\nReason: comment'
    assert await UserWarn.objects.filter(
        chat_id=parsed_message['chat_id'], user_id=123, warn_type=WarnType.KICK).acount() == 1
    assert await UserWarn.objects.filter(
        chat_id=parsed_message['chat_id'], user_id=456, warn_type=WarnType.KICK).acount() == 1
    assert message_event.message.delete.call_count == 1

    exc_generator = exc()

    async def raise_exceptions(*args, **kwargs):
        raise next(exc_generator)('')

    parsed_message['users'].append('789')
    patched_command.client.kick_participant = raise_exceptions
    assert await patched_command._kick(message_event, **parsed_message) == \
           'User [123](tg://user?id=123) not kicked\n' \
           'User [456](tg://user?id=456) not kicked\n' \
           'User [789](tg://user?id=789) not kicked\n' \
           'Reason: comment'


@pytest.mark.asyncio
async def test_kick(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!kick #123 #456 comment'
    await patched_command.kick(message_event)
    assert patched_command.client.send_message.call_count == 1
    result = \
        'User [123](tg://user?id=123) kicked\n' \
        'User [456](tg://user?id=456) kicked\n' \
        'Reason: comment'
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message=result)


@pytest.mark.asyncio
async def test_skick(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!kick #123 #456 comment'
    await patched_command.skick(message_event)
    assert patched_command.client.kick_participant.call_count == 2
    assert patched_command.client.kick_participant.call_args_list == [
        call(message_event.message.chat.id, 123),
        call(message_event.message.chat.id, 456),
    ]


@pytest.mark.asyncio
async def test__warn(patched_command, message_event, chat_admin_can_ban):
    assert await patched_command._warn(message_event, message_event.message.chat.id, users=[], comment='comment') == ''
    result = await patched_command._warn(
        message_event, message_event.message.chat.id, users=['123', '456'], comment='comment')
    assert result == \
           'User [123](tg://user?id=123) warned\n' \
           'User [456](tg://user?id=456) warned\n' \
           'Reason: comment'
    chat_settings = await ChatSettings.get_chat_settings(message_event.message.chat.id)
    for i in range(chat_settings.warn_count):
        result = await patched_command._warn(
            message_event, message_event.message.chat.id, users=['123', '456'], comment='comment')

    assert await UserWarn.objects.filter(
                chat_id=message_event.message.chat.id, user_id=123, warn_type=WarnType.WARN, comment='comment'
    ).acount() == chat_settings.warn_count + 1
    assert await UserWarn.objects.filter(
                chat_id=message_event.message.chat.id, user_id=456, warn_type=WarnType.WARN, comment='comment'
    ).acount() == chat_settings.warn_count + 1
    assert await UserWarn.objects.filter(
                chat_id=message_event.message.chat.id, user_id=123, warn_type=WarnType.MUTE, comment='comment'
    ).acount() == 2
    assert await UserWarn.objects.filter(
                chat_id=message_event.message.chat.id, user_id=456, warn_type=WarnType.MUTE, comment='comment'
    ).acount() == 2

    assert patched_command.client.edit_permissions.call_count == 4
    assert patched_command.client.edit_permissions.call_args_list == [
        call(message_event.message.chat.id, 123, until_date=chat_settings.mute_period, send_messages=False),
        call(message_event.message.chat.id, 456, until_date=chat_settings.mute_period, send_messages=False)
    ] * 2
    assert result == \
           'User [123](tg://user?id=123) warned\n' \
           'User [123](tg://user?id=123) muted for 1 day, 0:00:00\n' \
           'User [456](tg://user?id=456) warned\n' \
           'User [456](tg://user?id=456) muted for 1 day, 0:00:00\n' \
           'Reason: comment'

    exc_generator = exc()

    async def raise_exceptions(*args, **kwargs):
        raise next(exc_generator)('')

    patched_command.client.edit_permissions = raise_exceptions
    result = await patched_command._warn(
        message_event, message_event.message.chat.id, users=['123', '456', '789'], comment='comment')

    assert result == \
           'User [123](tg://user?id=123) warned\n' \
           'User [123](tg://user?id=123) NOT muted for 1 day, 0:00:00\n' \
           'User [456](tg://user?id=456) warned\n' \
           'User [456](tg://user?id=456) NOT muted for 1 day, 0:00:00\n' \
           'User [789](tg://user?id=789) warned\n' \
           'Reason: comment'

    assert message_event.message.delete.call_count == chat_settings.warn_count + 2


@pytest.mark.asyncio
async def test_warn(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!warn #123 #456 comment'
    await patched_command.warn(message_event)
    assert patched_command.client.send_message.call_args == call(
        message_event.message.chat.id,
        message='User [123](tg://user?id=123) warned\nUser [456](tg://user?id=456) warned\nReason: comment'
    )


@pytest.mark.asyncio
async def test_dwarn(patched_command, message_event, reply_event, chat_admin_can_ban):
    message_event.message.text = '!dwarn #123 #456 comment'

    assert await patched_command.dwarn(message_event) is None

    async def get_messages(*args, **kwargs):
        result = MagicMock()
        result.from_id = '123'
        return result

    patched_command.client.get_messages = get_messages
    reply_event.message.text = '!dwarn comment'

    await patched_command.dwarn(reply_event)

    assert patched_command.client.delete_messages.call_args == call(
        reply_event.message.chat.id, message_ids=reply_event.message.reply_to.reply_to_msg_id)

    assert patched_command.client.send_message.call_args == call(
        message_event.message.chat.id,
        message='User [123](tg://user?id=123) warned\nReason: comment'
    )


@pytest.mark.asyncio
async def test_unwarn(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!unwarn comment'
    assert await patched_command.unwarn(message_event) is None

    message_event.message.text = '!warn #123 #456 warn'
    await patched_command.warn(message_event)
    assert await UserWarn.objects.filter(
        chat_id=message_event.message.chat.id, user_id=123, comment='warn').acount() == 1
    assert await UserWarn.objects.filter(
        chat_id=message_event.message.chat.id, user_id=456, comment='warn').acount() == 1

    message_event.message.text = '!unwarn #123 unwarn'
    await patched_command.unwarn(message_event)

    assert await UserWarn.objects.filter(
        chat_id=message_event.message.chat.id, user_id=123, comment='warn').acount() == 0
    assert await UserWarn.objects.filter(
        chat_id=message_event.message.chat.id, user_id=456, comment='warn').acount() == 1
    assert patched_command.client.send_message.call_args == call(
        message_event.message.chat.id,
        message='User warnings was delete for [123](tg://user?id=123). Current count: 0\nReason: unwarn'
    )


@pytest.mark.asyncio
async def test_spam(patched_command, message_event):
    assert await patched_command.spam(message_event) is None


@pytest.mark.asyncio
async def test__freeze(patched_command, message_event):
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.ToggleSlowModeRequest') as request:
        await patched_command._freeze(message_event.message.chat.id)
        await patched_command._freeze(message_event.message.chat.id, minutes=2)
        await patched_command._freeze(message_event.message.chat.id, minutes=6)
        await patched_command._freeze(message_event.message.chat.id, hours=1)
        assert request.call_args_list == [
            call(channel=message_event.message.chat.id, seconds=0),
            call(channel=message_event.message.chat.id, seconds=60),
            call(channel=message_event.message.chat.id, seconds=300),
            call(channel=message_event.message.chat.id, seconds=3600)
        ]


@pytest.mark.asyncio
async def test_freeze(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!freeze 1h'

    await patched_command.freeze(message_event)
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message='Slow mode on.')

    with unittest.mock.patch(
            'guard_bot.bot.management.commands.start_bot.ToggleSlowModeRequest', side_effect=SecondsInvalidError('Hoho')
    ):
        await patched_command.freeze(message_event)
        assert patched_command.client.call_count == 1


@pytest.mark.asyncio
async def test_unfreeze(patched_command, message_event, chat_admin_can_ban):
    message_event.message.text = '!unfreeze'

    await patched_command.unfreeze(message_event)
    assert patched_command.client.send_message.call_args == call(message_event.message.chat.id, message='Slow mode off.')

    with unittest.mock.patch(
            'guard_bot.bot.management.commands.start_bot.ToggleSlowModeRequest', side_effect=SecondsInvalidError('Hoho')
    ):
        await patched_command.unfreeze(message_event)
        assert patched_command.client.call_count == 1


@pytest.mark.asyncio
async def test_refresh_admins(patched_command, message_event, chat_admin_can_refresh, another_chat_admin_cant_ban):
    patched_command.refresh_admins_for_chat = AsyncMock()
    await patched_command.refresh_admins(message_event)

    assert patched_command.refresh_admins_for_chat.call_args == call(message_event.message.chat.id, {1})

    message_event.message.chat.id = 2

    await patched_command.refresh_admins(message_event)

    assert patched_command.refresh_admins_for_chat.call_count == 1
