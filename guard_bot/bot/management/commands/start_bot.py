import asyncio
import logging
import re
import typing

from collections import OrderedDict
from datetime import timedelta
from functools import wraps

from guard_bot.bot.messages import (
    WRONG_COMMAND,
    UNMUTED,
    MUTED,
    UNBANNED,
    BANNED,
    RESULT_MESSAGE,
    RESULT_ERROR_MESSAGE,
    REASON,
    RESULT_KICK_MESSAGE,
    ERROR_KICK_MESSAGE,
    USER_WARNED,
    USER_MUTED,
    USER_NOT_MUTED,
    USER_WARN_DELETED,
    SLOW_MODE_ON,
    SLOW_MODE_OFF,
)

if typing.TYPE_CHECKING:
    from typing import Union, List, Tuple
    from telethon import hints


from django.core.management.base import BaseCommand
from django.conf import settings

from telethon import TelegramClient, events
from telethon.errors import (
    UserAdminInvalidError,
    ChatAdminRequiredError,
    UserIdInvalidError,
    SecondsInvalidError,
)
from telethon import types
from telethon.tl.functions.channels import ToggleSlowModeRequest
from telethon.tl.types import (
    ChannelParticipantsAdmins,
    PeerUser,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
)

from guard_bot.bot.models import ChatAdmins, UserWarn, WarnType

logger = logging.getLogger("asyncio")

TG_USER = re.compile(r"\[[^\]]*\]\(tg\:\/+\w+\?id=(\d+)\)", re.I)
DOG_USER = re.compile(r"(@\w+)", re.I)
SHARP_USER = re.compile(r"#(\d+)", re.I)
COMMAND = re.compile(r"!(\w+)", re.I)
HOURS = re.compile(r"(\d+)(hr|h)+", re.I)
MINUTES = re.compile(r"(\d+)(min|m)+", re.I)
DAYS = re.compile(r"(\d+)(days|d)+", re.I)


USERS_LIST = [TG_USER, DOG_USER, SHARP_USER]
PERIOD = [("hours", HOURS), ("minutes", MINUTES), ("days", DAYS)]

USERS = OrderedDict({"command": COMMAND, "users": USERS_LIST})
USERS_AND_PERIOD = OrderedDict(
    {"command": COMMAND, "users": USERS_LIST, "period": PERIOD}
)

SLOW_MODE_VALUES = [0, 10, 30, 60, 60 * 5, 60 * 15, 60 * 60]


def attr_setter(attrs: OrderedDict = None):
    """
    Decorator for bot command method.
    Extracts attrs from event by "attr_getter" function,
    add attr "chat_id" and call bot method with attrs
    :param attrs: OrderedDict
    :return: object
    """
    """attrib_setter(params={'attr_name1': [TG_USER, DOG_USER, SHARP_USER]})"""

    def decorator(method):
        @wraps(method)
        async def _impl(self, event, *args, **kwargs):
            params = attr_getter(event.message.text, attrs)
            kwargs.update(params)
            kwargs.update({"chat_id": event.message.chat.id})
            return await method(self, event, *args, **kwargs)

        return _impl

    return decorator


def admin_check(can_do: str):
    """
    Decorator for check user rights, set "is_chat_command" flag to decorated method.

    :param can_do: str, 'can_add_admin|can_ban|can_delete', see guard_bot.bot.models.ChatAdmins
    :return: object
    """

    def decorator(method):
        @wraps(method)
        async def _impl(self, event, *args, **kwargs):
            admin = None
            if not await ChatAdmins.objects.filter(
                chat_id=event.message.chat.id
            ).aexists():
                # maybe new, not cached chat
                async for u in self.client.iter_participants(
                    event.message.chat.id, filter=ChannelParticipantsAdmins
                ):
                    if u.id == event.message.sender.id and (
                        isinstance(u.participant, ChannelParticipantAdmin)
                        and u.participant.admin_rights.add_admins
                        or isinstance(u.participant, ChannelParticipantCreator)
                    ):
                        admin = u
                        setattr(admin, "can_add_admin", True)
                        break
            else:
                admin = await ChatAdmins.objects.filter(
                    chat_id=event.message.chat.id, user_id=event.message.sender.id
                ).afirst()
            if admin and getattr(admin, can_do, False):
                return await method(self, event, *args, **kwargs)
            return

        setattr(_impl, "is_chat_command", True)
        return _impl

    return decorator


