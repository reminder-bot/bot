from models import Reminder, Server, User, Strings, Todo, RoleRestrict, Blacklist, Interval, Timer, session, Language, ChannelNudge
from config import Config
from time_extractor import TimeExtractor
from enums import CreateReminderResponse, PermissionLevels, TimeExtractionTypes
from passers import *
from consts import *

import discord
import pytz
import asyncio
import aiohttp
import dateparser

from datetime import datetime
from time import time as unix_time
import os
from json import dumps as json_dump
import concurrent.futures
from functools import partial
import logging
import secrets
from types import FunctionType
import typing


def start_logger():
    handler = logging.StreamHandler()
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))
    logger.addHandler(handler)

    return logger


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        self.start_time: float = unix_time()

        self.commands: dict = {

            'help' : Command(self.help),
            'info' : Command(self.info),
            'donate' : Command(self.donate),

            'prefix' : Command(self.change_prefix, False, PermissionLevels.RESTRICTED),
            'blacklist' : Command(self.blacklist, False, PermissionLevels.RESTRICTED),
            'restrict' : Command(self.restrict, False, PermissionLevels.RESTRICTED),

            'timezone' : Command(self.set_timezone),
            'lang' : Command(self.set_language),
            'clock' : Command(self.clock),

            'offset' : Command(self.offset_reminders, True, PermissionLevels.RESTRICTED),
            'nudge' : Command(self.nudge_channel, True, PermissionLevels.RESTRICTED),

            'natural' : Command(self.natural, True, PermissionLevels.MANAGED),
            'remind' : Command(self.remind, True, PermissionLevels.MANAGED),
            'interval' : Command(self.remind, True, PermissionLevels.MANAGED),
            'timer' : Command(self.timer, True, PermissionLevels.MANAGED),
            'del' : Command(self.delete, True, PermissionLevels.MANAGED),
            'look' : Command(self.look, True, PermissionLevels.MANAGED),

            'todo' : Command(self.todo),
            'todos' : Command(self.todo, False, PermissionLevels.MANAGED),

            'ping' : Command(self.time_stats),
        }

        self.config: Config = Config()

        self.executor: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor()
        self.csession: aiohttp.ClientSession = None

        super(BotClient, self).__init__(*args, **kwargs)


    async def do_blocking(self, method):
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]


    def create_uid(self, i1: int, i2: int) -> str:
        m: int = i2
        while m > 0:
            i1 *= 10
            m //= 10

        bigint: int = i1 + i2
        full: str = hex(bigint)[2:]
        while len(full) < 64:
            full += secrets.choice(ALL_CHARACTERS)

        return full


    def clean_string(self, string: str, guild: discord.Guild) -> str:
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
                        user = guild.get_member(uid)
                        new_piece = '`@{}`'.format(user)

                    elif piece[2] == '&':
                        rid = int(''.join(x for x in piece if x in '0123456789'))
                        role = guild.get_role(rid)
                        new_piece = '`@@{}`'.format(role)

                new.append(new_piece)

            return ''.join(new)


    async def is_patron(self, memberid, level=0) -> bool:
        if self.config.patreon:

            roles = []
            p_server = self.get_guild(self.config.patreon_server)

            if p_server is None:

                url = 'https://discordapp.com/api/v6/guilds/{}/members/{}'.format(self.config.patreon_server, memberid)

                head = {
                    'authorization': self.config.token,
                    'content-type' : 'application/json'
                }

                async with self.csession.get(url, headers=head) as resp:
                    member = await resp.json()
                    roles = [int(x) for x in member['roles']]

            else:
                for m in p_server.members:
                    if m.id == memberid:
                        roles.extend([r.id for r in m.roles])

            return bool(set([self.config.donor_roles[level]]) & set(roles))

        else:
            return True


    async def welcome(self, guild, *args):

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding reminder-bot! To begin, type `$help`!')
                break
            else:
                continue


    async def time_stats(self, message, *args):
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

        logger.info('Logged in as')
        logger.info(self.user.name)
        logger.info(self.user.id)

        self.csession: aiohttp.client.ClientSession = aiohttp.ClientSession()

        if self.config.patreon:
            logger.info('Patreon is enabled. Will look for servers {}'.format(self.config.patreon_server))


    async def on_guild_remove(self, guild):
        await self.send()


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
                'content-type' : 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with self.csession.post(url, data=dump, headers=head) as resp:
                logger.info('returned {0.status} for {1}'.format(resp, dump))


    async def on_message(self, message):

        if message.author.bot or message.content is None:
            return

        u: User = session.query(User).filter(User.user == message.author.id)

        if u.count() < 1:

            user = User(user=message.author.id)

            session.add(user)
            session.commit()

        if message.guild is not None and session.query(Server).filter_by(server=message.guild.id).first() is None:

            server = Server(server=message.guild.id)

            session.add(server)
            session.commit()

        server = None if message.guild is None else session.query(Server).filter(Server.server == message.guild.id).first()
        user = session.query(User).filter(User.user == message.author.id).first()

        if message.channel.permissions_for(message.guild.me).send_messages:
            if await self.get_cmd(message, server, user):
                logger.info('Command: ' + message.content)


    async def get_cmd(self, message, server, user) -> bool:

        info: Preferences = Preferences(server, user)
        prefix: str = info.prefix

        command: str = ''
        stripped: str = ''

        if message.content[0:len(prefix)] == prefix:

            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:

            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        else:
            return False

        if command in self.commands.keys():
            if server is not None and not message.content.startswith(('{}help'.format(prefix), '{}blacklist'.format(prefix))):

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
                    restrict = session.query(RoleRestrict).filter(RoleRestrict.role.in_([x.id for x in message.author.roles]))

                    if restrict.count() == 0 and not message.author.guild_permissions.manage_messages:
                        permission_check_status = False

                        await message.channel.send(info.language.get_string('no_perms_managed').format(prefix=info.prefix))

                if permission_check_status:
                    m = message.guild.me.guild_permissions
                    if server is not None and not m.manage_webhooks:
                        await message.channel.send(info.language.get_string('no_perms_webhook'))
                        return False

                    await command_form.func(message, stripped, info)
                    return True

                else:
                    return False

            else:
                return False

        else:
            return False


    async def help(self, message, stripped, prefs):
        await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('help')))


    async def info(self, message, stripped, prefs):
        await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('info').format(prefix=prefs.prefix, user=self.user.name)))


    async def donate(self, message, stripped, prefs):
        await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('donate')))


    async def change_prefix(self, message, stripped, prefs):

        if stripped:

            stripped += ' '
            new = stripped[:stripped.find(' ')]

            if len(new) > 5:
                await message.channel.send(prefs.language.get_string('prefix/too_long'))

            else:
                prefs.prefix = new

                await message.channel.send(prefs.language.get_string('prefix/success').format(prefix=prefs.prefix))

        else:
            await message.channel.send(prefs.language.get_string('prefix/no_argument').format(prefix=prefs.prefix))

        session.commit()


    async def set_timezone(self, message, stripped, prefs):

        if message.guild is not None and message.author.guild_permissions.manage_guild:
            s = 'timezone/set'
            admin = True
        else:
            s = 'timezone/set_p'
            admin = False

        if stripped == '':
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('timezone/no_argument').format(prefix=prefs.prefix, timezone=prefs.timezone)))

        else:
            if stripped not in pytz.all_timezones:
                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('timezone/no_timezone')))
            else:
                if admin:
                    prefs.server_timezone = stripped
                else:
                    prefs.timezone = stripped

                d = datetime.now(pytz.timezone(stripped))

                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string(s).format(timezone=stripped, time=d.strftime('%H:%M:%S'))))

                session.commit()


    async def set_language(self, message, stripped, prefs):

        new_lang = session.query(Language).filter((Language.code == stripped.upper()) | (Language.name == stripped.lower())).first()

        if new_lang is not None:
            prefs.language = new_lang.code

            await message.channel.send(embed=discord.Embed(description=new_lang.get_string('lang/set_p')))
    
            session.commit()

        else:
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('lang/invalid').format('\n'.join(['{} ({})'.format(l.name.title(), l.code.upper()) for l in session.query(Language)]))))


    async def clock(self, message, stripped, prefs):

        t = datetime.now(pytz.timezone(prefs.timezone))

        await message.channel.send(prefs.language.get_string('clock/time').format(t.strftime('%H:%M:%S')))


    async def natural(self, message, stripped, server):

        if len(stripped.split(server.language.get_string('natural/send'))) < 2:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('natural/no_argument').format(prefix=server.prefix)))
            return

        err: bool = False
        location_ids: typing.List[int] = [message.channel.id]

        time_crop = stripped.split(server.language.get_string('natural/send'))[0]
        message_crop = stripped.split(server.language.get_string('natural/send'), 1)[1]
        datetime_obj = await self.do_blocking( partial(dateparser.parse, time_crop, settings={'TIMEZONE': server.timezone, 'TO_TIMEZONE': 'UTC'}) )

        if datetime_obj is None:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('natural/invalid_time')))
            return

        if message.guild is not None:
            chan_split = message_crop.split(server.language.get_string('natural/to'))
            if len(chan_split) > 1:

                location_ids: typing.List[int] = [int( ''.join([x for x in z if x in '0123456789']) ) for z in chan_split[-1].split(' ') ]

                message_crop: str = message_crop.rsplit(server.language.get_string('natural/to'), 1)[0]

        interval_split = message_crop.split(server.language.get_string('natural/every'))
        recurring: bool = False
        interval: int = 0

        if len(interval_split) > 1:
            interval = await self.do_blocking( partial(dateparser.parse, '1 ' + interval_split[-1], settings={'TO_TIMEZONE' : 'UTC'}) )

            if interval is None:
                pass

            elif await self.is_patron(message.author.id):
                recurring = True

                interval = abs((interval - datetime.utcnow()).total_seconds())

                message_crop = message_crop.rsplit(server.language.get_string('natural/every'), 1)[0]

            else:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/donor').format(prefix=server.prefix)))
                return

        mtime: float = datetime_obj.timestamp()
        responses: typing.List[ReminderInformation] = []

        for id in location_ids:
            response: ReminderInformation = await self.create_reminder(message, id, message_crop, mtime, interval=interval if recurring else None, method='natural')
            responses.append(response)

        if len(responses) == 1:
            result: CreateReminderResponse = responses[0]
            string: str = NATURAL_STRINGS.get(result.status, REMIND_STRINGS[result.status])

            response = server.language.get_string(string).format(location=result.location.mention, offset=int(result.time - unix_time()), min_interval=MIN_INTERVAL, max_time=MAX_TIME_DAYS)

            await message.channel.send(embed=discord.Embed(description=response))

        else:
            successes: int = len([r for r in responses if r.status == CreateReminderResponse.OK])

            await message.channel.send(embed=discord.Embed(description=server.language.get_string('natural/bulk_set').format(successes)))


    async def remind(self, message, stripped, server):

        args = stripped.split(' ')
        is_interval = message.content[1] == 'i'

        if len(args) < 2:
            if is_interval:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/no_argument').format(prefix=server.prefix)))

            else:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('remind/no_argument').format(prefix=server.prefix)))

        else:
            if is_interval and not await self.is_patron(message.author.id):
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/donor')))

            else:
                channel = message.channel
                interval = None
                scope_id = message.channel.id

                if args[0][0] == '<' and message.guild is not None:
                    arg = args.pop(0)
                    scope_id = int(''.join(x for x in arg if x in '0123456789'))

                t = args.pop(0)
                time_parser = TimeExtractor(t, server.timezone)

                try:
                    mtime = time_parser.extract_exact()
                except:
                    await message.channel.send(embed=discord.Embed(description=server.language.get_string('remind/invalid_time')))
                else:
                    if is_interval:
                        i = args.pop(0)

                        parser = TimeExtractor(i, server.timezone)

                        try:
                            interval = parser.extract_displacement()
                        except:
                            await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/invalid_interval')))
                            return

                    text = ' '.join(args)

                    result = await self.create_reminder(message, scope_id, text, mtime, interval, method='remind')

                    response = server.language.get_string(REMIND_STRINGS[result.status]).format(location=result.location.mention, offset=int(result.time - unix_time()), min_interval=MIN_INTERVAL, max_time=MAX_TIME_DAYS)

                    await message.channel.send(embed=discord.Embed(description=response))


    async def create_reminder(self, message: discord.Message, location: int, text: str, time: int, interval: int=None, method: str='natural') -> ReminderInformation:
        uid: str = self.create_uid(location, message.id) # create a UID

        nudge_channel: ChannelNudge = session.query(ChannelNudge).filter(ChannelNudge.channel == location).first() # check if it's being nudged

        if nudge_channel is not None:
            time += nudge_channel.time

        if time > unix_time() + MAX_TIME:
            return ReminderInformation(CreateReminderResponse.LONG_TIME)

        elif time < unix_time():
            return ReminderInformation(CreateReminderResponse.PAST_TIME)

        url: typing.Optional[str] = None
        channel: typing.Optional[discord.Channel] = None

        if message.guild is not None:
            channel = message.guild.get_channel(location)

            if channel is not None: # if not a DM reminder

                hooks = [x for x in await channel.webhooks() if x.user.id == self.user.id]
                hook = hooks[0] if len(hooks) > 0 else await channel.create_webhook(name='Reminders')
                url = hook.url

                restrict = session.query(RoleRestrict).filter(RoleRestrict.role.in_([x.id for x in message.author.roles]))

            else:
                member = message.guild.get_member(location)

                if member is None:
                    return ReminderInformation(CreateReminderResponse.INVALID_TAG)

                else:
                    await member.create_dm()
                    channel = member.dm_channel

        else:
            channel = message.channel

        if interval is not None:
            if MIN_INTERVAL > interval:
                return ReminderInformation(CreateReminderResponse.SHORT_INTERVAL)

            elif interval > MAX_TIME:
                return ReminderInformation(CreateReminderResponse.LONG_INTERVAL)

            else:
                reminder = Reminder(
                    uid=uid,
                    message=text,
                    channel=channel.id,
                    time=time,
                    webhook=url,
                    enabled=True,
                    position=0,
                    method=method)
                session.add(reminder)
                session.commit()

                i = Interval(reminder=reminder.id, period=interval, position=0)
                session.add(i)
                session.commit()

        else:
            r = Reminder(
                uid=uid,
                message=text,
                channel=channel.id,
                time=time,
                webhook=url,
                enabled=True,
                position=None,
                method=method)
            session.add(r)
            session.commit()

        return ReminderInformation(CreateReminderResponse.OK, channel=channel, time=time)


    async def timer(self, message, stripped, prefs):

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
                await message.channel.send(prefs.language.get_string('timer/limit'))

            else:
                n = stripped.split(' ')[1:2] or 'New timer #{}'.format(timers.count() + 1)

                if len(n) > 32:
                    await message.channel.send(prefs.language.get_string('timer/name_length').format(len(n)))

                elif n in [x.name for x in timers]:
                    await message.channel.send(prefs.language.get_string('timer/unique'))

                else:
                    t = Timer(name=n, owner=owner)
                    session.add(t)

                    session.commit()

                    await message.channel.send(prefs.language.get_string('timer/success'))

        elif stripped.startswith('delete '):

            n = ' '.join(stripped.split(' ')[1:])

            timers = session.query(Timer).filter(Timer.owner == owner).filter(Timer.name == n)

            if timers.count() < 1:
                await message.channel.send(prefs.language.get_string('timer/not_found'))

            else:
                timers.delete(synchronize_session='fetch')
                await message.channel.send(prefs.language.get_string('timer/deleted'))

                session.commit()

        else:
            await message.channel.send(prefs.language.get_string('timer/help'))


    async def blacklist(self, message, stripped, server):

        if len(message.channel_mentions) > 0:
            disengage_all = True

            all_channels = set([x.channel for x in session.query(Blacklist).filter(Blacklist.server == message.guild.id)])
            c = set([x.id for x in message.channel_mentions])

            for mention in message.channel_mentions:
                if mention.id not in all_channels:
                    disengage_all = False

            if disengage_all:
                channels = c & all_channels
                session.query(Blacklist).filter(Blacklist.channel.in_(channels)).delete(synchronize_session='fetch')

                await message.channel.send(embed=discord.Embed(description=server.language.get_string('blacklist/removed_from')))

            else:
                channels = [x for x in c if x not in all_channels]
                for channel in channels:
                    blacklist = Blacklist(channel=channel, server=message.guild.id)
                    session.add(blacklist)

                await message.channel.send(embed=discord.Embed(description=server.language.get_string('blacklist/added_from')))

        else:
            q = session.query(Blacklist).filter(Blacklist.channel == message.channel.id)

            if q.count() > 0:
                q.delete(synchronize_session='fetch')
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('blacklist/removed')))

            else:
                blacklist = Blacklist(channel=message.channel.id, server=message.guild.id)
                session.add(blacklist)
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('blacklist/added')))

        session.commit()


    async def restrict(self, message, stripped, server):

        disengage_all = True
        args = False

        all_roles = [x.role for x in session.query(RoleRestrict).filter(RoleRestrict.server == message.guild.id)]

        for role in message.role_mentions:
            args = True
            if role.id not in all_roles:
                disengage_all = False
                r = RoleRestrict(role=role.id, server=message.guild.id)
                session.add(r)

        if disengage_all and args:
            roles = [x.id for x in message.role_mentions]
            session.query(RoleRestrict).filter(RoleRestrict.role.in_(roles)).delete(synchronize_session='fetch')

            await message.channel.send(embed=discord.Embed(description=server.language.get_string('restrict/disabled')))

        elif args:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('restrict/enabled')))

        elif stripped:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('restrict/help')))

        else:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('restrict/allowed').format(' '.join(['<@&{}>'.format(i) for i in all_roles]))))

        session.commit()


    async def todo(self, message, stripped, server):
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
            msg = ['\n{}: {}'.format(i+1, todo.value) for i, todo in enumerate(todos)]
            if len(msg) == 0:
                msg.append(server.language.get_string('todo/add').format(prefix=server.prefix, command=command))
            await message.channel.send(embed=discord.Embed(title='{} TODO'.format('Server' if command == 'todos' else 'Your', name), description=''.join(msg)))

        elif len(splits) >= 2:
            if splits[0]  == 'add':
                a = ' '.join(splits[1:])
                if len('   '.join(todo.value for todo in todos)) > 1800:
                    await message.channel.send(server.language.get_string('todo/too_long2'))
                    return

                todo = Todo(owner=location, value=a)
                session.add(todo)
                await message.channel.send(server.language.get_string('todo/added').format(name=a))

            elif splits[0] == 'remove':
                try:
                    a = session.query(Todo).filter(Todo.id == todos[int(splits[1])-1].id).first()
                    session.query(Todo).filter(Todo.id == todos[int(splits[1])-1].id).delete(synchronize_session='fetch')
                    
                    await message.channel.send(server.language.get_string('todo/removed').format(a.value))

                except ValueError:
                    await message.channel.send(server.language.get_string('todo/error_value').format(prefix=server.prefix, command=command))
                except IndexError:
                    await message.channel.send(server.language.get_string('todo/error_index'))

            else:
                await message.channel.send(server.language.get_string('todo/help').format(prefix=server.prefix, command=command))

        else:
            if stripped == 'clear':
                session.query(Todo).filter(Todo.owner == location).delete(synchronize_session='fetch')
                await message.channel.send(server.language.get_string('todo/cleared'))

            else:
                await message.channel.send(server.language.get_string('todo/help').format(prefix=server.prefix, command=command))

        session.commit()


    async def delete(self, message, stripped, prefs):
        if message.guild is not None:
            li = [ch.id for ch in message.guild.channels] ## get all channels and their ids in the current server
        else:
            li = [message.channel.id]

        await message.channel.send(prefs.language.get_string('del/listing'))

        n = 1

        reminders = session.query(Reminder).filter(Reminder.channel.in_(li)).all()

        s = ''
        for rem in reminders:
            string = '''**{}**: '{}' *<#{}>*\n'''.format(
                n,
                self.clean_string(rem.message, message.guild),
                rem.channel)

            if len(s) + len(string) > 2000:
                await message.channel.send(s)
                s = string
            else:
                s += string

            n += 1

        if s:
            await message.channel.send(s)

        await message.channel.send(prefs.language.get_string('del/listed'))

        num = await client.wait_for('message', check=lambda m: m.author == message.author and m.channel == message.channel)
        nums = [n.strip() for n in num.content.split(',')]

        dels = 0
        for i in nums:
            try:
                i = int(i) - 1
                if i < 0:
                    continue

                session.query(Reminder).filter(Reminder.id == reminders[i].id).delete(synchronize_session='fetch')

                logger.info('Deleted reminder')
                dels += 1

            except ValueError:
                continue
            except IndexError:
                continue

        await message.channel.send(prefs.language.get_string('del/count').format(dels))
        session.commit()


    async def look(self, message, stripped, prefs):

        channel = message.channel_mentions[0] if len(message.channel_mentions) > 0 else message.channel
        channel = channel.id

        reminders = session.query(Reminder).filter(Reminder.channel == channel)

        if reminders.count() > 0:
            await message.channel.send(prefs.language.get_string('look/listing'))

            s = ''
            for rem in reminders:
                string = '\'{}\' *{}* **{}**\n'.format(
                    self.clean_string(rem.message, message.guild),
                    prefs.language.get_string('look/inter'),
                    datetime.fromtimestamp(rem.time, pytz.timezone(prefs.timezone)).strftime('%Y-%m-%d %H:%M:%S'))

                if len(s) + len(string) > 2000:
                    await message.channel.send(s)
                    s = string
                else:
                    s += string

            await message.channel.send(s)

        else:
            await message.channel.send(prefs.language.get_string('look/no_reminders'))


    async def offset_reminders(self, message, stripped, prefs):

        if message.guild is None:
            channels = [message.channel.id]
        else:
            channels = [x.id for x in message.guild.channels]

        time_parser = TimeExtractor(stripped, prefs.timezone)

        try:
            time = time_parser.extract_displacement()

        except:
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('offset/invalid_time')))

        else:
            if time == 0:
                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('offset/help').format(prefix=prefs.prefix)))

            else:
                reminders = session.query(Reminder).filter(Reminder.channel.in_(channels))

                for r in reminders:
                    r.time += time

                session.commit()

                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('offset/success').format(time)))


    async def nudge_channel(self, message, stripped, prefs):

        time_parser = TimeExtractor(stripped, prefs.timezone)

        try:
            t = time_parser.extract_displacement()

        except:
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('nudge/invalid_time')))

        else:
            query = session.query(ChannelNudge).filter(ChannelNudge.channel == message.channel.id)

            if query.count() < 1:
                new = ChannelNudge(channel=message.channel.id, time=t)
                session.add(new)

            else:
                query.first().time = t

            session.commit()

            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('nudge/success').format(t)))


logger = start_logger()
client = BotClient(max_messages=100, guild_subscriptions=False)
client.run(client.config.token)
