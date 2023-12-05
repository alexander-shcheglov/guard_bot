import asyncio
import random
import uuid

import pytest
import pytest_asyncio
from django.core.management import BaseCommand
from telethon import TelegramClient
from telethon.errors import PhoneNumberUnoccupiedError, SessionPasswordNeededError, InviteHashExpiredError, \
    FloodWaitError
from telethon.sessions import MemorySession
from django.conf import settings
from telethon.tl.functions.account import UpdateUsernameRequest
from telethon.tl.functions.channels import DeleteChannelRequest
from telethon.tl.functions.messages import CreateChatRequest, ExportChatInviteRequest, \
    ImportChatInviteRequest, MigrateChatRequest
from telethon.tl.patched import MessageService

from guard_bot.bot.management.commands.start_bot import Command


class PatchedTelegramClient(TelegramClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, flood_sleep_threshold=10,  **kwargs)
        self.last_commands = []

    async def range(self, count, delay):
        for i in range(count):
            yield i
            await asyncio.sleep(delay)

    async def run_until_command_complete(self, command: str):
        async for i in self.range(10000, 0.1):
            if i % 100 == 0:
                await self.catch_up()
            if self.last_commands and self.last_commands[-1] == command:
                self.last_commands.clear()
                return
        raise Exception('Cant wait anymore')

    async def get_invite_link(self, channel):
        result = await self(ExportChatInviteRequest(channel, usage_limit=1000))
        return result.link.lstrip('https://t.me/+')

    async def join_to_channel(self, admin, channel):
        while True:
            try:
                link = await admin.get_invite_link(channel)
                await self(ImportChatInviteRequest(hash=link))
                break
            except InviteHashExpiredError:
                await asyncio.sleep(1)
            except FloodWaitError as e:
                print(f'Flood wait error sleep {e.seconds} seconds')
                await asyncio.sleep(e.seconds)

    async def get_last_message(self, chat):
        await asyncio.sleep(1)
        message, *_ = filter(lambda x: not isinstance(x, MessageService), await self.get_messages(chat.id, limit=10))
        return message

    async def get_last_message_text(self, chat):
        message = await self.get_last_message(chat)
        return message.text


class PatchedCommand(Command):
    def __init__(self, *args, **kwargs):
        super(BaseCommand).__init__(*args, **kwargs)
        self.me = None

    async def set_user(self):
        self.client = await get_telegram_user()
        self.loop = self.client.loop
        self.set_events()

    async def run_command(self, event):
        command = event.message.text
        await super().run_command(event)
        self.client.last_commands.append(command)


async def get_telegram_user():
    ms = MemorySession()
    ms.set_dc(dc_id=settings.TEST_DC, server_address=settings.TEST_SERVER, port=settings.TEST_PORT)
    client = PatchedTelegramClient(
        session=ms,
        api_id=settings.API_ID,
        api_hash=settings.API_HASH
    )
    for i in range(0, 10):
        try:
            if not client.is_connected():
                await client.connect()
            login = f'99966{settings.TEST_DC}{random.randint(0, 9999):04d}'
            await client.sign_in(login)
            await client.sign_in(code=str(settings.TEST_DC) * 5)
            # to prevent flood wait exception
            await asyncio.sleep(1)
            return client
        except (PhoneNumberUnoccupiedError, SessionPasswordNeededError):
            pass
        except FloodWaitError as e:
            print(f'Flood wait error sleep {e.seconds} seconds')
            await asyncio.sleep(e.seconds)


@pytest_asyncio.fixture(scope='module')
async def admin():
    user = await get_telegram_user()
    yield user
    if user.is_connected():
        await user.disconnect()


@pytest_asyncio.fixture(scope='module')
async def user_one():
    user = await get_telegram_user()
    username = f'%012x' % uuid.uuid4().node
    if username[0].isdigit():
        username = 'a' + username
    await user(UpdateUsernameRequest(username=username))
    setattr(user, 'username', username)
    yield user
    if user.is_connected():
        await user.disconnect()


@pytest_asyncio.fixture(scope='module')
async def user_two():
    user = await get_telegram_user()
    yield user
    if user.is_connected():
        await user.disconnect()


@pytest_asyncio.fixture(scope='module')
async def as_bot():
    command = PatchedCommand()
    await command.set_user()
    user = command.client
    yield user
    if user.is_connected():
        await user.disconnect()


@pytest_asyncio.fixture(scope='module')
async def chat(admin):
    result = await admin(
        CreateChatRequest(
            users=[], title=f'{uuid.uuid4()}')
    )
    result = await admin(MigrateChatRequest(chat_id=result.chats[0].id))
    yield result.chats[2]

    result = await admin(DeleteChannelRequest(
        channel=result.chats[2]
    ))


@pytest.fixture(scope="module")
def event_loop():
    """Overrides pytest default function scoped event loop"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()



