import asyncio
import concurrent.futures
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
from models import Reminder, Todo, Blacklist, Timer, ChannelNudge, \
    CommandRestriction, Message
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

    async def find_member(self, member_id: int, context_guild: typing.Optional[discord.Guild]):
        u: User = session.query(User).get(member_id)

        if u is None and context_guild is not None:
            m = context_guild.get_member(member_id) or self.get_user(member_id)

            if m is not None:
                u = User(user=m.id, name='{}'.format(m), dm_channel=(await m.create_dm()).id)

                session.add(u)
                session.commit()

        return u

    async def clean_string(self, string: str, guild: discord.Guild) -> str:
        if guild is None:
            return string

        else:
            parts = ['']
            for char in string:
                if char in '<>':
                    parts.append(char)
                else:
                    parts[-1] += char

            new = []
            for piece in parts:
                new_piece = piece
                if len(piece) > 3 and piece[1] == '@' and all(x in '0123456789' for x in piece[3:]):
                    if piece[2] in '0123456789!':
                        uid = int(''.join(x for x in piece if x in '0123456789'))
                        user = await self.find_member(uid, guild)
                        new_piece = '`@{}`'.format(user)

                    elif piece[2] == '&':
                        rid = int(''.join(x for x in piece if x in '0123456789'))
                        role = guild.get_role(rid)
                        new_piece = '`@@{}`'.format(role)

                new.append(new_piece)

            return ''.join(new).replace('@everyone', '`@everyone`').replace('@here', '`@here`')

    async def is_patron(self, memberid) -> bool:
        if self.config.patreon:

            url = 'https://discordapp.com/api/v6/guilds/{}/members/{}'.format(self.config.patreon_server, memberid)

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

        if message.author.bot or message.content is None:
            return

        if session.query(User).get(message.author.id) is None:

            user = User(user=message.author.id, name='{}'.format(message.author),
                        dm_channel=(await message.author.create_dm()).id)

            session.add(user)
            try:
                session.commit()

            except:
                return

        if message.guild is not None and session.query(Guild).get(message.guild.id) is None:

            server = Guild(guild=message.guild.id)

            session.add(server)
            try:
                session.commit()

            except:
                return

        server = None if message.guild is None else session.query(Guild).get(message.guild.id)
        user = session.query(User).get(message.author.id)

        user.name = '{}'.format(message.author)

        if user.dm_channel is None:
            user.dm_channel = (await message.author.create_dm()).id

        if message.guild is None or message.channel.permissions_for(message.guild.me).send_messages:
            try:
                if await self.get_cmd(message, server, user):
                    print('Command: {}'.format(message.content))

            except discord.errors.Forbidden:
                await message.channel.send('Insufficient permissions for command')

    async def get_cmd(self, message, server, user) -> bool:

        info: Preferences = Preferences(server, user)
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
            if server is not None and not message.content.startswith(
                    ('{}help'.format(prefix), '{}blacklist'.format(prefix))):

                channel = session.query(Blacklist).filter(Blacklist.channel == message.channel.id)

                if channel.count() > 0:
                    await message.channel.send(embed=discord.Embed(description=info.language.get_string('blacklisted')))
                    return False

            command_form: Command = self.commands[command]

            if command_form.allowed_dm or server is not None:

                permission_check_status: bool = True

                if server is not None and command_form.permission_level == PermissionLevels.RESTRICTED:
                    if not message.author.guild_permissions.manage_guild:
                        permission_check_status = False

                        await message.channel.send(info.language.get_string('no_perms_restricted'))

                elif server is not None and command_form.permission_level == PermissionLevels.MANAGED:
                    restrict = server.command_restrictions \
                        .filter(CommandRestriction.command == command) \
                        .filter(CommandRestriction.role.in_([x.id for x in message.author.roles]))

                    if restrict.count() == 0 and not message.author.guild_permissions.manage_messages:
                        permission_check_status = False

                        await message.channel.send(
                            info.language.get_string('no_perms_managed').format(prefix=info.prefix))

                if permission_check_status:
                    if server is not None and not message.guild.me.guild_permissions.manage_webhooks:
                        await message.channel.send(info.language.get_string('no_perms_webhook'))
                        return False

                    elif server is not None and not message.channel.permissions_for(message.guild.me).embed_links:
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
        nudge_channel: ChannelNudge = session.query(ChannelNudge).filter(
            ChannelNudge.channel == location).first()  # check if it's being nudged

        ut: float = unix_time()

        if nudge_channel is not None:
            time += nudge_channel.time

        if time > ut + MAX_TIME:
            return ReminderInformation(CreateReminderResponse.LONG_TIME)

        elif time < ut:

            if (ut - time) < 10:
                time = int(ut)

            else:
                return ReminderInformation(CreateReminderResponse.PAST_TIME)

        url: typing.Optional[str] = None
        # noinspection PyUnusedLocal
        channel: typing.Optional[typing.Union[discord.TextChannel, DMChannelId]] = None

        if message.guild is not None:
            channel = message.guild.get_channel(location)

            if channel is not None:  # if not a DM reminder

                hooks = [x for x in await channel.webhooks() if x.user.id == self.user.id]
                hook = hooks[0] if len(hooks) > 0 else await channel.create_webhook(name='Reminders')
                url = hook.url

            else:
                member = await self.find_member(location, message.guild)

                if member is None or member.dm_channel is None:
                    return ReminderInformation(CreateReminderResponse.INVALID_TAG)

                else:
                    channel = DMChannelId(member.dm_channel, member.user)

        else:
            channel = message.channel

        if interval is not None:
            if MIN_INTERVAL > interval:
                return ReminderInformation(CreateReminderResponse.SHORT_INTERVAL)

            elif interval > MAX_TIME:
                return ReminderInformation(CreateReminderResponse.LONG_INTERVAL)

            else:
                reminder = Reminder(
                    message=Message(content=text),
                    channel=channel.id,
                    time=time,
                    webhook=url,
                    enabled=True,
                    method=method,
                    interval=interval)
                session.add(reminder)
                session.commit()

        else:
            r = Reminder(
                message=Message(content=text),
                channel=channel.id,
                time=time,
                webhook=url,
                enabled=True,
                method=method)
            session.add(r)
            session.commit()

        return ReminderInformation(CreateReminderResponse.OK, channel=channel, time=time)

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
    async def blacklist(message, _stripped, preferences):

        if len(message.channel_mentions) > 0:
            disengage_all = True

            all_channels = set(
                [x.channel for x in session.query(Blacklist).filter(Blacklist.guild_id == message.guild.id)])
            c = set([x.id for x in message.channel_mentions])

            for mention in message.channel_mentions:
                if mention.id not in all_channels:
                    disengage_all = False

            if disengage_all:
                channels = c & all_channels
                session.query(Blacklist).filter(Blacklist.channel.in_(channels)).delete(synchronize_session='fetch')

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('blacklist/removed_from')))

            else:
                channels = [x for x in c if x not in all_channels]
                for channel in channels:
                    blacklist = Blacklist(channel=channel, guild_id=message.guild.id)
                    session.add(blacklist)

                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('blacklist/added_from')))

        else:
            q = session.query(Blacklist).filter(Blacklist.channel == message.channel.id)

            if q.count() > 0:
                q.delete(synchronize_session='fetch')
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('blacklist/removed')))

            else:
                blacklist = Blacklist(channel=message.channel.id, guild_id=message.guild.id)
                session.add(blacklist)
                await message.channel.send(
                    embed=discord.Embed(description=preferences.language.get_string('blacklist/added')))

        session.commit()

    async def restrict(self, message, stripped, prefs):

        role_tag = re.search(r'<@&([0-9]+)>', stripped)

        args: typing.List[str] = re.findall(r'([a-z]+)', stripped)

        if len(args) == 0:
            if role_tag is None:
                # no parameters given so just show existing
                await message.channel.send(
                    embed=discord.Embed(
                        description=prefs.language.get_string('restrict/allowed').format(
                            '\n'.join(
                                ['<@&{}> can use `{}`'.format(r.role, r.command) for r in prefs.command_restrictions]
                            )
                        )
                    )
                )

            else:
                # only a role is given so delete all the settings for this role
                prefs.command_restrictions.filter(CommandRestriction.role == int(role_tag.group(1))).delete(
                    synchronize_session='fetch')
                await message.channel.send(
                    embed=discord.Embed(description=prefs.language.get_string('restrict/disabled')))

        elif role_tag is None:
            # misused- show help
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('restrict/help')))

        else:
            # enable permissions for role for selected commands
            role_id: int = int(role_tag.group(1))

            for command in filter(lambda x: len(x) <= 9, args):
                c: typing.Optional[Command] = self.commands.get(command)

                if c is not None and c.permission_level == PermissionLevels.MANAGED:
                    q = prefs.command_restrictions \
                        .filter(CommandRestriction.command == command) \
                        .filter(CommandRestriction.role == role_id)

                    if q.first() is None:
                        new_restriction = CommandRestriction(guild_id=message.guild.id, command=command, role=role_id)

                        session.add(new_restriction)

                else:
                    await message.channel.send(embed=discord.Embed(
                        description=prefs.language.get_string('restrict/failure').format(command=command)))

            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('restrict/enabled')))

        session.commit()

    @staticmethod
    async def todo(message, stripped, preferences):
        if 'todos' in message.content.split(' ')[0]:
            location = message.guild.id
            name = message.guild.name
            command = 'todos'
        else:
            location = message.author.id
            name = message.author.name
            command = 'todo'

        todos = session.query(Todo).filter(Todo.owner == location).all()

        splits = stripped.split(' ')

        if len(splits) == 1 and splits[0] == '':
            msg = ['\n{}: {}'.format(i + 1, todo.value) for i, todo in enumerate(todos)]
            if len(msg) == 0:
                msg.append(preferences.language.get_string('todo/add').format(
                    prefix=preferences.prefix, command=command))

            s = ''
            for item in msg:
                if len(item) + len(s) < 2000:
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

                todo = Todo(owner=location, value=a)
                session.add(todo)
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
                session.query(Todo).filter(Todo.owner == location).delete(synchronize_session='fetch')
                await message.channel.send(preferences.language.get_string('todo/cleared'))

            else:
                await message.channel.send(
                    preferences.language.get_string('todo/help').format(prefix=preferences.prefix, command=command))

        session.commit()

    async def delete(self, message, _stripped, preferences):
        if message.guild is not None:
            li = [ch.id for ch in message.guild.channels]  # get all channels and their ids in the current server
        else:
            li = [message.channel.id]

        await message.channel.send(preferences.language.get_string('del/listing'))

        n = 1

        reminders = session.query(Reminder).filter(Reminder.channel.in_(li)).all()

        s = ''
        for reminder in reminders:
            string = '''**{}**: '{}' *<#{}>*\n'''.format(
                n,
                await self.clean_string(reminder.message_content(), message.guild),
                reminder.channel)

            if len(s) + len(string) > 2000:
                await message.channel.send(s)
                s = string
            else:
                s += string

            n += 1

        if s:
            await message.channel.send(s)

        await message.channel.send(preferences.language.get_string('del/listed'))

        num = await client.wait_for('message',
                                    check=lambda m: m.author == message.author and m.channel == message.channel)
        nums = [n.strip() for n in num.content.split(',')]

        deletion_count: int = 0
        for i in nums:
            try:
                i = int(i) - 1
                if i < 0:
                    continue

                session.query(Reminder).filter(Reminder.id == reminders[i].id).delete(synchronize_session='fetch')

                print('Deleted reminder')
                deletion_count += 1

            except ValueError:
                continue
            except IndexError:
                continue

        await message.channel.send(preferences.language.get_string('del/count').format(deletion_count))
        session.commit()

    async def look(self, message, stripped, prefs):

        r = re.search(r'(\d+)', stripped)

        limit: typing.Optional[int] = None
        if r is not None:
            limit = int(r.groups()[0])

        channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel
        channel = channel.id

        if limit is not None:
            reminders = session.query(Reminder).filter(Reminder.channel == channel).order_by(Reminder.time).limit(limit)
        else:
            reminders = session.query(Reminder).filter(Reminder.channel == channel).order_by(Reminder.time)

        if reminders.count() > 0:
            if limit is not None:
                await message.channel.send(prefs.language.get_string('look/listing_limited').format(reminders.count()))

            else:
                await message.channel.send(prefs.language.get_string('look/listing'))

            s = ''
            for reminder in reminders:
                string = '\'{}\' *{}* **{}**\n'.format(
                    await self.clean_string(reminder.message_content(), message.guild),
                    prefs.language.get_string('look/inter'),
                    datetime.fromtimestamp(reminder.time, pytz.timezone(prefs.timezone)).strftime('%Y-%m-%d %H:%M:%S'))

                if len(s) + len(string) > 2000:
                    await message.channel.send(s)
                    s = string
                else:
                    s += string

            await message.channel.send(s)

        else:
            await message.channel.send(prefs.language.get_string('look/no_reminders'))

    @staticmethod
    async def offset_reminders(message, stripped, preferences):

        if message.guild is None:
            channels = [message.channel.id]
        else:
            channels = [x.id for x in message.guild.channels]

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
                reminders = session.query(Reminder).filter(Reminder.channel.in_(channels))

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
            query = session.query(ChannelNudge).filter(ChannelNudge.channel == message.channel.id)

            if query.count() < 1:
                new = ChannelNudge(channel=message.channel.id, time=t)
                session.add(new)

            else:
                query.first().time = t

            session.commit()

            await message.channel.send(
                embed=discord.Embed(description=preferences.language.get_string('nudge/success').format(t)))


client = BotClient(max_messages=100, guild_subscriptions=False, fetch_offline_members=False)
client.run(client.config.token)