def attr_getter(s: str, c: OrderedDict) -> dict:
    """
    Get attributes from given string by rules from ordered dict
    Uses by "attr_setter" decorator for bot command to throw attrs in method
    :param s: str, example !ban @user #1234 some reason
    :param c: OrderedDict, example OrderedDict({'command': COMMAND, 'users': USERS_LIST})
    :return: dict, example {'command': 'ban', 'users':['@user', '#1234'], 'comment': 'some reason'}
    """
    result = {}
    for k, value in c.items():
        if not isinstance(value, list):
            match = value.match(s)
            if match:
                result.update({k: match.groups()[0]})
                s = s[match.span()[1] :]
        else:
            while True:
                match = None
                for el in value:
                    attr_name = None
                    if isinstance(el, tuple):
                        attr_name = el[0]
                        match = el[1].match(s)
                    else:
                        match = el.match(s)
                    if match:
                        if (attr_name or k) in result:
                            if not isinstance(result[attr_name or k], list):
                                result[attr_name or k] = [result[attr_name or k]]
                            result[attr_name or k].append(match.groups()[0])
                        else:
                            result[attr_name or k] = match.groups()[0]
                        s = s[match.span()[1] :]
                        break
                if not match:
                    break
                s = s.lstrip()
        s = s.lstrip()
    if s:
        result.update({"comment": s})
    return result


class LockException(Exception):
    pass


class Lock:
    def __init__(
        self,
        memset: set = None,
        obj_id: int = None,
        timeout: float = 1.0,
        check: float = 0.1,
    ):
        self.memset = memset
        self.obj_id = obj_id
        self.timeout = timeout or 0.0
        self.check = check

    async def _acquire_lock(self) -> bool:
        current_timeout = 0.0
        while current_timeout < self.timeout:
            if self.obj_id in self.memset:
                current_timeout += self.check
                await asyncio.sleep(self.check)
            else:
                self.memset.add(self.obj_id)
                return True
        return False

    async def __aenter__(self):
        locked = await self._acquire_lock()
        if locked:
            return self
        raise LockException("Already locked by another coroutine")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.memset.remove(self.obj_id)


def get_command(message_text: str) -> str:
    """
    extract !command from string
    :param message_text: str
    :return:
    """
    return message_text.split(" ")[0][1:]


def get_user_name(user: "Union[PeerUser, str]") -> str:
    """
    Return telegram username or link
    :param user:
    :return: str
    """
    if isinstance(user, PeerUser):
        return f"[{user.user_id}](tg://user?id={user.user_id})"
    return f"[{user}](tg://user?id={user})" if user.isdigit() else user


def get_id_from_entity(entity: "hints.EntityLike") -> int:
    """
    Get entity ID from any type
    :param entity: EntityLike
    :return: int
    """
    if isinstance(entity, str) and entity.isdigit():
        return int(entity)
    if isinstance(entity, types.InputPeerChat):
        return entity.chat_id
    if isinstance(entity, types.InputPeerChannel):
        return entity.channel_id
    if isinstance(entity, types.InputPeerUser):
        return entity.user_id
    raise ValueError("Can`t find entity ID")


