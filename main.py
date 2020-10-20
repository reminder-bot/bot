import asyncio
import concurrent.futures
import itertools
import re
from datetime import datetime, timedelta
from functools import partial
from json import dumps as json_dump
from time import time as unix_time
import logging

import aiohttp
import dateparser
import pytz

from config import Config
from consts import *
from models import Reminder, Todo, Timer, Message, Channel, Event, CommandAlias
from passers import *
from time_extractor import TimeExtractor, InvalidTime
from enums import TodoScope

THEME_COLOR = 0x8fb677

logging.basicConfig(level=logging.INFO)


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        self.start_time: float = unix_time()

        self.commands: typing.Dict[str, Command] = {

            'ping': Command('ping', self.time_stats),

            'help': Command('help', self.help, blacklists=False),
            'dashboard': Command('dashboard', self.dash),
            'info': Command('info', self.info),
            'donate': Command('donate', self.donate),

            'timezone': Command('timezone', self.set_timezone),
            'lang': Command('lang', self.set_language),
            'clock': Command('clock', self.clock),

            'todo': Command('todo', self.todo_user),
            'todoc': Command('todo', self.todo_channel),
            'todos': Command('todos', self.todo_guild, False, PermissionLevels.MANAGED),

            'todo user': Command('todo', self.todo_user),
            'todo channel': Command('todo', self.todo_channel),
            'todo server': Command('todo', self.todo_guild),

            'natural': Command('natural', self.natural, True, PermissionLevels.MANAGED),
            'n': Command('natural', self.natural, True, PermissionLevels.MANAGED),
            '': Command('natural', self.natural, True, PermissionLevels.MANAGED),
            'remind': Command('remind', self.remind_cmd, True, PermissionLevels.MANAGED),
            'r': Command('remind', self.remind_cmd, True, PermissionLevels.MANAGED),
            'interval': Command('interval', self.interval_cmd, True, PermissionLevels.MANAGED),
            # TODO: remodel timer table with FKs for guild table
            'timer': Command('timer', self.timer, False, PermissionLevels.MANAGED),
            'del': Command('del', self.delete, True, PermissionLevels.MANAGED),
            # TODO: allow looking at reminder attributes in full by name
            'look': Command('look', self.look, True, PermissionLevels.MANAGED),

            'alias': Command('alias', self.create_alias, False, PermissionLevels.MANAGED),
            'a': Command('alias', self.create_alias, False, PermissionLevels.MANAGED),

            'prefix': Command('prefix', self.change_prefix, False, PermissionLevels.RESTRICTED),

            'blacklist': Command('blacklist', self.blacklist, False, PermissionLevels.RESTRICTED, blacklists=False),
            'restrict': Command('restrict', self.restrict, False, PermissionLevels.RESTRICTED),

            'offset': Command('offset', self.offset_reminders, True, PermissionLevels.RESTRICTED),
            'nudge': Command('nudge', self.nudge_channel, True, PermissionLevels.RESTRICTED),
            'pause': Command('pause', self.pause_channel, False, PermissionLevels.RESTRICTED),
        }

        self.match_string = None

        self.command_names = set(self.commands.keys())
        self.joined_names = '|'.join(sorted(self.commands.keys(), key=len, reverse=True))

        # used in restrict command for filtration
        self.max_command_length = max(len(x) for x in self.command_names)

        self.executor: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor()
        self.c_session: typing.Optional[aiohttp.ClientSession] = None

        super(BotClient, self).__init__(*args, **kwargs)

    async def do_blocking(self, method):
        # perform a long running process within a threadpool
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]

    @staticmethod
    async def find_and_create_member(member_id: int, context_guild: typing.Optional[discord.Guild]) \
            -> typing.Optional[User]:
        u: User = session.query(User).filter(User.user == member_id).first()

        if u is None and context_guild is not None:
            m = await context_guild.fetch_member(member_id)

            if m is not None:
                c = Channel(channel=(await m.create_dm()).id)
                session.add(c)
                session.flush()

                u = User(user=m.id, name='{}'.format(m), dm_channel=c.id)

                session.add(u)
                session.commit()

        return u

    async def is_patron(self, member_id) -> bool:
        if config.patreon_enabled:

            url = 'https://discordapp.com/api/v6/guilds/{}/members/{}'.format(config.patreon_server, member_id)

            head = {
                'authorization': 'Bot {}'.format(config.token),
                'content-type': 'application/json'
            }

            async with self.c_session.get(url, headers=head) as resp:

                if resp.status == 200:
                    member = await resp.json()
                    roles = [int(x) for x in member['roles']]

                else:
                    return False

            return config.patreon_role in roles

        else:
            return True

    async def on_error(self, *a, **k):
        session.rollback()
        raise

    async def on_ready(self):

        logging.info('Logged in as')
        logging.info(self.user.name)
        logging.info(self.user.id)

        self.match_string = \
            r'(?:(?:<@ID>\s*)|(?:<@!ID>\s*)|(?P<prefix>\S{1,5}?))(?P<cmd>COMMANDS)(?:$|\s+(?P<args>.*))' \
                .replace('ID', str(self.user.id)).replace('COMMANDS', self.joined_names)

        self.c_session: aiohttp.client.ClientSession = aiohttp.ClientSession()

        if config.patreon_enabled:
            logging.info('Patreon is enabled. Will look for servers {}'.format(config.patreon_server))

        logging.info('Local timezone set to *{}*'.format(config.local_timezone))
        logging.info('Local language set to *{}*'.format(config.local_language))

    async def on_guild_join(self, guild):

        async def welcome(guild, *_):

            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                    await channel.send('Thank you for adding reminder-bot! To begin, type `$help`!')
                    break

                else:
                    continue

        await self.send()

        await welcome(guild)

    # noinspection PyMethodMayBeStatic
    async def on_guild_remove(self, guild):
        session.query(Guild).filter(Guild.guild == guild.id).delete(synchronize_session='fetch')

    # noinspection PyMethodMayBeStatic
    async def on_guild_channel_delete(self, channel):
        session.query(Channel).filter(Channel.channel == channel.id).delete(synchronize_session='fetch')

    async def send(self):
        if config.dbl_token and self.c_session is not None:
            guild_count = len(self.guilds)

            dump = json_dump({
                'server_count': guild_count
            })

            head = {
                'authorization': config.dbl_token,
                'content-type': 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with self.c_session.post(url, data=dump, headers=head) as resp:
                logging.debug('returned {0.status} for {1}'.format(resp, dump))

    # noinspection PyBroadException
    async def on_message(self, message):

        def _check_self_permissions(_channel):
            p = _channel.permissions_for(message.guild.me)

            return p.send_messages and p.embed_links

        async def _get_user(_message):
            _user = session.query(User).filter(User.user == message.author.id).first()
            if _user is None:
                dm_channel_id = (await message.author.create_dm()).id

                c = session.query(Channel).filter(Channel.channel == dm_channel_id).first()

                if c is None:
                    c = Channel(channel=dm_channel_id)
                    session.add(c)
                    session.flush()

                    _user = User(user=_message.author.id, dm_channel=c.id, name='{}#{}'.format(
                        _message.author.name, _message.author.discriminator))
                    session.add(_user)
                    session.flush()

            return _user

        if (message.author.bot and config.ignore_bots) or \
                message.content is None or \
                message.tts or \
                len(message.attachments) > 0 or \
                self.match_string is None:

            # either a bot or cannot be a command
            return

        elif message.guild is None:
            # command has been DMed. dont check for prefix :)
            split = message.content.split(' ')

            command_word = split[0].lower()
            if len(command_word) > 0:
                if command_word[0] == '$':
                    command_word = command_word[1:]

                args = ' '.join(split[1:]).strip()

                if command_word in self.command_names:
                    command = self.commands[command_word]

                    if command.allowed_dm:
                        # get user
                        user = await _get_user(message)

                        await command.func(message, args, Preferences(None, user))

        elif _check_self_permissions(message.channel):
            if not message.guild.me.guild_permissions.manage_webhooks:
                await message.channel.send(ENGLISH_STRINGS.get_string('no_perms_webhook'))

            else:
                # command sent in guild. check for prefix & call
                match = re.match(
                    self.match_string,
                    message.content,
                    re.MULTILINE | re.DOTALL | re.IGNORECASE
                )

                if match is not None:
                    # matched command structure; now query for guild to compare prefix
                    guild = session.query(Guild).filter(Guild.guild == message.guild.id).first()
                    if guild is None:
                        guild = Guild(guild=message.guild.id)

                        session.add(guild)
                        session.flush()

                    # if none, suggests mention has been provided instead since pattern still matched
                    if (prefix := match.group('prefix')) in (guild.prefix, None):
                        # prefix matched, might as well get the user now since this is a very small subset of messages
                        user = await _get_user(message)

                        if guild not in user.guilds:
                            guild.users.append(user)

                        # create the nice info manager
                        info = Preferences(guild, user)

                        command_word = match.group('cmd').lower()
                        stripped = match.group('args') or ''
                        command = self.commands[command_word]

                        # some commands dont get blacklisted e.g help, blacklist
                        if command.blacklists:
                            channel, just_created = Channel.get_or_create(message.channel)

                            if channel.guild_id is None:
                                channel.guild_id = guild.id

                            if channel.blacklisted:
                                await message.channel.send(
                                    embed=discord.Embed(description=info.language.get_string('blacklisted')))
                                return

                        # blacklist checked; now do command permissions
                        if command.check_permissions(message.author, guild):
                            await command.func(message, stripped, info)
                            session.commit()

                        else:
                            await message.channel.send(
                                info.language.get_string(
                                    str(command.permission_level)).format(prefix=prefix))

        else:
            return

    async def time_stats(self, message, *_):
        uptime: float = unix_time() - self.start_time

        message_ts: float = message.created_at.timestamp()

        m: discord.Message = await message.channel.send('.')

        ping: float = m.created_at.timestamp() - message_ts

        await m.edit(content='''
        Uptime: {}s
        Ping: {}ms
        '''.format(round(uptime), round(ping * 1000)))

    @staticmethod
    async def help(message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(
            description=preferences.language.get_string('help'),
            color=THEME_COLOR,
            footer_text='reminder-bot ver final'
        ))

    @staticmethod
    async def dash(message, _stripped, _preferences):
        await message.channel.send(embed=discord.Embed(
            title='Dashboard',
            description='https://reminder-bot.com/dashboard',
            color=THEME_COLOR,
            footer_text='reminder-bot ver final'
        ))

    async def info(self, message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(
            description=preferences.language.get_string('info').format(prefix=preferences.prefix, user=self.user.name),
            color=THEME_COLOR,
            footer_text='reminder-bot ver final'
        ))

    @staticmethod
    async def donate(message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(
            description=preferences.language.get_string('donate'),
            color=THEME_COLOR
        ))

    @staticmethod
    async def change_prefix(message, stripped, preferences):

        if stripped:

            stripped += ' '
            new = stripped[:stripped.find(' ')]

            if len(new) > 5:
                await message.channel.send(preferences.language.get_string('prefix/too_long'))

            else:
                preferences.prefix = new
                session.commit()

                await message.channel.send(preferences.language.get_string('prefix/success').format(
                    prefix=preferences.prefix))

        else:
            await message.channel.send(preferences.language.get_string('prefix/no_argument').format(
                prefix=preferences.prefix))

    async def create_alias(self, message, stripped, preferences):
        groups = re.fullmatch(r'(?P<name>[\S]{1,12})(?:(?: (?P<cmd>.*)$)|$)', stripped)

        if groups is not None:
            named_groups: typing.Dict[str, str] = groups.groupdict()

            name: str = named_groups['name']
            command: typing.Optional[str] = named_groups.get('cmd')

            if (name in ['list',
                         'remove'] or command is not None) and not message.author.guild_permissions.manage_guild:
                await message.channel.send(preferences.language['no_perms_restricted'])

            elif name == 'list':
                alias_concat = ''

                for alias in preferences.guild.aliases:
                    alias_concat += '**{}**: `{}`\n'.format(alias.name, alias.command)

                await message.channel.send('Aliases: \n{}'.format(alias_concat))

            elif name == 'remove':
                name = command

                query = session.query(CommandAlias) \
                    .filter(CommandAlias.name == name) \
                    .filter(CommandAlias.guild == preferences.guild)

                if query.first() is not None:
                    query.delete(synchronize_session='fetch')
                    await message.channel.send(preferences.language['alias/removed'].format(count=1))

                else:
                    await message.channel.send(preferences.language['alias/removed'].format(count=0))

            elif command is None:
                # command not specified so look for existing alias
                try:
                    aliased_command = next(filter(lambda alias: alias.name == name, preferences.guild.aliases))

                except StopIteration:
                    await message.channel.send(preferences.language['alias/not_found'].format(name=name))

                else:
                    command = aliased_command.command
                    split = command.split(' ')

                    command_obj = self.commands.get(split[0])

                    if command_obj is None or command_obj.name == 'alias':
                        await message.channel.send(preferences.language['alias/invalid_command'])

                    elif command_obj.check_permissions(message.author, preferences.guild):
                        await command_obj.func(message, ' '.join(split[1:]), preferences)

                    else:
                        await message.channel.send(
                            preferences.language[str(command_obj.permission_level)]
                                .format(prefix=preferences.guild.prefix))

            else:
                # command provided so create new alias
                if (cmd := command.split(' ')[0]) not in self.command_names and cmd not in ['alias', 'a']:
                    await message.channel.send(preferences.language['alias/invalid_command'])

                else:
                    if (alias := session.query(CommandAlias)
                            .filter_by(guild=preferences.guild, name=name).first()) is not None:

                        alias.command = command

                    else:
                        alias = CommandAlias(guild=preferences.guild, command=command, name=name)
                        session.add(alias)

                    session.commit()

                    await message.channel.send(preferences.language['alias/created'].format(name=name))

        else:
            await message.channel.send(preferences.language['alias/help'].format(prefix=preferences.guild.prefix))

    @staticmethod
    async def set_timezone(message, stripped, preferences):

        if message.guild is not None and message.author.guild_permissions.manage_guild:
            s = 'timezone/set'
            admin = True
        else:
            s = 'timezone/set_p'
            admin = False

        if stripped == '':
            await message.channel.send(embed=discord.Embed(
                description=preferences.language.get_string('timezone/no_argument').format(
                    prefix=preferences.prefix, timezone=preferences.timezone)))

        else:
            if stripped not in pytz.all_timezones:
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('timezone/no_timezone')))
            else:
                if admin:
                    preferences.server_timezone = stripped
                else:
                    preferences.timezone = stripped

                d = datetime.now(pytz.timezone(stripped))

                await message.channel.send(embed=discord.Embed(
                    description=preferences.language.get_string(s).format(
                        timezone=stripped, time=d.strftime('%H:%M:%S'))))

                session.commit()

    @staticmethod
    async def set_language(message, stripped, preferences):

        new_lang = session.query(Language).filter(
            (Language.code == stripped.upper()) | (Language.name == stripped.lower())).first()

        if new_lang is not None:
            preferences.language = new_lang.code
            session.commit()

            await message.channel.send(embed=discord.Embed(description=new_lang.get_string('lang/set_p')))

        else:
            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('lang/invalid').format(
                    '\n'.join(
                        ['{} ({})'.format(lang.name.title(), lang.code.upper()) for lang in session.query(Language)])
                )
                )
            )

    @staticmethod
    async def clock(message, stripped, preferences):

        if '12' in stripped:
            f_string = '%I:%M:%S %p'
        else:
            f_string = '%H:%M:%S'

        t = datetime.now(pytz.timezone(preferences.timezone))

        await message.channel.send(preferences.language.get_string('clock/time').format(t.strftime(f_string)))

    async def natural(self, message, stripped, server):

        if len(stripped.split(server.language.get_string('natural/send'))) < 2:
            await message.channel.send(embed=discord.Embed(
                description=server.language.get_string('natural/no_argument').format(prefix=server.prefix)))
            return

        location_ids: typing.List[int] = [message.channel.id]

        time_crop = stripped.split(server.language.get_string('natural/send'))[0]
        message_crop = stripped.split(server.language.get_string('natural/send'), 1)[1]
        datetime_obj = await self.do_blocking(partial(dateparser.parse, time_crop, settings={
            'TIMEZONE': server.timezone,
            'TO_TIMEZONE': config.local_timezone,
            'RELATIVE_BASE': datetime.now(pytz.timezone(server.timezone)).replace(tzinfo=None),
            'PREFER_DATES_FROM': 'future'
        }))

        if datetime_obj is None:
            await message.channel.send(
                embed=discord.Embed(description=server.language.get_string('natural/invalid_time')))
            return

        if message.guild is not None:
            chan_split = message_crop.split(server.language.get_string('natural/to'))
            if len(chan_split) > 1 and all(bool(set(x) & set('0123456789')) for x in chan_split[-1].split(' ')):
                location_ids = [int(''.join([x for x in z if x in '0123456789'])) for z in chan_split[-1].split(' ')]

                message_crop: str = message_crop.rsplit(server.language.get_string('natural/to'), 1)[0]

        interval_split = message_crop.split(server.language.get_string('natural/every'))
        recurring: bool = False
        interval: int = 0

        if len(interval_split) > 1:
            interval_dt = await self.do_blocking(partial(dateparser.parse, '1 ' + interval_split[-1]))

            if interval_dt is None:
                pass

            elif await self.is_patron(message.author.id):
                recurring = True

                interval = abs((interval_dt - datetime.now()).total_seconds())

                message_crop = message_crop.rsplit(server.language.get_string('natural/every'), 1)[0]

            else:
                await message.channel.send(embed=discord.Embed(
                    description=server.language.get_string('interval/donor').format(prefix=server.prefix)))
                return

        mtime: int = int(datetime_obj.timestamp())
        responses: typing.List[ReminderInformation] = []

        for location_id in location_ids:
            response: ReminderInformation = await self.create_reminder(message, location_id, message_crop, mtime,
                                                                       interval=interval if recurring else None,
                                                                       method='natural')
            responses.append(response)

        if len(responses) == 1:
            result: ReminderInformation = responses[0]
            string: str = NATURAL_STRINGS.get(result.status, REMIND_STRINGS[result.status])

            response = server.language.get_string(string).format(location=result.location.mention,
                                                                 offset=timedelta(
                                                                     seconds=int(result.time - unix_time())),
                                                                 min_interval=MIN_INTERVAL, max_time=MAX_TIME_DAYS)

            await message.channel.send(embed=discord.Embed(description=response))

        else:
            successes: int = len([r for r in responses if r.status == CreateReminderResponse.OK])

            await message.channel.send(
                embed=discord.Embed(description=server.language.get_string('natural/bulk_set').format(successes)))

    async def remind_cmd(self, message, stripped, server):
        await self.remind(False, message, stripped, server)

    async def interval_cmd(self, message, stripped, server):
        await self.remind(True, message, stripped, server)

    async def remind(self, is_interval, message, stripped, server):

        def filter_blanks(args, max_blanks=2):
            actual_args = 0

            for arg in args:
                if len(arg) == 0 and actual_args <= max_blanks:
                    continue

                else:
                    actual_args += 1
                    yield arg

        args = [x for x in filter_blanks(stripped.split(' '))]

        if len(args) < 2:
            if is_interval:
                await message.channel.send(embed=discord.Embed(
                    description=server.language.get_string('interval/no_argument').format(prefix=server.prefix)))

            else:
                await message.channel.send(embed=discord.Embed(
                    description=server.language.get_string('remind/no_argument').format(prefix=server.prefix)))

        else:
            if is_interval and not await self.is_patron(message.author.id):
                await message.channel.send(
                    embed=discord.Embed(description=server.language.get_string('interval/donor')))

            else:
                interval = None
                scope_id = message.channel.id

                if args[0][0] == '<' and message.guild is not None:
                    arg = args.pop(0)
                    scope_id = int(''.join(x for x in arg if x in '0123456789'))

                t = args.pop(0)
                time_parser = TimeExtractor(t, server.timezone)

                try:
                    mtime = time_parser.extract_exact()

                except InvalidTime:
                    await message.channel.send(
                        embed=discord.Embed(description=server.language.get_string('remind/invalid_time')))
                else:
                    if is_interval:
                        i = args.pop(0)

                        parser = TimeExtractor(i, server.timezone)

                        try:
                            interval = parser.extract_displacement()

                        except InvalidTime:
                            await message.channel.send(embed=discord.Embed(
                                description=server.language.get_string('interval/invalid_interval')))
                            return

                    text = ' '.join(args)

                    result = await self.create_reminder(message, scope_id, text, mtime, interval, method='remind')

                    response = server.language[REMIND_STRINGS[result.status]].format(
                        location=result.location.mention, offset=timedelta(seconds=int(result.time - unix_time())),
                        min_interval=MIN_INTERVAL, max_time=MAX_TIME_DAYS)

                    await message.channel.send(embed=discord.Embed(description=response))

    async def create_reminder(self, message: discord.Message, location: int, text: str, time: int,
                              interval: typing.Optional[int] = None, method: str = 'natural') -> ReminderInformation:
        ut: float = unix_time()

        if time > ut + MAX_TIME:
            return ReminderInformation(CreateReminderResponse.LONG_TIME)

        elif time < ut:

            if (ut - time) < 10:
                time = int(ut)

            else:
                return ReminderInformation(CreateReminderResponse.PAST_TIME)

        channel: typing.Optional[Channel] = None
        user: typing.Optional[User] = None

        creator: User = User.from_discord(message.author)

        # noinspection PyUnusedLocal
        discord_channel: typing.Optional[typing.Union[discord.TextChannel, DMChannelId]] = None

        # command fired inside a guild
        if message.guild is not None:
            discord_channel = message.guild.get_channel(location)

            if discord_channel is not None:  # if not a DM reminder

                channel, _ = Channel.get_or_create(discord_channel)

                try:
                    await channel.attach_webhook(discord_channel)

                except discord.errors.HTTPException as e:
                    logging.info(e)
                    return ReminderInformation(CreateReminderResponse.NO_WEBHOOK)

                else:
                    time += channel.nudge

            else:
                user = await self.find_and_create_member(location, message.guild)

                if user is None:
                    return ReminderInformation(CreateReminderResponse.INVALID_TAG)

                discord_channel = DMChannelId(user.dm_channel, user.user)

        # command fired in a DM; only possible target is the DM itself
        else:
            user = User.from_discord(message.author)
            discord_channel = DMChannelId(user.dm_channel, message.author.id)

        if interval is not None:
            if MIN_INTERVAL > interval:
                return ReminderInformation(CreateReminderResponse.SHORT_INTERVAL)

            elif interval > MAX_TIME:
                return ReminderInformation(CreateReminderResponse.LONG_INTERVAL)

            else:
                # noinspection PyArgumentList
                reminder = Reminder(
                    message=Message(content=text),
                    channel=channel or user.channel,
                    time=time,
                    enabled=True,
                    method=method,
                    interval=interval,
                    set_by=creator.id)
                session.add(reminder)
                session.commit()

        else:
            # noinspection PyArgumentList
            reminder = Reminder(
                message=Message(content=text),
                channel=channel or user.channel,
                time=time,
                enabled=True,
                method=method,
                set_by=creator.id)
            session.add(reminder)
            session.commit()

        return ReminderInformation(CreateReminderResponse.OK, channel=discord_channel, time=time)

    @staticmethod
    async def timer(message, stripped, preferences):

        if message.guild is None:
            owner = message.author.id
        else:
            owner = message.guild.id

        if stripped == 'list':
            timers = session.query(Timer).filter(Timer.owner == owner)

            e = discord.Embed(title='Timers')
            for timer in timers:
                delta = int((datetime.now() - timer.start_time).total_seconds())
                minutes, seconds = divmod(delta, 60)
                hours, minutes = divmod(minutes, 60)
                e.add_field(name=timer.name, value="{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds))

            await message.channel.send(embed=e)

        elif stripped.startswith('start'):
            timers = session.query(Timer).filter(Timer.owner == owner)

            if timers.count() >= 25:
                await message.channel.send(preferences.language.get_string('timer/limit'))

            else:
                n = stripped.split(' ')[1:2] or 'New timer #{}'.format(timers.count() + 1)

                if len(n) > 32:
                    await message.channel.send(preferences.language.get_string('timer/name_length').format(len(n)))

                elif n in [x.name for x in timers]:
                    await message.channel.send(preferences.language.get_string('timer/unique'))

                else:
                    t = Timer(name=n, owner=owner)

                    session.add(t)
                    session.commit()

                    await message.channel.send(preferences.language.get_string('timer/success'))

        elif stripped.startswith('delete '):

            n = ' '.join(stripped.split(' ')[1:])

            timers = session.query(Timer).filter(Timer.owner == owner).filter(Timer.name == n)

            if timers.count() < 1:
                await message.channel.send(preferences.language.get_string('timer/not_found'))

            else:
                timers.delete(synchronize_session='fetch')
                session.commit()

                await message.channel.send(preferences.language.get_string('timer/deleted'))

        else:
            await message.channel.send(preferences.language.get_string('timer/help'))

    @staticmethod
    async def blacklist(message, _, preferences):

        target_channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel

        channel, _ = Channel.get_or_create(target_channel)

        channel.blacklisted = not channel.blacklisted

        if channel.blacklisted:
            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('blacklist/added')))

        else:
            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('blacklist/removed')))

        session.commit()

    async def restrict(self, message, stripped, preferences):

        role_tag = re.search(r'<@&([0-9]+)>', stripped)

        args: typing.List[str] = re.findall(r'([a-z]+)', stripped)

        if len(args) == 0:
            if role_tag is None:
                # no parameters given so just show existing
                await message.channel.send(
                    embed=discord.Embed(
                        description=preferences.language.get_string('restrict/allowed').format(
                            '\n'.join(
                                ['{} can use `{}`'.format(r.role, r.command)
                                 for r in preferences.command_restrictions]
                            )
                        )
                    )
                )

            else:
                # only a role is given so delete all the settings for this role
                role_query = preferences.guild.roles.filter(Role.role == int(role_tag.group(1)))

                if (role := role_query.first()) is not None:
                    preferences.command_restrictions \
                        .filter(CommandRestriction.role == role) \
                        .delete(synchronize_session='fetch')

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('restrict/disabled')))

        elif role_tag is None:
            # misused- show help
            await message.channel.send(embed=discord.Embed(
                description=preferences.language.get_string('restrict/help')))

        else:
            # enable permissions for role for selected commands
            role_id: int = int(role_tag.group(1))
            enabled: bool = False

            for command in args:
                c: typing.Optional[Command] = self.commands.get(command)

                if c is not None and c.permission_level == PermissionLevels.MANAGED:
                    role_query = preferences.guild.roles.filter(Role.role == role_id)

                    if (role := role_query.first()) is not None:

                        q = preferences.command_restrictions \
                            .filter(CommandRestriction.command == c.name) \
                            .filter(CommandRestriction.role == role)

                        if q.first() is None:
                            new_restriction = CommandRestriction(guild_id=preferences.guild.id, command=c.name,
                                                                 role=role)

                            enabled = True

                            session.add(new_restriction)

                    else:
                        role = Role(role=role_id, guild=preferences.guild)
                        new_restriction = CommandRestriction(guild_id=preferences.guild.id, command=c.name, role=role)

                        session.add(new_restriction)

                else:
                    await message.channel.send(embed=discord.Embed(
                        description=preferences.language.get_string('restrict/failure').format(command=command)))

            if enabled:
                await message.channel.send(embed=discord.Embed(
                    description=preferences.language.get_string('restrict/enabled')))

        session.commit()

    async def todo_user(self, message, stripped, preferences):
        await self.todo_command(message, stripped, preferences, TodoScope.USER)

    async def todo_channel(self, message, stripped, preferences):
        await self.todo_command(message, stripped, preferences, TodoScope.CHANNEL)

    async def todo_guild(self, message, stripped, preferences):
        await self.todo_command(message, stripped, preferences, TodoScope.GUILD)

    @staticmethod
    async def todo_command(message, stripped, preferences, scope):
        if scope == TodoScope.CHANNEL:
            location, _ = Channel.get_or_create(message.channel)
            location_name = 'Channel'
            todos = location.todo_list
            channel = location
            guild = preferences.guild

        elif scope == TodoScope.USER:
            location = preferences.user
            location_name = 'User'
            todos = location.todo_list.filter(Todo.guild_id.is_(None))
            channel = None
            guild = None

        else:
            location = preferences.guild
            location_name = 'Server'
            todos = location.todo_list.filter(Todo.channel_id.is_(None))
            channel = None
            guild = preferences.guild

        command = 'todo {}'.format(location_name.lower())

        splits = stripped.split(' ')

        if len(splits) == 1 and splits[0] == '':
            msg = []
            for i, todo in enumerate(todos, start=1):
                msg.append('\n{}{}: {}'.format(
                    i,
                    ' (server)' if todo.channel_id is None and scope == TodoScope.CHANNEL else '',
                    todo.value)
                )

            if len(msg) == 0:
                msg.append(preferences.language.get_string('todo/add').format(
                    prefix=preferences.prefix, command=command))

            s = ''
            for item in msg:
                if len(item) + len(s) < 2048:
                    s += item
                else:
                    await message.channel.send(
                        embed=discord.Embed(title='{} TODO'.format(location_name), description=s))
                    s = ''

            if len(s) > 0:
                await message.channel.send(embed=discord.Embed(title='{} TODO'.format(location_name), description=s))

        elif len(splits) >= 2:
            if splits[0] == 'add':
                s = ' '.join(splits[1:])

                todo = Todo(value=s, guild=guild, user=preferences.user, channel=channel)
                session.add(todo)
                await message.channel.send(preferences.language.get_string('todo/added').format(name=s))

            elif splits[0] == 'remove':
                try:
                    pos = int(splits[1]) - 1

                    if pos < 0:
                        raise IndexError

                    else:
                        todo = session.query(Todo).filter(Todo.id == todos[pos].id).first()
                        session.query(Todo).filter(Todo.id == todos[pos].id).delete(
                            synchronize_session='fetch')

                        await message.channel.send(preferences.language.get_string('todo/removed').format(todo.value))

                except ValueError:
                    await message.channel.send(
                        preferences.language.get_string('todo/error_value').format(
                            prefix=preferences.prefix, command=command))

                except IndexError:
                    await message.channel.send(preferences.language.get_string('todo/error_index'))

            else:
                await message.channel.send(
                    preferences.language.get_string('todo/help').format(prefix=preferences.prefix, command=command))

        else:
            if stripped == 'clear':
                await message.channel.send(
                    preferences.language.get_string('todo/confirm').format(
                        todos.count(),
                        location_name.lower()
                    )
                )

                try:
                    confirm = await client.wait_for('message',
                                                    check=lambda m:
                                                        m.author == message.author and m.channel == message.channel,
                                                    timeout=30)

                except asyncio.exceptions.TimeoutError:
                    pass

                else:
                    if confirm.content.lower() == 'yes':
                        todos.delete(synchronize_session='fetch')
                        await message.channel.send(preferences.language.get_string('todo/cleared'))

                    else:
                        await message.channel.send(preferences.language.get_string('todo/canceled'))

            else:
                await message.channel.send(
                    preferences.language.get_string('todo/help').format(prefix=preferences.prefix, command=command))

        session.commit()

    @staticmethod
    async def delete(message, _stripped, preferences):
        if message.guild is not None:
            channels = preferences.guild.channels
            reminders = itertools.chain(*[c.reminders for c in channels])

        else:
            reminders = preferences.user.channel.reminders

        await message.channel.send(preferences.language.get_string('del/listing'))

        enumerated_reminders = [x for x in enumerate(reminders, start=1)]

        s = ''
        for count, reminder in enumerated_reminders:
            string = '''**{}**: '{}' *{}* at {}\n'''.format(
                count,
                reminder.message_content(),
                reminder.channel,
                datetime.fromtimestamp(reminder.time, pytz.timezone(preferences.timezone)).strftime(
                    '%Y-%m-%d %H:%M:%S'))

            if len(s) + len(string) > 2000:
                await message.channel.send(s)
                s = string
            else:
                s += string

        if s:
            await message.channel.send(s)

        await message.channel.send(preferences.language.get_string('del/listed'))

        try:
            num = await client.wait_for('message',
                                        check=lambda m: m.author == message.author and m.channel == message.channel,
                                        timeout=30)

        except asyncio.exceptions.TimeoutError:
            pass

        else:
            num_content = num.content.replace(',', ' ')
            removal_ids: typing.Set[int] = set()

            try:
                nums = set([int(x) for x in num_content.split(' ') if len(x) > 0])

            except ValueError:
                pass

            else:
                for count, reminder in enumerated_reminders:
                    if count in nums:
                        removal_ids.add(reminder.id)
                        nums.remove(count)

                if message.guild is not None:
                    deletion_event = Event(
                        event_name='delete', bulk_count=len(removal_ids), guild=preferences.guild,
                        user=preferences.user)
                    session.add(deletion_event)

                session.query(Reminder).filter(Reminder.id.in_(removal_ids)).delete(synchronize_session='fetch')
                session.commit()

            await message.channel.send(preferences.language.get_string('del/count').format(len(removal_ids)))

    @staticmethod
    async def look(message, stripped, preferences):

        def relative_time(t):
            days, seconds = divmod(int(t - unix_time()), 86400)
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)

            sections = []

            for var, name in zip((days, hours, minutes, seconds), ('days', 'hours', 'minutes', 'seconds')):
                if var > 0:
                    sections.append('{} {}'.format(var, name))

            return ', '.join(sections)

        def absolute_time(t):
            return datetime.fromtimestamp(t, pytz.timezone(preferences.timezone)).strftime('%Y-%m-%d %H:%M:%S')

        r = re.search(r'(\d+)', stripped)

        limit: typing.Optional[int] = None
        if r is not None:
            limit = int(r.groups()[0])

        if 'enabled' in stripped:
            show_disabled = False
        else:
            show_disabled = True

        if 'time' in stripped:
            time_func = absolute_time

        else:
            time_func = relative_time

        if message.guild is None:
            channel = preferences.user.channel
            new = False

        else:
            discord_channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel

            channel, new = Channel.get_or_create(discord_channel)

        if new:
            await message.channel.send(preferences.language.get_string('look/no_reminders'))

        else:
            reminder_query = channel.reminders.order_by(Reminder.time)

            if not show_disabled:
                reminder_query = reminder_query.filter(Reminder.enabled)

            if limit is not None:
                reminder_query = reminder_query.limit(limit)

            if reminder_query.count() > 0:
                if limit is not None:
                    await message.channel.send(preferences.language.get_string('look/listing_limited').format(
                        reminder_query.count()))

                else:
                    await message.channel.send(preferences.language.get_string('look/listing'))

                s = ''
                for reminder in reminder_query:
                    string = '\'{}\' *{}* **{}** {}\n'.format(
                        reminder.message_content(),
                        preferences.language.get_string('look/inter'),
                        time_func(reminder.time),
                        '' if reminder.enabled else '`disabled`')

                    if len(s) + len(string) > 2000:
                        await message.channel.send(s)
                        s = string
                    else:
                        s += string

                await message.channel.send(s)

            else:
                await message.channel.send(preferences.language.get_string('look/no_reminders'))

    @staticmethod
    async def offset_reminders(message, stripped, preferences):

        if message.guild is None:
            reminders = preferences.user.channel.reminders
        else:
            reminders = itertools.chain(*[channel.reminders for channel in preferences.guild.channels])

        time_parser = TimeExtractor(stripped, preferences.timezone)

        try:
            time = time_parser.extract_displacement()

        except InvalidTime:
            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('offset/invalid_time')))

        else:
            if time == 0:
                await message.channel.send(embed=discord.Embed(
                    description=preferences.language.get_string('offset/help').format(prefix=preferences.prefix)))

            else:
                c = 0
                for r in reminders:
                    c += 1
                    r.time += time

                if message.guild is not None:
                    edit_event = Event(
                        event_name='edit', bulk_count=c, guild=preferences.guild, user=preferences.user)
                    session.add(edit_event)

                session.commit()

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('offset/success').format(time)))

    @staticmethod
    async def nudge_channel(message, stripped, preferences):

        time_parser = TimeExtractor(stripped, preferences.timezone)

        try:
            t = time_parser.extract_displacement()

        except InvalidTime:
            await message.channel.send(embed=discord.Embed(
                description=preferences.language.get_string('nudge/invalid_time')))

        else:
            if 2 ** 15 > t > -2 ** 15:
                channel, _ = Channel.get_or_create(message.channel)

                channel.nudge = t

                session.commit()

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('nudge/success').format(t)))

            else:
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('nudge/invalid_time')))

    @staticmethod
    async def pause_channel(message, stripped, preferences):

        channel, _ = Channel.get_or_create(message.channel)

        if len(stripped) > 0:
            # argument provided for time
            time_parser = TimeExtractor(stripped, preferences.timezone)

            try:
                t = time_parser.extract_displacement()

            except InvalidTime:
                await message.channel.send(embed=discord.Embed(
                    description=preferences.language['pause/invalid_time']))

            else:
                channel.paused = True
                channel.paused_until = datetime.now() + timedelta(seconds=t)

                display = channel.paused_until \
                    .astimezone(pytz.timezone(preferences.timezone)) \
                    .strftime('%Y-%m-%d, %H:%M:%S')

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language['pause/paused_until'].format(display)))

        else:
            # otherwise toggle the paused status and clear the time
            channel.paused = not channel.paused
            channel.paused_until = None

            if channel.paused:
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language['pause/paused_indefinite']))

            else:
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language['pause/unpaused']))


intents = discord.Intents.none()
intents.guilds = True
intents.messages = True

config: Config = Config(filename='config.ini')

if (config.min_shard and config.max_shard and config.shard_count) is not None:
    client = BotClient(
        shard_ids=[x for x in range(config.min_shard, config.max_shard + 1)],
        shard_count=config.shard_count,
        max_messages=None,
        intents=intents,
        guild_subscriptions=False,
        allowed_mentions=discord.AllowedMentions.none(),
        fetch_offline_members=False)

else:
    client = BotClient(
        max_messages=None,
        intents=intents,
        guild_subscriptions=False,
        allowed_mentions=discord.AllowedMentions.none(),
        fetch_offline_members=False)

client.run(config.token)
