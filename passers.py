import discord

from enums import PermissionLevels, CreateReminderResponse
from models import Guild, User, Language, session, ENGLISH_STRINGS, CommandRestriction
import typing


# wrapper for command functions
class Command:
    def __init__(self, name: str, func_call: (discord.Message, str, 'Preferences'), dm_allowed: bool = True,
                 permission_level: PermissionLevels = PermissionLevels.UNRESTRICTED, *, blacklists: bool = True):
        self.name = name
        self.func = func_call
        self.allowed_dm = dm_allowed
        self.permission_level = permission_level
        self.blacklists = blacklists

    def check_permissions(self, member, guild_data):
        if self.permission_level == PermissionLevels.UNRESTRICTED:
            return True

        elif self.permission_level == PermissionLevels.MANAGED:
            restrict = guild_data.command_restrictions \
                .filter(CommandRestriction.command == self.name) \
                .filter(CommandRestriction.role.in_([x.id for x in member.roles]))

            return restrict.count() == 0 and not member.guild_permissions.manage_messages

        elif self.permission_level == PermissionLevels.RESTRICTED:
            return member.guild_permissions.manage_guild


class Preferences:
    def __init__(self, guild: typing.Optional[Guild], user: User):
        self.user: User = user
        self.guild: Guild = guild

        language_code: str = user.language or 'EN'
        timezone_code: str = user.timezone or ('UTC' if guild is None else guild.timezone)
        guild_timezone_code = None if guild is None else guild.timezone

        self._language: typing.Optional[Language] = session.query(Language).filter(
            Language.code == language_code).first() or ENGLISH_STRINGS
        self._timezone: str = timezone_code
        self._guild_timezone: str = guild_timezone_code
        self._prefix: str = '$'
        self.command_restrictions = None

        if guild is not None:
            self._prefix = guild.prefix
            self.command_restrictions = guild.command_restrictions

        self._allowed_dm: bool = user.allowed_dm

    @property
    def language(self):
        return self._language

    @property
    def timezone(self):
        return self._timezone

    @property
    def server_timezone(self):
        return self._guild_timezone

    @property
    def prefix(self):
        return self._prefix

    @language.setter
    def language(self, value):
        self.user.language = value
        self._language = value

    @timezone.setter
    def timezone(self, value):
        self.user.timezone = value
        self._timezone = value

    @server_timezone.setter
    def server_timezone(self, value):
        self.guild.timezone = value
        self._guild_timezone = value

    @prefix.setter
    def prefix(self, value):
        self.guild.prefix = value
        self._prefix = value


class ReminderInformation:
    def __init__(self, status: CreateReminderResponse, channel: discord.TextChannel = None, time: float = 0):
        self.status: CreateReminderResponse = status
        self.time: typing.Optional[float] = time
        self.location: typing.Optional[discord.TextChannel] = None

        if channel is not None:
            self.location = channel.recipient if isinstance(channel, discord.DMChannel) else channel
        else:
            self.location = NoneChannel()


class NoneChannel:
    def __init__(self):
        self.mention: str = ''


class DMChannelId:
    def __init__(self, channel_id: int, user_id: int):
        self.id: int = channel_id
        self.mention: str = '<@{}>'.format(user_id)
