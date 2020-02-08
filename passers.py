import discord

from types import FunctionType
from enums import PermissionLevels, CreateReminderResponse
from models import Guild, User, Language, session, ENGLISH_STRINGS
import typing


# wrapper for command functions
class Command():
    def __init__(self, func_call: FunctionType, dm_allowed: bool = True, permission_level: PermissionLevels = PermissionLevels.UNRESTRICTED):
        self.func = func_call
        self.allowed_dm = dm_allowed
        self.permission_level = permission_level

class Preferences():
    def __init__(self, server: Guild, user: User):

        self._user: User = user
        self._server: Guild = server

        language_code: str = user.language or 'EN'
        timezone_code: str = user.timezone or ('UTC' if server is None else server.timezone)
        server_timezone_code = None if server is None else server.timezone

        self._language: typing.Optional[Language] = session.query(Language).filter(Language.code == language_code).first() or ENGLISH_STRINGS
        self._timezone: str = timezone_code
        self._server_timezone: str = server_timezone_code
        self._prefix: str = '$'
        self.command_restrictions = None

        if server is not None:
            self._prefix = server.prefix
            self.command_restrictions = server.command_restrictions

        self._allowed_dm: bool = user.allowed_dm


    @property
    def language(self):
        return self._language

    @property
    def timezone(self):
        return self._timezone

    @property
    def server_timezone(self):
        return self._server_timezone

    @property
    def prefix(self):
        return self._prefix

    @language.setter
    def language(self, value):
        self._user.language = value
        self._language = value

    @timezone.setter
    def timezone(self, value):
        self._user.timezone = value
        self._timezone = value

    @server_timezone.setter
    def server_timezone(self, value):
        self._server.timezone = value
        self._server_timezone = value

    @prefix.setter
    def prefix(self, value):
        self._server.prefix = value
        self._prefix = value


class ReminderInformation():
    def __init__(self, status: CreateReminderResponse, channel: discord.TextChannel = None, time: float = 0):
        self.status: CreateReminderResponse = status
        self.time: typing.Optional[float] = time
        self.location: typing.Optional[discord.TextChannel] = None

        if channel is not None:
            self.location = channel.recipient if isinstance(channel, discord.DMChannel) else channel
        else:
            self.location = NoneChannel()


class NoneChannel():
    def __init__(self):
        self.mention: str = ''


class DMChannelId():
    def __init__(self, id, user):
        self.id: int = id
        self.mention: str = '<@{}>'.format(user)