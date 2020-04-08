import asyncio
import concurrent.futures
import itertools
import re
from datetime import datetime
from functools import partial
from json import dumps as json_dump
from time import time as unix_time

import aiohttp
import dateparser
import pytz

from config import Config
from consts import *
from models import Reminder, Todo, Timer, CommandRestriction, Message, Channel
from passers import *
from time_extractor import TimeExtractor, InvalidTime


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        self.start_time: float = unix_time()

        self.commands: typing.Dict[str, Command] = {

            'help': Command(self.help),
            'info': Command(self.info),
            'donate': Command(self.donate),

            'prefix': Command(self.change_prefix, False, PermissionLevels.RESTRICTED),
            'blacklist': Command(self.blacklist, False, PermissionLevels.RESTRICTED),
            # TODO: remodel restriction table with FKs for role table
            'restrict': Command(self.restrict, False, PermissionLevels.RESTRICTED),

            'timezone': Command(self.set_timezone),
            'lang': Command(self.set_language),
            'clock': Command(self.clock),

            'offset': Command(self.offset_reminders, True, PermissionLevels.RESTRICTED),
            'nudge': Command(self.nudge_channel, True, PermissionLevels.RESTRICTED),

            'natural': Command(self.natural, True, PermissionLevels.MANAGED),
            'n': Command(self.natural, True, PermissionLevels.MANAGED),
            'remind': Command(self.remind, True, PermissionLevels.MANAGED),
            'r': Command(self.remind, True, PermissionLevels.MANAGED),
            'interval': Command(self.remind, True, PermissionLevels.MANAGED),
            # TODO: remodel timer table with FKs for guild table
            'timer': Command(self.timer, False, PermissionLevels.MANAGED),
            'del': Command(self.delete, True, PermissionLevels.MANAGED),
            'look': Command(self.look, True, PermissionLevels.MANAGED),

            'todos': Command(self.todo, False, PermissionLevels.MANAGED),
            'todo': Command(self.todo),

            'ping': Command(self.time_stats),
        }

        # used in restrict command for filtration
        self.max_command_length = max(len(x) for x in self.commands.keys())

        self.config: Config = Config()

        self.executor: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor()
        self.c_session: typing.Optional[aiohttp.ClientSession] = None

        super(BotClient, self).__init__(*args, **kwargs)

    async def do_blocking(self, method):
        # perform a long running process within a threadpool
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]

    async def find_and_create_member(self, member_id: int, context_guild: typing.Optional[discord.Guild]) \
            -> typing.Optional[User]:
        u: User = session.query(User).filter(User.user == member_id).first()

        if u is None and context_guild is not None:
            m = context_guild.get_member(member_id) or self.get_user(member_id)

            if m is not None:
                u = User(user=m.id, name='{}'.format(m), dm_channel=(await m.create_dm()).id)

                session.add(u)
                session.commit()

        return u

    async def is_patron(self, member_id) -> bool:
        if self.config.patreon:

            url = 'https://discordapp.com/api/v6/guilds/{}/members/{}'.format(self.config.patreon_server, member_id)

            head = {
                'authorization': 'Bot {}'.format(self.config.token),
                'content-type': 'application/json'
            }

            async with self.c_session.get(url, headers=head) as resp:

                if resp.status == 200:
                    member = await resp.json()
                    roles = [int(x) for x in member['roles']]

                else:
                    return False

            return self.config.donor_role in roles

        else:
            return True

    @staticmethod
    async def welcome(guild, *_):

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding reminder-bot! To begin, type `$help`!')
                break

            else:
                continue

    async def time_stats(self, message, *_):
        uptime: float = unix_time() - self.start_time

        message_ts: float = message.created_at.timestamp()

        m: discord.Message = await message.channel.send('.')

        ping: float = m.created_at.timestamp() - message_ts

        await m.edit(content='''
        Uptime: {}s
        Ping: {}ms
        '''.format(round(uptime), round(ping * 1000)))

    async def on_error(self, *a, **k):
        session.rollback()
        raise

    async def on_ready(self):

        print('Logged in as')
        print(self.user.name)
        print(self.user.id)

        self.c_session: aiohttp.client.ClientSession = aiohttp.ClientSession()

        if self.config.patreon:
            print('Patreon is enabled. Will look for servers {}'.format(self.config.patreon_server))

        print('Local timezone set to *{}*'.format(self.config.localzone))

    async def on_guild_join(self, guild):
        await self.send()

        await self.welcome(guild)

    async def send(self):
        if self.config.dbl_token:
            guild_count = len(self.guilds)

            dump = json_dump({
                'server_count': guild_count
            })

            head = {
                'authorization': self.config.dbl_token,
                'content-type': 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with self.c_session.post(url, data=dump, headers=head) as resp:
                print('returned {0.status} for {1}'.format(resp, dump))

    # noinspection PyBroadException
    async def on_message(self, message):

        channel = None

        if message.author.bot or message.content is None:
            return

        if message.guild is not None:
            if session.query(Guild).filter(Guild.guild == message.guild.id).first() is None:

                guild = Guild(guild=message.guild.id)

                session.add(guild)

                for channel in message.guild.text_channels:
                    db_channel = Channel(channel=channel.id, name=channel.name, guild=guild)
                    session.add(db_channel)

                try:
                    session.commit()
                except:
                    return

            channel, just_created = await Channel.get_or_create(message.channel)

            if not just_created:
                channel.name = message.channel.name

        guild = None if message.guild is None else session.query(Guild).filter(Guild.guild == message.guild.id).first()
        user, just_created = await User.get_or_create(message.author)

        if not just_created:
            await user.update_details(message.author)

        if user not in guild.users:
            guild.users.append(user)

        session.commit()

        if message.guild is None or message.channel.permissions_for(message.guild.me).send_messages:
            try:
                if await self.get_cmd(message, guild, channel, user):
                    print('Command: {}'.format(message.content))

            except discord.errors.Forbidden:
                await message.channel.send('Insufficient permissions for command')

    async def get_cmd(self,
                      message: discord.Message,
                      guild: Guild,
                      channel: typing.Optional[Channel],
                      user: User) -> bool:

        info: Preferences = Preferences(guild, user)
        prefix: str = info.prefix

        # noinspection PyUnusedLocal
        command: str = ''
        # noinspection PyUnusedLocal
        stripped: str = ''

        if message.content[0:len(prefix)] == prefix:

            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:

            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        elif isinstance(message.channel, discord.DMChannel):

            command = message.content.split(' ')[0]
            stripped = message.content[len(command) + 1:]

        else:
            return False

        if command in self.commands.keys():
            if guild is not None and not message.content.startswith(
                    ('{}help'.format(prefix), '{}blacklist'.format(prefix))):

                if channel.blacklisted:
                    await message.channel.send(embed=discord.Embed(description=info.language.get_string('blacklisted')))
                    return False

            command_form: Command = self.commands[command]

            if command_form.allowed_dm or guild is not None:

                permission_check_status: bool = True

                if guild is not None and command_form.permission_level == PermissionLevels.RESTRICTED:
                    if not message.author.guild_permissions.manage_guild:
                        permission_check_status = False

                        await message.channel.send(info.language.get_string('no_perms_restricted'))

                elif guild is not None and command_form.permission_level == PermissionLevels.MANAGED:
                    # noinspection PyUnresolvedReferences
                    restrict = guild.command_restrictions \
                        .filter(CommandRestriction.command == command) \
                        .filter(CommandRestriction.role.in_([x.id for x in message.author.roles]))

                    if restrict.count() == 0 and not message.author.guild_permissions.manage_messages:
                        permission_check_status = False

                        await message.channel.send(
                            info.language.get_string('no_perms_managed').format(prefix=info.prefix))

                if permission_check_status:
                    if guild is not None and not message.guild.me.guild_permissions.manage_webhooks:
                        await message.channel.send(info.language.get_string('no_perms_webhook'))
                        return False

                    elif guild is not None and not message.channel.permissions_for(message.guild.me).embed_links:
                        await message.channel.send(info.language.get_string('no_perms_embed_links'))
                        return False

                    await command_form.func(message, stripped, info)
                    return True

                else:
                    return False

            else:
                return False

        else:
            return False

    @staticmethod
    async def help(message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(description=preferences.language.get_string('help')))

    async def info(self, message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(
            description=preferences.language.get_string('info').format(prefix=preferences.prefix, user=self.user.name)))

    @staticmethod
    async def donate(message, _stripped, preferences):
        await message.channel.send(embed=discord.Embed(description=preferences.language.get_string('donate')))

    @staticmethod
    async def change_prefix(message, stripped, preferences):

        if stripped:

            stripped += ' '
            new = stripped[:stripped.find(' ')]

            if len(new) > 5:
                await message.channel.send(preferences.language.get_string('prefix/too_long'))

            else:
                preferences.prefix = new

                await message.channel.send(preferences.language.get_string('prefix/success').format(
                    prefix=preferences.prefix))

        else:
            await message.channel.send(preferences.language.get_string('prefix/no_argument').format(
                prefix=preferences.prefix))

        session.commit()

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

            await message.channel.send(embed=discord.Embed(description=new_lang.get_string('lang/set_p')))

            session.commit()

        else:
            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('lang/invalid').format(
                    '\n'.join(
                        ['{} ({})'.format(lang.name.title(), lang.code.upper()) for lang in session.query(Language)])
                    )
                )
            )

    @staticmethod
    async def clock(message, _stripped, preferences):

        t = datetime.now(pytz.timezone(preferences.timezone))

        await message.channel.send(preferences.language.get_string('clock/time').format(t.strftime('%H:%M:%S')))

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
            'TO_TIMEZONE': self.config.localzone,
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
                                                                 offset=int(result.time - unix_time()),
                                                                 min_interval=MIN_INTERVAL, max_time=MAX_TIME_DAYS)

            await message.channel.send(embed=discord.Embed(description=response))

        else:
            successes: int = len([r for r in responses if r.status == CreateReminderResponse.OK])

            await message.channel.send(
                embed=discord.Embed(description=server.language.get_string('natural/bulk_set').format(successes)))

    async def remind(self, message, stripped, server):

        args = stripped.split(' ')
        is_interval = message.content[1] == 'i'

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

                    response = server.language.get_string(REMIND_STRINGS[result.status]).format(
                        location=result.location.mention, offset=int(result.time - unix_time()),
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

        # noinspection PyUnusedLocal
        discord_channel: typing.Optional[typing.Union[discord.TextChannel, DMChannelId]] = None

        # command fired inside a guild
        if message.guild is not None:
            discord_channel = message.guild.get_channel(location)

            if discord_channel is not None:  # if not a DM reminder

                channel, _ = await Channel.get_or_create(discord_channel)

                time += channel.nudge

            else:
                user = await self.find_and_create_member(location, message.guild)

                if user is None or user.dm_channel is None:
                    return ReminderInformation(CreateReminderResponse.INVALID_TAG)

                discord_channel = DMChannelId(user.dm_channel, user.user)

        # command fired in a DM; only possible target is the DM itself
        else:
            user, _ = await User.get_or_create(message.author)
            discord_channel = DMChannelId(user.dm_channel, user.user)

        if interval is not None:
            if MIN_INTERVAL > interval:
                return ReminderInformation(CreateReminderResponse.SHORT_INTERVAL)

            elif interval > MAX_TIME:
                return ReminderInformation(CreateReminderResponse.LONG_INTERVAL)

            else:
                # noinspection PyArgumentList
                reminder = Reminder(
                    message=Message(content=text),
                    channel=channel,
                    user=user,
                    time=time,
                    enabled=True,
                    method=method,
                    interval=interval)
                session.add(reminder)
                session.commit()

        else:
            # noinspection PyArgumentList
            r = Reminder(
                message=Message(content=text),
                channel=channel,
                user=user,
                time=time,
                enabled=True,
                method=method)
            session.add(r)
            session.commit()

        return ReminderInformation(CreateReminderResponse.OK, channel=discord_channel, time=time)

    @staticmethod
    async def timer(message, stripped, preferences):

        owner: int = message.guild.id

        if message.guild is None:
            owner = message.author.id

        if stripped == 'list':
            timers = session.query(Timer).filter(Timer.owner == owner)

            e = discord.Embed(title='Timers')
            for timer in timers:
                delta = int(unix_time() - timer.start_time)
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
                await message.channel.send(preferences.language.get_string('timer/deleted'))

                session.commit()

        else:
            await message.channel.send(preferences.language.get_string('timer/help'))

    @staticmethod
    async def blacklist(message, _, preferences):

        target_channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel

        channel, _ = await Channel.get_or_create(target_channel)

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
                                ['<@&{}> can use `{}`'.format(r.role, r.command)
                                    for r in preferences.command_restrictions]
                            )
                        )
                    )
                )

            else:
                # only a role is given so delete all the settings for this role
                preferences.command_restrictions.filter(CommandRestriction.role == int(role_tag.group(1))).delete(
                    synchronize_session='fetch')
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('restrict/disabled')))

        elif role_tag is None:
            # misused- show help
            await message.channel.send(embed=discord.Embed(
                description=preferences.language.get_string('restrict/help')))

        else:
            # enable permissions for role for selected commands
            role_id: int = int(role_tag.group(1))

            for command in filter(lambda x: len(x) <= 9, args):
                c: typing.Optional[Command] = self.commands.get(command)

                if c is not None and c.permission_level == PermissionLevels.MANAGED:
                    q = preferences.command_restrictions \
                        .filter(CommandRestriction.command == command) \
                        .filter(CommandRestriction.role == role_id)

                    if q.first() is None:
                        new_restriction = CommandRestriction(guild_id=message.guild.id, command=command, role=role_id)

                        session.add(new_restriction)

                else:
                    await message.channel.send(embed=discord.Embed(
                        description=preferences.language.get_string('restrict/failure').format(command=command)))

            await message.channel.send(embed=discord.Embed(
                description=preferences.language.get_string('restrict/enabled')))

        session.commit()

    @staticmethod
    async def todo(message, stripped, preferences):
        if 'todos' in message.content.split(' ')[0]:
            location = preferences.guild
            name = message.guild.name
            command = 'todos'
        else:
            location = preferences.user
            name = message.author.name
            command = 'todo'

        todos = location.todo_list

        splits = stripped.split(' ')

        if len(splits) == 1 and splits[0] == '':
            msg = ['\n{}: {}'.format(i, todo.value) for i, todo in enumerate(todos, start=1)]
            if len(msg) == 0:
                msg.append(preferences.language.get_string('todo/add').format(
                    prefix=preferences.prefix, command=command))

            s = ''
            for item in msg:
                if len(item) + len(s) < 2048:
                    s += item
                else:
                    await message.channel.send(
                        embed=discord.Embed(title='{} TODO'.format('Server' if command == 'todos' else 'Your', name),
                                            description=s))
                    s = ''

            if len(s) > 0:
                await message.channel.send(
                    embed=discord.Embed(title='{} TODO'.format('Server' if command == 'todos' else 'Your', name),
                                        description=s))

        elif len(splits) >= 2:
            if splits[0] == 'add':
                a = ' '.join(splits[1:])

                todo = Todo(value=a)
                location.todo_list.append(todo)
                await message.channel.send(preferences.language.get_string('todo/added').format(name=a))

            elif splits[0] == 'remove':
                try:
                    a = session.query(Todo).filter(Todo.id == todos[int(splits[1]) - 1].id).first()
                    session.query(Todo).filter(Todo.id == todos[int(splits[1]) - 1].id).delete(
                        synchronize_session='fetch')

                    await message.channel.send(preferences.language.get_string('todo/removed').format(a.value))

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
                todos.clear()
                await message.channel.send(preferences.language.get_string('todo/cleared'))

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
            reminders = preferences.user.reminders

        await message.channel.send(preferences.language.get_string('del/listing'))

        enumerated_reminders = [x for x in enumerate(reminders, start=1)]

        s = ''
        for count, reminder in enumerated_reminders:
            string = '''**{}**: '{}' *{}*\n'''.format(
                count,
                reminder.message_content(),
                reminder.channel)

            if len(s) + len(string) > 2000:
                await message.channel.send(s, allowed_mentions=NoMention)
                s = string
            else:
                s += string

        if s:
            await message.channel.send(s, allowed_mentions=NoMention)

        await message.channel.send(preferences.language.get_string('del/listed'))

        num = await client.wait_for('message',
                                    check=lambda m: m.author == message.author and m.channel == message.channel)

        num_content = num.content.replace(',', ' ')

        nums = set([int(x) for x in re.findall(r'(\d+)(?:\s|$)', num_content)])

        removal_ids: typing.Set[int] = set()

        for count, reminder in enumerated_reminders:
            if count in nums:
                removal_ids.add(reminder.id)
                nums.remove(count)

        session.query(Reminder).filter(Reminder.id.in_(removal_ids)).delete(synchronize_session='fetch')
        session.commit()

        await message.channel.send(preferences.language.get_string('del/count').format(len(removal_ids)))

    @staticmethod
    async def look(message, stripped, preferences):

        r = re.search(r'(\d+)', stripped)

        limit: typing.Optional[int] = None
        if r is not None:
            limit = int(r.groups()[0])

        if 'enabled' in stripped:
            show_disabled = False
        else:
            show_disabled = True

        discord_channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel

        channel, new = await Channel.get_or_create(discord_channel)

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
                        datetime.fromtimestamp(reminder.time, pytz.timezone(preferences.timezone)).strftime(
                            '%Y-%m-%d %H:%M:%S'),
                        '' if reminder.enabled else '`disabled`')

                    if len(s) + len(string) > 2000:
                        await message.channel.send(s, allowed_mentions=NoMention)
                        s = string
                    else:
                        s += string

                await message.channel.send(s, allowed_mentions=NoMention)

            else:
                await message.channel.send(preferences.language.get_string('look/no_reminders'))

    @staticmethod
    async def offset_reminders(message, stripped, preferences):

        if message.guild is None:
            reminders = preferences.user.reminders
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
                for r in reminders:
                    r.time += time

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
            channel, _ = await Channel.get_or_create(message.channel)

            channel.nudge = t

            session.commit()

            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('nudge/success').format(t)))


client = BotClient(max_messages=100, guild_subscriptions=False, fetch_offline_members=False)
client.run(client.config.token)
