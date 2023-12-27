import unittest
from unittest.mock import MagicMock, AsyncMock

import pytest
import pytest_asyncio
from types import SimpleNamespace

from telethon.tl.types import PeerChat, MessageReplyHeader, ChannelParticipantAdmin, ChatAdminRights, \
    ChannelParticipantCreator

from guard_bot.bot.management.commands.start_bot import Command
from guard_bot.bot.models import ChatAdmins, UserWarn, WarnType, ChatSettings


@pytest.fixture
def not_shadow_chat_admin():
    not_shadow_admin = ChatAdmins.objects.create(user_id=1, chat_id=1)
    yield not_shadow_admin
    not_shadow_admin.delete()


@pytest.fixture
def shadow_chat_admin():
    shadow_admin = ChatAdmins.objects.create(user_id=2, chat_id=1, shadow_admin=True)
    yield shadow_admin
    shadow_admin.delete()


@pytest.fixture
def user_warn_mute():
    user_warn = UserWarn.objects.create(user_id=1, chat_id=1, warn_type=WarnType.WARN)
    yield user_warn
    user_warn.delete()


@pytest.fixture
def chat_default_settings():
    settings = ChatSettings.objects.create(chat_id=0)
    yield settings
    settings.delete()


@pytest_asyncio.fixture
async def chat_admin_can_ban():
    admin = await ChatAdmins.objects.acreate(user_id=1, chat_id=1, can_ban=True, can_delete=True)
    yield admin
    await ChatAdmins.objects.filter(id=admin.id).adelete()


@pytest_asyncio.fixture
async def chat_admin_cant_ban():
    admin = await ChatAdmins.objects.acreate(user_id=2, chat_id=1, can_ban=False)
    yield admin
    await ChatAdmins.objects.filter(id=admin.id).adelete()


@pytest_asyncio.fixture
async def another_chat_admin_cant_ban():
    admin = await ChatAdmins.objects.acreate(user_id=3, chat_id=2, can_ban=False)
    yield admin
    await ChatAdmins.objects.filter(id=admin.id).adelete()


class NestedSimpleNamespace:
    def __init__(self, /, **kwargs):
        for key in kwargs:
            if isinstance(kwargs[key], dict):
                kwargs[key] = NestedSimpleNamespace(**kwargs[key])
        self.__dict__.update(kwargs)

    def __repr__(self):
        items = (f"{k}={v!r}" for k, v in self.__dict__.items())
        return "{}({})".format(type(self).__name__, ", ".join(items))

    def __eq__(self, other):
        if isinstance(self, SimpleNamespace) and isinstance(other, SimpleNamespace):
           return self.__dict__ == other.__dict__
        return NotImplemented


@pytest_asyncio.fixture
async def iter_participants(*args, **kwargs):
    async def participants(*args, **kwargs):
        participants = [
            {'id': 3,
             'participant':
                 ChannelParticipantAdmin(
                     user_id=3,
                     admin_rights=ChatAdminRights(delete_messages=True, ban_users=False, add_admins=False),
                     promoted_by=0, date=None
                 )},
            {'id': 4,
             'participant':
                 ChannelParticipantAdmin(
                     user_id=4,
                     admin_rights=ChatAdminRights(delete_messages=True, ban_users=True, add_admins=False),
                     promoted_by=0, date=None)},
            {'id': 5,
             'participant':
                 ChannelParticipantAdmin(
                     user_id=5,
                     admin_rights=ChatAdminRights(delete_messages=False, ban_users=True, add_admins=False),
                     promoted_by=0, date=None)},
            {'id': 6,
             'participant':
                 ChannelParticipantAdmin(
                     user_id=6,
                     admin_rights=ChatAdminRights(delete_messages=False, ban_users=False, add_admins=False),
                     promoted_by=0, date=None)},
            {'id': 7,
             'participant':
                 ChannelParticipantCreator(
                     user_id=7,
                     admin_rights=ChatAdminRights(delete_messages=True, ban_users=True, add_admins=True))},
        ]

        for x in participants:
            yield NestedSimpleNamespace(**x)

    yield participants

    await ChatAdmins.objects.filter(id__in=[3, 4, 5, 6, 7]).adelete()


def dummy_message():
    event = MagicMock()
    event.message = AsyncMock()
    event.message.text = '!test_command'
    event.message.from_id = 1
    event.message.chat = MagicMock()
    event.message.chat.id = 1
    event.message.sender = MagicMock()
    event.message.sender.id = 1
    return event


@pytest.fixture
def message_event():
    event = dummy_message()
    event.message.is_reply = False
    yield event
    del event


@pytest.fixture
def patched_command():
    with unittest.mock.patch('guard_bot.bot.management.commands.start_bot.TelegramClient'):
        com = Command()
        com.client = AsyncMock()
        yield com

        del com


@pytest.fixture
def reply_event():
    event = dummy_message()
    event.chat = PeerChat(chat_id=1)
    event.reply_to = MessageReplyHeader(reply_to_msg_id=1)
    event.message = AsyncMock()
    event.message.reply_to = MessageReplyHeader(reply_to_msg_id=1)
    event.message.chat = MagicMock()
    event.message.chat.id = 1
    event.message.sender = MagicMock()
    event.message.sender.id = 1
    yield event

    del event


@pytest.fixture
def parsed_message():
    message = {
        'users': None,
        'chat_id': 1,
        'mute': True,
        'undo': False,
        'days': 1,
        'hours': 2,
        'minutes': 3,
        'comment': 'comment',
    }

    yield message

    del message


@pytest.fixture
def parsed_ban_message():
    message = {
        'users': ['123', '456'],
        'chat_id': 1,
        'mute': False,
        'comment': 'comment',
        'command': 'ban'
    }

    yield message

    del message


@pytest.fixture
def parsed_mute_message():
    message = {
        'users': ['123', '456'],
        'chat_id': 1,
        'comment': 'comment',
        'command': 'mute',
        'days': '1',
        'hours': '2',
        'minutes': '3',
    }

    yield message

    del message


@pytest.fixture
def parsed_perm_on_message():
    message = {
        'users': [],
        'chat_id': 1,
        'comment': 'comment',
        'command': 'on',
        'perms': ['message', 'media', 'sticker', 'gif', 'game', 'inline', 'link', 'poll', 'invite']
    }

    yield message

    del message


@pytest_asyncio.fixture
async def chat_admin_can_refresh():
    admin = await ChatAdmins.objects.acreate(user_id=1, chat_id=1, can_ban=True, can_delete=True, can_add_admin=True)
    yield admin
    await ChatAdmins.objects.filter(id=admin.id).adelete()
