from models import Reminder, Server, User, Strings, Todo, RoleRestrict, Blacklist, Interval, Timer, session, Language, ChannelNudge

import discord
import pytz
import asyncio
import aiohttp
import dateparser

from datetime import datetime
from time import time as unix_time
import os
from configparser import SafeConfigParser as ConfigParser
from json import dumps as json_dump
import concurrent.futures
from functools import partial
import logging
import secrets

from enum import Enum


handler = logging.StreamHandler()
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))
logger.addHandler(handler)


FIFTY_YEARS = 1576800000

# enumerate possible responses from the remind and natural commands
class CreateReminderResponse(Enum):
    OK = 0
    LONG_TIME = 1
    LONG_INTERVAL = 2
    SHORT_INTERVAL = 3
    PERMISSIONS = 4
    INVALID_TAG = 5


REMIND_STRINGS = {
    CreateReminderResponse.OK: 'remind/success',
    CreateReminderResponse.LONG_TIME: 'remind/long_time',
    CreateReminderResponse.LONG_INTERVAL: 'interval/long_interval',
    CreateReminderResponse.SHORT_INTERVAL: 'interval/short_interval',
    CreateReminderResponse.PERMISSIONS: 'remind/no_perms',
    CreateReminderResponse.INVALID_TAG: 'remind/invalid_tag',
}

NATURAL_STRINGS = {
    CreateReminderResponse.LONG_TIME: 'natural/long_time',
}


class Information():
    def __init__(self, language, timezone, prefix, allowed_dm):
        self.language = session.query(Language).filter(Language.code == language).first() or session.query(Language).filter(Language.code == 'EN').first()
        self.timezone = timezone
        self.prefix = prefix
        self.allowed_dm = allowed_dm