class Command(BaseCommand):
    help = "run guard bot"

    def handle(self, *args, **options):
        """
        Client and loop initialization
        :param args: ignored
        :param options: ignored
        :return:
        """
        self.loop.create_task(self.get_me(), name="get_me")
        self.loop.create_task(self.refresh_admins_task(), name="refresh_admins")
        self.set_events()

        self.client.run_until_disconnected()

    async def refresh_admins_for_chat(self, chat_id: int, db_admins: set[int]):
        """
        Reload admins for current chat

        :param chat_id: int
        :param db_admins: set
        :return:
        """
        try:
            async with Lock(self.groups_memset, chat_id):
                tg_admin_ids = set()
                async for tg_admin in self.client.iter_participants(
                    chat_id, filter=ChannelParticipantsAdmins
                ):
                    tg_admin_ids.add(tg_admin.id)
                    if tg_admin.id not in db_admins:
                        await ChatAdmins.objects.acreate(
                            chat_id=chat_id,
                            user_id=tg_admin.id,
                            can_delete=tg_admin.participant.admin_rights.delete_messages,
                            can_ban=tg_admin.participant.admin_rights.ban_users,
                            can_add_admin=tg_admin.participant.admin_rights.add_admins,
                        ) if isinstance(
                            tg_admin.participant, ChannelParticipantAdmin
                        ) else await ChatAdmins.objects.acreate(
                            chat_id=chat_id,
                            user_id=tg_admin.id,
                            can_delete=True,
                            can_ban=True,
                            can_add_admin=True,
                        )
                    else:
                        await ChatAdmins.objects.filter(
                            chat_id=chat_id, user_id=tg_admin.id
                        ).aupdate(
                            can_delete=tg_admin.participant.admin_rights.delete_messages,
                            can_ban=tg_admin.participant.admin_rights.ban_users,
                            can_add_admin=tg_admin.participant.admin_rights.add_admins,
                        ) if isinstance(
                            tg_admin.participant, ChannelParticipantAdmin
                        ) else await ChatAdmins.objects.acreate(
                            chat_id=chat_id,
                            user_id=tg_admin.id,
                            can_delete=True,
                            can_ban=True,
                            can_add_admin=True,
                        )
                delete_ids = db_admins.difference(tg_admin_ids)
                if delete_ids:
                    await ChatAdmins.objects.filter(
                        chat_id=chat_id, user_id__in=delete_ids
                    ).adelete()
        except LockException as e:
            logger.warning(f"Reloading admins for chat {chat_id}. {e}")

    async def _refresh_admins_task(self):
        """
        Refresh admin task implementation, uses in periodic updates
        :return: None
        """
        chat_admins = await ChatAdmins.get_admins_by_chat()
        for chat_id, db_admins in chat_admins.items():
            logger.info(f"Reloading admins for chat {chat_id}")
            await self.refresh_admins_for_chat(chat_id, db_admins)
            await asyncio.sleep(settings.BETWEEN_GROUPS_REFRESH_COOLDOWN)
        await asyncio.sleep(settings.ADMIN_GROUPS_REFRESH_PERIOD * 60)

    async def refresh_admins_task(self):
        """
        Periodic Task for admin update
        :return: None
        """
        while True:
            await self._refresh_admins_task()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.me = None
        self.client = TelegramClient(
            settings.BOT_DB, settings.API_ID, settings.API_HASH
        ).start(bot_token=settings.BOT_TOKEN)
        self.loop = self.client.loop
        self.groups_memset = set()

    async def get_me(self):
        """
        get client info

        :return:
        """
        self.me = await self.client.get_me()

    def set_events(self):
        """
        set events
        :return:
        """
        self.client.add_event_handler(
            self.on_new_message, events.NewMessage(incoming=True)
        )
        self.client.add_event_handler(
            self.on_edit_message, events.MessageEdited(incoming=True)
        )

    async def run_command(self, event: events.NewMessage):
        """
        Run bot command
        :param event:
        :return:
        """
        command = get_command(event.message.text)
        method = getattr(self, command, None)
        if method and getattr(method, "is_chat_command", False):
            await method(event)
        else:
            await event.message.reply(WRONG_COMMAND)

    async def spam_check(self, event: "Union[events.NewMessage, events.MessageEdited]"):
        """
        spam check for message
        :param event: events.MessageEdited
        :return:
        """
        # TODO: think about it
        pass

    async def on_new_message(self, event: events.NewMessage):
        """Run command or spam check"""
        if event.message.text and event.message.text.startswith("!"):
            await self.run_command(event)
        else:
            await self.spam_check(event)

    async def on_edit_message(self, event: events.MessageEdited):
        """Spam check"""
        await self.spam_check(event)

    async def _get_users(
        self, event: events.NewMessage, users: "Union[str, list[str]]"
    ) -> "List[Union[str, int]]":
        """
        Get usernames
        :param event: events.NewMessage
        :param users: string or list of strings
        :return: if message is reply, then return list as [user_id], where user_id is integer, else
        return list of users as [str, ...]
        """
        if event.message.is_reply:
            message: Union[
                hints.MessageLike, hints.TotalList
            ] = await self.client.get_messages(
                event.message.chat.id, ids=event.message.reply_to.reply_to_msg_id
            )
            users = [message.from_id]
        if users:
            if not isinstance(users, list):
                users = [users]
        return users

    async def get_user_id(self, user: "Union[hints.EntityLike, str]") -> int:
        """
        Get user ID
        :param user: str or EntityLike
        :return: int
        """
        if isinstance(user, str) and user.isdigit():
            return int(user)
        user_entity = await self.client.get_input_entity(user)
        return get_id_from_entity(user_entity)

    async def get_user_name_and_id(
        self, user: "Union[hints.EntityLike, str]"
    ) -> "Tuple[str, int]":
        """
        Return username and ID
        :param user: str or EntityLike
        :return: tuple(str, int)
        """
        user_id = await self.get_user_id(user)
        user_name = get_user_name(user)
        return user_name, user_id

    async def _mute_or_ban(
        self,
        event: events.NewMessage,
        chat_id: int = None,
        mute: bool = True,
        undo: bool = False,
        users: list[str] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        comment: str = None,
        **kwargs,
    ):
        """Base method for mute or ban users"""

        action = (
            (UNMUTED if undo else MUTED) if mute else (UNBANNED if undo else BANNED)
        )
        result_message = ""
        users = await self._get_users(event, users)
        if not users:
            return result_message
        for user in users:
            user_name, user_id = await self.get_user_name_and_id(user)
            try:
                kwargs = {"send_messages" if mute else "view_messages": undo}
                delta = timedelta(
                    days=int(days), hours=int(hours), minutes=int(minutes)
                )
                await self.client.edit_permissions(
                    chat_id, user_id, until_date=delta, **kwargs
                )
                delta_str = f" on {delta}" if delta else ""
                result_message += RESULT_MESSAGE.format(user_name, action, delta_str)
                await UserWarn.set_warn(
                    chat_id=chat_id,
                    user_id=user_id,
                    warn_type=(WarnType.UNMUTE if undo else WarnType.MUTE)
                    if mute
                    else (WarnType.UNBAN if undo else WarnType.BAN),
                    comment=comment,
                )
            except (UserAdminInvalidError, ChatAdminRequiredError, UserIdInvalidError):
                result_message += RESULT_ERROR_MESSAGE.format(user_name, action)
        if comment:
            result_message += REASON.format(comment)
        await event.message.delete()
        return result_message

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def ban(self, event: events.NewMessage, **kwargs):
        """ban user by reply, @username or ID"""
        result_message = await self._mute_or_ban(event, mute=False, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def sban(self, event: events.NewMessage, **kwargs):
        """silent ban by @username or ID. Admin message will be deleted"""
        await self._mute_or_ban(event, mute=False, **kwargs)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def unban(self, event: events.NewMessage, **kwargs):
        """Unban user by reply, @username or ID"""
        result_message = await self._mute_or_ban(event, mute=False, undo=True, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS_AND_PERIOD)
    @admin_check("can_ban")
    async def mute(self, event: events.NewMessage, **kwargs):
        """Mute user by reply, @username or ID"""
        result_message = await self._mute_or_ban(event, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS_AND_PERIOD)
    @admin_check("can_ban")
    async def smute(self, event: events.NewMessage, **kwargs):
        """Silent mute by reply, @username or ID. Admin message will be deleted"""
        await self._mute_or_ban(event, **kwargs)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def unmute(self, event: events.NewMessage, **kwargs):
        """Unmute user by reply, @username or ID"""
        result_message = await self._mute_or_ban(event, undo=True, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    async def _kick(
        self,
        event: events.NewMessage,
        chat_id: int = None,
        users: list[str] = None,
        comment: str = None,
        **kwargs,
    ):
        """Base method for user kick"""
        result_message = ""
        users = await self._get_users(event, users)
        if not users:
            return result_message
        for user in users:
            user_name, user_id = await self.get_user_name_and_id(user)
            try:
                await self.client.kick_participant(chat_id, user_id)
                result_message += RESULT_KICK_MESSAGE.format(user_name)
                await UserWarn.set_warn(
                    chat_id=chat_id,
                    user_id=user_id,
                    warn_type=WarnType.KICK,
                    comment=comment,
                )
            except (UserAdminInvalidError, ChatAdminRequiredError, UserIdInvalidError):
                result_message += ERROR_KICK_MESSAGE.format(user_name)
        if comment:
            result_message += REASON.format(comment)
        await event.message.delete()
        return result_message

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def kick(self, event: events.NewMessage, **kwargs):
        """Kick user from chat"""
        result_message = await self._kick(event, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def skick(self, event: events.NewMessage, **kwargs):
        """Silent kick user from chat. Admin message will be deleted"""
        await self._kick(event, **kwargs)

    async def _warn(
        self,
        event: events.NewMessage,
        chat_id: int = None,
        users: list[str] = None,
        comment: str = None,
        **kwargs,
    ):
        """Base method for user warn"""
        result_message = ""
        users = await self._get_users(event, users)
        if not users:
            return result_message
        for user in users:
            user_name, user_id = await self.get_user_name_and_id(user)
            time_period = await UserWarn.have_to_mute(chat_id=chat_id, user_id=user_id)
            result_message += USER_WARNED.format(user_name)
            await UserWarn.set_warn(
                chat_id=chat_id,
                user_id=user_id,
                warn_type=WarnType.WARN,
                comment=comment,
            )
            if time_period:
                try:
                    await self.client.edit_permissions(
                        chat_id, user_id, until_date=time_period, send_messages=False
                    )
                    result_message += USER_MUTED.format(user_name, time_period)
                    await UserWarn.set_warn(
                        chat_id=chat_id,
                        user_id=user_id,
                        warn_type=WarnType.MUTE,
                        comment=comment,
                    )
                except (
                    UserAdminInvalidError,
                    ChatAdminRequiredError,
                    UserIdInvalidError,
                ):
                    result_message += USER_NOT_MUTED.format(user_name, time_period)
        if comment:
            result_message += REASON.format(comment)
        await event.message.delete()
        return result_message

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def warn(self, event: events.NewMessage, **kwargs):
        """issue a warning"""
        result_message = await self._warn(event, **kwargs)
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def dwarn(self, event: events.NewMessage, **kwargs):
        """Delete message and issue a warning, only for reply"""
        if not event.message.is_reply:
            return
        result_message = await self._warn(event, **kwargs)
        await self.client.delete_messages(
            kwargs["chat_id"], message_ids=event.message.reply_to.reply_to_msg_id
        )
        if result_message:
            await self.client.send_message(kwargs["chat_id"], message=result_message)

    @attr_setter(USERS)
    @admin_check("can_ban")
    async def unwarn(
        self, event: events.NewMessage, chat_id=None, users=None, comment=None, **kwargs
    ):
        """Delete all current warnings for users"""
        result_message = ""
        users = await self._get_users(event, users)
        if not users:
            return
        for user in users:
            user_name, user_id = await self.get_user_name_and_id(user)
            warn_count = await UserWarn.delete_current_warnings(
                chat_id=chat_id, user_id=user_id
            )
            result_message += USER_WARN_DELETED.format(user_name, warn_count)
        if comment:
            result_message += REASON.format(comment)
        if result_message:
            await self.client.send_message(chat_id, message=result_message)

    async def spam(self, event: events.NewMessage):
        """Delete spam message, reply to and mark as spam"""
        # TODO: think about it
        pass

    async def _freeze(
        self,
        chat_id: int = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        **kwargs,
    ):
        """Base method for chat slowdown"""
        seconds = timedelta(
            days=int(days), hours=int(hours), minutes=int(minutes)
        ).seconds
        await self.client(
            ToggleSlowModeRequest(
                channel=chat_id,
                seconds=min(SLOW_MODE_VALUES, key=lambda x: abs(x - seconds)),
            )
        )

    @attr_setter(OrderedDict({"command": COMMAND, "period": PERIOD}))
    @admin_check("can_delete")
    async def freeze(self, event: events.NewMessage, chat_id=None, **kwargs):
        """Slowdown chat"""
        try:
            await self._freeze(chat_id=chat_id, **kwargs)
            await self.client.send_message(chat_id, message=SLOW_MODE_ON)
        except SecondsInvalidError:
            pass

    @attr_setter(OrderedDict({"command": COMMAND, "period": PERIOD}))
    @admin_check("can_delete")
    async def unfreeze(self, event: events.NewMessage, chat_id=None, **kwargs):
        """unfreeze chat"""
        try:
            await self._freeze(chat_id=chat_id)
            await self.client.send_message(chat_id, message=SLOW_MODE_OFF)
        except SecondsInvalidError:
            pass

    @admin_check("can_add_admin")
    async def refresh_admins(self, event: events.NewMessage):
        """reload admins in chat"""
        chat_id = event.message.chat.id
        admins = await ChatAdmins.get_admins_by_chat(chat_id)
        await self.refresh_admins_for_chat(chat_id, admins.get(chat_id, set()))