class Config():
    def __init__(self):
        config = ConfigParser()
        config.read('config.ini')

        self.donor_roles = [353630811561394206, 353226278435946496]

        self.dbl_token = config.get('DEFAULT', 'dbl_token')
        self.token = config.get('DEFAULT', 'token')

        self.patreon = config.get('DEFAULT', 'patreon_enabled') == 'yes'
        self.patreon_servers = [int(x.strip()) for x in config.get('DEFAULT', 'patreon_server').split(',')]

        if self.patreon:
            logger.info('Patreon is enabled. Will look for servers {}'.format(self.patreon_servers))


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        self.start_time = unix_time()

        self.commands = {
        ##  format: 'command' : [<function>, <works in DMs?>]

            'help' : [self.help, True],
            'info' : [self.info, True],
            'donate' : [self.donate, True],

            'prefix' : [self.change_prefix, False],
            'blacklist' : [self.blacklist, False],
            'restrict' : [self.restrict, False],

            'timezone' : [self.timezone, True],
            'clock' : [self.clock, True],
            'lang' : [self.language, True],
            'offset' : [self.offset_reminders, True],
            'nudge' : [self.nudge_channel, True],

            'natural' : [self.natural, True],
            'remind' : [self.remind, True],
            'interval' : [self.remind, True],
            'timer' : [self.timer, True],
            'del' : [self.delete, True],
            'look' : [self.look, True],

            'todo' : [self.todo, True],
            'todos' : [self.todo, False],

            'ping' : [self.time_stats, True],
        }

        self.config = Config()

        self.executor = concurrent.futures.ThreadPoolExecutor()

        super(BotClient, self).__init__(*args, **kwargs)


    async def do_blocking(self, method):
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]


    def create_uid(self, i1, i2):
        m = i2
        while m > 0:
            i1 *= 10
            m //= 10
        
        bigint = i1 + i2
        full = hex(bigint)[2:]
        while len(full) < 64:
            full += secrets.choice('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_')

        return full


    def clean_string(self, string, guild):
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


    def is_patron(self, memberid, level=0):
        if self.config.patreon:
            p_servers = [client.get_guild(x) for x in self.config.patreon_servers]
            members = []
            for guild in p_servers:
                for member in guild.members:
                    if member.id == memberid:
                        members.append(member)

            roles = []
            for member in members:
                for role in member.roles:
                    roles.append(role.id)

            return bool(set(self.config.donor_roles[level]) & set(roles))

        else:
            return True


    def format_time(self, text, as_exact, server):
        invert = False
        if text[0] == '-':
            invert = True
            text = text[1:]

        if '/' in text or ':' in text:
            date = datetime.now(pytz.timezone(server.timezone))

            for clump in text.split('-'):
                if '/' in clump:
                    a = clump.split('/')
                    if len(a) == 2:
                        date = date.replace(month=int(a[1]), day=int(a[0]))
                    elif len(a) == 3:
                        date = date.replace(year=int(a[2]), month=int(a[1]), day=int(a[0]))

                elif ':' in clump:
                    a = clump.split(':')
                    if len(a) == 2:
                        date = date.replace(hour=int(a[0]), minute=int(a[1]))
                    elif len(a) == 3:
                        date = date.replace(hour=int(a[0]), minute=int(a[1]), second=int(a[2]))
                    else:
                        return None

                else:
                    date = date.replace(day=int(clump))

            return date.timestamp()

        else:
            current_buffer = '0'
            seconds = 0
            minutes = 0
            hours = 0
            days = 0

            for char in text:

                if char == 's':
                    seconds = int(current_buffer)
                    current_buffer = '0'

                elif char == 'm':
                    minutes = int(current_buffer)
                    current_buffer = '0'

                elif char == 'h':
                    hours = int(current_buffer)
                    current_buffer = '0'

                elif char == 'd':
                    days = int(current_buffer)
                    current_buffer = '0'

                else:
                    try:
                        int(char)
                        current_buffer += char
                    except ValueError:
                        return None

            full = seconds + (minutes * 60) + (hours * 3600) + (days * 86400) + int(current_buffer)

            if as_exact:
                if invert:
                    time_sec = round(unix_time() - full)
                else:
                    time_sec = round(unix_time() + full)

            else:
                if invert:
                    time_sec = -full
                else:
                    time_sec = full

            return time_sec


    async def welcome(self, guild, *args):

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding reminder-bot! To begin, type `$help`!')
                break
            else:
                continue


    async def time_stats(self, message, *args):
        uptime = unix_time() - self.start_time

        message_ts = message.created_at.timestamp()

        m = await message.channel.send('.')

        ping = m.created_at.timestamp() - message_ts

        await m.edit(content='''
        Uptime: {}s
        Ping: {}ms
        '''.format(round(uptime), round(ping*1000)))


    async def on_error(self, *a, **k):
        session.rollback()
        raise


    async def on_ready(self):

        logger.info('Logged in as')
        logger.info(self.user.name)
        logger.info(self.user.id)
        logger.info('------------')


    async def on_guild_remove(self, guild):
        await self.send()


    async def on_guild_join(self, guild):
        await self.send()

        await self.welcome(guild)


    async def send(self):
        if not self.config.dbl_token:
            return

        guild_count = len(self.guilds)

        csession = aiohttp.ClientSession()
        dump = json_dump({
            'server_count': guild_count
        })

        head = {
            'authorization': self.config.dbl_token,
            'content-type' : 'application/json'
        }

        url = 'https://discordbots.org/api/bots/stats'
        async with csession.post(url, data=dump, headers=head) as resp:
            logger.info('returned {0.status} for {1}'.format(resp, dump))

        await csession.close()


    async def on_message(self, message):

        if message.author.bot or message.content is None:
            return

        u = session.query(User).filter(User.user == message.author.id)

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

        try:
            if await self.get_cmd(message, server, user):
                logger.info('Command: ' + message.content)

        except discord.errors.Forbidden:
            try:
                await message.channel.send(server.language.get_string('no_perms_general'))
            except discord.errors.Forbidden:
                logger.info('Twice Forbidden')


    async def get_cmd(self, message, server, user):

        prefix = '$' if server is None else server.prefix

        command = ''
        stripped = ''

        if message.content[0:len(prefix)] == prefix:

            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:

            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        else:
            return False

        if command in self.commands.keys():
            if server is not None and not message.content.startswith(('{}help'.format(server.prefix), '{}blacklist'.format(server.prefix), '{}restrict'.format(server.prefix))):

                channel = session.query(Blacklist).filter(Blacklist.channel == message.channel.id)

                if channel.count() > 0:
                    await message.channel.send(embed=discord.Embed(description=server.language.get_string('blacklisted')))
                    return False

            command_form = self.commands[command]

            if command_form[1] or server is not None:

                if server is not None and not message.guild.me.guild_permissions.manage_webhooks:
                    await message.channel.send(server.language.get_string('no_perms_webhook'))

                language = user.language or ('EN' if server is None else server.language)
                timezone = user.timezone or ('UTC' if server is None else server.timezone)

                info = Information(language, timezone, prefix, user.allowed_dm)

                await command_form[0](message, stripped, info)
                return True

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
            if message.author.guild_permissions.manage_guild:

                stripped += ' '
                new = stripped[:stripped.find(' ')]

                if len(new) > 5:
                    await message.channel.send(prefs.language.get_string('prefix/too_long'))

                else:
                    s = session.query(Server).filter(Server.server == message.guild.id).first()
                    s.prefix = new

                    await message.channel.send(prefs.language.get_string('prefix/success').format(prefix=s.prefix))

            else:
                await message.channel.send(prefs.language.get_string('admin_required'))

        else:
            await message.channel.send(prefs.language.get_string('prefix/no_argument').format(prefix=prefs.prefix))

        session.commit()


    async def timezone(self, message, stripped, prefs):

        if message.guild is not None and message.author.guild_permissions.manage_guild:
            target = session.query(Server).filter(Server.server == message.guild.id).first()
            s = 'timezone/set'
        else:
            target = session.query(User).filter(User.user == message.author.id).first()
            s = 'timezone/set_p'

        if stripped == '':
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('timezone/no_argument').format(prefix=prefs.prefix, timezone=prefs.timezone)))

        else:
            if stripped not in pytz.all_timezones:
                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('timezone/no_timezone')))
            else:
                target.timezone = stripped
                d = datetime.now(pytz.timezone(target.timezone))

                await message.channel.send(embed=discord.Embed(description=prefs.language.get_string(s).format(timezone=target.timezone, time=d.strftime('%H:%M:%S'))))

                session.commit()


    async def language(self, message, stripped, prefs):

        if message.guild is not None and message.author.guild_permissions.manage_guild:
            target = session.query(Server).filter(Server.server == message.guild.id).first()
            s = 'lang/set'
        else:
            target = session.query(User).filter(User.user == message.author.id).first()
            s = 'lang/set_p'

        new_lang = session.query(Language).filter((Language.code == stripped.upper()) | (Language.name == stripped.lower())).first()

        if new_lang is not None:
            target.language = new_lang.code

            await message.channel.send(embed=discord.Embed(description=new_lang.get_string(s)))
    
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

        err = False
        location_id = message.channel.id

        time_crop = stripped.split(server.language.get_string('natural/send'))[0]
        message_crop = stripped.split(server.language.get_string('natural/send'), 1)[1]
        datetime_obj = await self.do_blocking( partial(dateparser.parse, time_crop, settings={'TIMEZONE': server.timezone, 'TO_TIMEZONE': 'UTC'}) )

        if datetime_obj is None:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('natural/invalid_time')))
            return

        if message.guild is not None:
            chan_split = message_crop.split(server.language.get_string('natural/to'))
            if len(chan_split) > 1 \
                and chan_split[-1].strip()[0] == '<' \
                and chan_split[-1].strip()[-1] == '>' \
                and all([x not in '< >' for x in chan_split[-1].strip()[1:-1]]):

                location_id = int( ''.join([x for x in chan_split[-1] if x in '0123456789']) )

                message_crop = message_crop.rsplit(server.language.get_string('natural/to'), 1)[0]

        interval_split = message_crop.split(server.language.get_string('natural/every'))
        recurring = False
        interval = 0

        if len(interval_split) > 1:
            interval = await self.do_blocking( partial(dateparser.parse, '1 ' + interval_split[-1], settings={'TO_TIMEZONE' : 'UTC'}) )

            if interval is None:
                pass
            elif self.is_patron(message.author.id):
                recurring = True

                interval = abs((interval - datetime.utcnow()).total_seconds())

                message_crop = message_crop.rsplit(server.language.get_string('natural/every'), 1)[0]

            else:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/donor')))
                return

        mtime = datetime_obj.timestamp()

        result, location = await self.add_reminder(message, location_id, message_crop, mtime, interval=interval if recurring else None, method='natural')
        string = NATURAL_STRINGS.get(result, REMIND_STRINGS[result])

        if location is not None:
            location = location.recipient if isinstance(location, discord.DMChannel) else location
            response = server.language.get_string(string).format(location=location.mention, offset='some')

        else:
            response = server.language.get_string(string)

        await message.channel.send(embed=discord.Embed(description=response))


    async def remind(self, message, stripped, server):

        args = stripped.split(' ')
        is_interval = message.content[1] == 'i'

        if len(args) < 2:
            if is_interval:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/no_argument').format(prefix=server.prefix)))

            else:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('remind/no_argument').format(prefix=server.prefix)))

        else:
            is_patreon = self.is_patron(message.author.id)

            if is_interval and not is_patreon:
                await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/donor')))

            else:
                channel = message.channel
                interval = None
                scope_id = message.channel.id

                if args[0][0] == '<' and message.guild is not None:
                    arg = args.pop(0)
                    scope_id = int(''.join(x for x in arg if x in '0123456789'))

                t = args.pop(0)
                mtime = self.format_time(t, True, server)

                if mtime is None:
                    await message.channel.send(embed=discord.Embed(description=server.language.get_string('remind/invalid_time')))
        
                else:
                    if is_interval:
                        i = args.pop(0)
                        interval = self.format_time(i, False, server)

                        if interval is None:
                            await message.channel.send(embed=discord.Embed(description=server.language.get_string('interval/invalid_interval')))
                            return

                    text = ' '.join(args)

                    result, location = await self.add_reminder(message, scope_id, text, mtime, interval, method='remind')

                    if location is not None:
                        location = location.recipient if isinstance(location, discord.DMChannel) else location
                        response = server.language.get_string(REMIND_STRINGS[result]).format(location=location.mention, offset='some')

                    else:
                        response = server.language.get_string(REMIND_STRINGS[result])

                    await message.channel.send(embed=discord.Embed(description=response))


    async def add_reminder(self, message, location, text, time, interval=None, method='natural'):
        uid = self.create_uid(location, message.id) # create a UID

        nudge_channel = session.query(ChannelNudge).filter(ChannelNudge.channel == location).first() # check if it's being nudged

        if nudge_channel is not None:
            time += nudge_channel.time

        if time > unix_time() + FIFTY_YEARS:
            return CreateReminderResponse.LONG_TIME, None

        elif time < unix_time():
            time = int(unix_time()) + 1
            # push time to be 'now'

        url = None

        channel = message.guild.get_channel(location)

        if channel is not None: # if not a DM reminder

            hooks = [x for x in await channel.webhooks() if x.user.id == self.user.id]
            hook = hooks[0] if len(hooks) > 0 else await channel.create_webhook(name='Reminders')
            url = hook.url

            restrict = session.query(RoleRestrict).filter(RoleRestrict.role.in_([x.id for x in message.author.roles]))

            if restrict.count() != 0 and not message.author.guild_permissions.manage_messages:        
                return CreateReminderResponse.PERMISSIONS, None
                # invalid permissions

        else:
            member = message.guild.get_member(location)

            if member is None:
                return CreateReminderResponse.INVALID_TAG, None

            else:
                await member.create_dm()
                channel = member.dm_channel

        if interval is not None:
            if 8 > interval:
                return CreateReminderResponse.SHORT_INTERVAL, None

            elif interval > FIFTY_YEARS:
                return CreateReminderResponse.LONG_INTERVAL, None

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

        return CreateReminderResponse.OK, channel


    async def timer(self, message, stripped, prefs):

        if message.guild is None:
            owner = message.author.id
        else:
            owner = message.guild.id

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

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('admin_required')))

        elif len(message.channel_mentions) > 0:
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

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=server.language.get_string('admin_required')))

        else:
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
            await message.channel.send(embed=discord.Embed(title='{}\'s TODO'.format(name), description=''.join(msg)))

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

        time = self.format_time(stripped, False, prefs)

        if time is None:
            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('offset/invalid_time')))

        else:
            reminders = session.query(Reminder).filter(Reminder.channel.in_(channels))

            for r in reminders:
                r.time += time

            session.commit()

            await message.channel.send(embed=discord.Embed(description=prefs.language.get_string('offset/success').format(time)))


    async def nudge_channel(self, message, stripped, prefs):

        t = self.format_time(stripped, False, prefs)

        if t is None:
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


client = BotClient(max_messages=10)

client.run(client.config.token)
