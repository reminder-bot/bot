from models import Reminder, Server, session

import discord
import pytz
import asyncio
import aiohttp
import dateparser
import sqlalchemy

from datetime import datetime
import time
import sys
import os
import configparser
import json
import traceback
import concurrent.futures
from functools import partial
import logging


class OneLineExceptionFormatter(logging.Formatter):
    def formatException(self, exc_info):
        result = super().formatException(exc_info)
        return repr(result)

    def format(self, record):
        result = super().format(record)
        if record.exc_text:
            result = result.replace("\n", "")
        return result

handler = logging.StreamHandler()
formatter = OneLineExceptionFormatter(logging.BASIC_FORMAT)
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))
logger.addHandler(handler)


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.start_time = time.time()

        self.commands = {
        ## format: 'command' : [<function>, <works in DMs?>]

            'help' : [self.help, True],
            'info' : [self.info, True],
            'donate' : [self.donate, True],

            'prefix' : [self.change_prefix, False],
            'blacklist' : [self.blacklist, False],
            'restrict' : [self.restrict, False],

            'timezone' : [self.timezone, False],
            'clock' : [self.clock, False],
            'lang' : [self.language, False],
            'offset' : [self.offset_reminders, False],

            'natural' : [self.natural, False],
            'remind' : [self.remind, False],
            'interval' : [self.interval, False],
            'del' : [self.delete, True],
            'look' : [self.look, True],

            'todo' : [self.todo, True],
            'todos' : [self.todo, False],

            'welcome' : [self.welcome, False],
            'ping' : [self.time_stats, True],
        }

        self.strings = {

        }

        self.languages = {

        }

        self.donor_roles = {
            1 : [353630811561394206],
            2 : [353226278435946496],
            3 : [353639034473676802, 404224194641920011]
        }

        self.config = configparser.SafeConfigParser()
        self.config.read('config.ini')
        self.dbl_token = self.config.get('DEFAULT', 'dbl_token')
        self.patreon = self.config.get('DEFAULT', 'patreon_enabled') == 'yes'
        self.patreon_servers = [int(x.strip()) for x in self.config.get('DEFAULT', 'patreon_server').split(',')]

        if self.patreon:
            logger.info('Patreon is enabled. Will look for servers {}'.format(self.patreon_servers))

        try:
            with open('DATA/todos.json', 'r') as f:
                self.todos = json.load(f)
                self.todos = {int(x) : y for x, y in self.todos.items()}
        except FileNotFoundError:
            logger.warn('No todos file found')
            self.todos = {}

        self.update()

        if 'EN' not in self.strings.keys():
            logger.critical('English strings file not present or broken. Exiting...')
            sys.exit()

        self.executor = concurrent.futures.ThreadPoolExecutor()


    async def do_blocking(self, method):
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]


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


    def get_patrons(self, memberid, level=2):
        if self.patreon:
            p_servers = [client.get_guild(x) for x in self.patreon_servers]
            members = []
            for guild in p_servers:
                for member in guild.members:
                    if member.id == memberid:
                        members.append(member)

            roles = []
            for member in members:
                for role in member.roles:
                    roles.append(role.id)

            return bool(set(self.donor_roles[level]) & set(roles))

        else:
            return True


    def parse_mention(self, message, text, server):
        if text[2:-1][0] == '!':
            tag = int(text[3:-1])

        else:
            try:
                tag = int(text[2:-1])
            except ValueError:
                return None, None

        if text[1] == '@': # if the scope is a user
            pref = '@'
            scope = message.guild.get_member(tag)

        else:
            pref = '#'
            scope = message.guild.get_channel(tag)

        if scope is None:
            return None, None

        else:
            return scope.id, pref


    def perm_check(self, message, server):
        if not message.author.guild_permissions.manage_messages:
            for role in message.author.roles:
                if role.id in server.restrictions['data']:
                    return True
            else:
                return False

        else:
            return True


    def length_check(self, message, text):
        if len(text) > 150 and not self.get_patrons(message.author.id):
            return '150'

        if len(text) >= 1900:
            return '2000'

        else:
            return True


    def format_time(self, text, server):
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
            if invert:
                time_sec = round(time.time() - full)
            else:
                time_sec = round(time.time() + full)
            return time_sec


    def get_strings(self, server, string):
        strings = {}
        if server is None:
            strings = self.strings['EN']
        else:
            strings = self.strings[server.language]

        pathfinder = string.split('/')
        for path in pathfinder:
            strings = strings.get(path)

            if strings is None:
                strings = self.strings['EN']

                for path in pathfinder:
                    strings = strings.get(path)

                return '{} (no translation available, maintainer: {})'.format(strings, self.strings[server.language].get('__maintainer__'))

        return strings


    async def welcome(self, guild, *args):
        if isinstance(guild, discord.Message):
            guild = guild.guild

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding reminder-bot! To begin, type `$help`!')
                break
            else:
                continue


    async def time_stats(self, message, *args):
        uptime = time.time() - self.start_time

        message_ts = message.created_at.timestamp()

        m = await message.channel.send('.')

        ping = m.created_at.timestamp() - message_ts

        await m.edit(content='''
        Uptime: {}s
        Ping: {}ms
        '''.format(round(uptime), round(ping*1000)))


    def update(self, *args):
        for fn in os.listdir(self.config.get('DEFAULT', 'strings_location')):
            if fn.startswith('strings_'):
                with open(self.config.get('DEFAULT', 'strings_location') + fn, 'r', encoding='utf-8') as f:
                    a = f.read()
                    try:
                        self.strings[fn[8:10]] = eval(a)
                    except:
                        exc_info = sys.exc_info()
                        logger.error('String file {} will not be loaded'.format(fn))

                        traceback.print_exception(*exc_info)
                    else:
                        self.languages[a.split('\n')[0].strip('#:\n ')] = fn[8:10]

        logger.info('Languages enabled: ' + str(self.languages))


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
        if not self.dbl_token:
            return

        guild_count = len(self.guilds)

        csession = aiohttp.ClientSession()
        dump = json.dumps({
            'server_count': guild_count
        })

        head = {
            'authorization': self.dbl_token,
            'content-type' : 'application/json'
        }

        url = 'https://discordbots.org/api/bots/stats'
        async with csession.post(url, data=dump, headers=head) as resp:
            logger.info('returned {0.status} for {1}'.format(resp, dump))

        await csession.close()


    async def on_message(self, message):
        if message.guild is not None and session.query(Server).filter_by(id=message.guild.id).first() is None:

            server = Server(id=message.guild.id, prefix='$', timezone='UTC', language='EN', blacklist={'data': []}, restrictions={'data': []})

            session.add(server)
            session.commit()

        server = None if message.guild is None else session.query(Server).filter_by(id=message.guild.id).first()

        if message.author.bot or message.content == None:
            return

        try:
            if await self.get_cmd(message, server):
                logger.info('Command: ' + message.content)

        except discord.errors.Forbidden:
            try:
                await message.channel.send(self.get_strings(server, 'no_perms_general'))
            except discord.errors.Forbidden:
                logger.info('Twice Forbidden')


    async def get_cmd(self, message, server):

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
            if server is not None and message.channel.id in server.blacklist['data'] and not message.content.startswith(('{}help'.format(server.prefix), '{}blacklist'.format(server.prefix))):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklisted')))
                return False

            command_form = self.commands[command]

            if command_form[1] or server is not None:

                if server is not None and not message.guild.me.guild_permissions.manage_webhooks:
                    await message.channel.send(self.get_strings(server, 'no_perms_webhook'))

                await command_form[0](message, stripped, server)
                return True

            else:
                return False

        else:
            return False


    async def help(self, message, stripped, server):
        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'help')))


    async def info(self, message, stripped, server):
        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'info').format(prefix=server.prefix, user=self.user.name)))


    async def donate(self, message, stripped, server):
        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'donate')))


    async def change_prefix(self, message, stripped, server):

        if stripped:
            if message.author.guild_permissions.manage_guild:

                stripped += ' '
                new = stripped[:stripped.find(' ')]

                if len(new) > 5:
                    await message.channel.send(self.get_strings(server, 'prefix/too_long'))

                else:
                    server.prefix = new

                    await message.channel.send(self.get_strings(server, 'prefix/success').format(prefix=server.prefix))

            else:
                await message.channel.send(self.get_strings(server, 'admin_required'))

        else:
            await message.channel.send(self.get_strings(server, 'prefix/no_argument').format(prefix=server.prefix))

        session.commit()


    async def timezone(self, message, stripped, server):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'admin_required')))

        elif stripped == '':
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'timezone/no_argument').format(prefix=server.prefix, timezone=server.timezone)))

        else:
            if stripped not in pytz.all_timezones:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'timezone/no_timezone')))
            else:
                server.timezone = stripped
                d = datetime.now(pytz.timezone(server.timezone))

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'timezone/success').format(timezone=server.timezone, time=d.strftime('%H:%M:%S'))))

                session.commit()


    async def language(self, message, stripped, server):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(self.get_strings(server, 'admin_required'))

        elif stripped.lower() in self.languages.keys():
            server.language = self.languages[stripped.lower()]
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'lang/set')))

        elif stripped.upper() in self.languages.values():
            server.language = stripped.upper()
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'lang/set')))

        else:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'lang/invalid').format('\n'.join(['{} ({})'.format(x.title(), y.upper()) for x, y in self.languages.items()]))))
            return

        session.commit()


    async def clock(self, message, stripped, server):

        t = datetime.now(pytz.timezone(server.timezone))

        await message.channel.send(self.get_strings(server, 'clock/time').format(t.strftime('%H:%M:%S')))


    async def natural(self, message, stripped, server):

        err = False
        if len(stripped.split(self.get_strings(server, 'natural/send'))) < 2:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'natural/no_argument').format(prefix=server.prefix)))
            return

        scope = message.channel

        time_crop = stripped.split(self.get_strings(server, 'natural/send'))[0]
        message_crop = stripped.split(self.get_strings(server, 'natural/send'), 1)[1]
        datetime_obj = await self.do_blocking( partial(dateparser.parse, time_crop, settings={'TIMEZONE': server.timezone, 'TO_TIMEZONE': 'UTC'}) )

        if datetime_obj is None:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'natural/bad_time')))
            err = True

        elif datetime_obj.timestamp() - time.time() > 1576800000:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'natural/long_time')))
            err = True

        chan_split = message_crop.split(self.get_strings(server, 'natural/to'))
        if len(chan_split) > 1 \
            and chan_split[-1].strip()[0] == '<' \
            and chan_split[-1].strip()[-1] == '>' \
            and all([x not in '< >' for x in chan_split[-1].strip()[1:-1]]):

            id = int( ''.join([x for x in chan_split[-1] if x in '0123456789']) )
            scope = message.guild.get_member(id)
            if scope is None:
                scope = message.guild.get_channel(id)

                if scope is None:
                    await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_tag')))
                    err = True

            message_crop = message_crop.rsplit(self.get_strings(server, 'natural/to'), 1)[0]

        interval_split = message_crop.split(self.get_strings(server, 'natural/every'))
        recurring = False
        interval = 0

        if len(interval_split) > 1:
            interval = await self.do_blocking( partial(dateparser.parse, '1 ' + interval_split[-1], settings={'TO_TIMEZONE' : 'UTC'}) )

            if interval is None:
                pass
            elif self.get_patrons(message.author.id, level=1):
                recurring = True
                interval = abs((interval - datetime.utcnow()).total_seconds())
                if interval < 8:
                    await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/8_seconds')))
                    err = True
                elif interval > 1576800000:
                    await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'natural/long_time')))
                    err = True

                message_crop = message_crop.rsplit(self.get_strings(server, 'natural/every'), 1)[0]
            else:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/donor')))
                return

        if isinstance(scope, discord.TextChannel):
            if not self.perm_check(message, server):

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_perms').format(prefix=server.prefix)))
                err = True

        elif scope is not None:
            s = scope.dm_channel
            if s is None:
                await scope.create_dm()
                s = scope.dm_channel

            scope = s

        if self.length_check(message, message_crop) is not True:
            if self.length_check(message, message_crop) == '150':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars').format(len(message_crop), prefix=server.prefix)))
                err = True

            elif self.length_check(message, message_crop) == '2000':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars_2000')))
                err = True

        if not err:
            webhook = None

            if isinstance(scope, discord.TextChannel):
                for hook in await scope.webhooks():
                    if hook.user.id == self.user.id:
                        webhook = hook.url
                        break

                if webhook is None:
                    w = await scope.create_webhook(name='Reminders')
                    webhook = w.url

            if recurring:
                reminder = Reminder(time=datetime_obj.timestamp(), message=message_crop.strip(), channel=scope.id, interval=interval, webhook=webhook, method='natural')
            else:
                reminder = Reminder(time=datetime_obj.timestamp(), message=message_crop.strip(), channel=scope.id, webhook=webhook, method='natural')

            logger.info('{}: New: {}'.format(datetime.utcnow().strftime('%H:%M:%S'), reminder))
            if isinstance(scope, discord.TextChannel):
                tag = scope.mention
            else:
                tag = scope.recipient.mention
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'natural/success').format(tag, round(datetime_obj.timestamp() - time.time()))))

            session.add(reminder)
            session.commit()


    async def remind(self, message, stripped, server):

        webhook = None

        args = stripped.split(' ')

        if len(args) < 2:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_argument').format(prefix=server.prefix)))
            return

        scope = message.channel.id
        pref = '#'

        if args[0].startswith('<'): # if a scope is provided

            scope, pref = self.parse_mention(message, args[0], server)
            if scope is None:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_tag')))
                return

            args.pop(0)

        try:
            while args[0] == '':
                args.pop(0)

            msg_time = self.format_time(args[0], server)
        except ValueError:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_time')))
            return

        if msg_time is None or msg_time - time.time() > 1576800000:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_time')))
            return

        args.pop(0)

        msg_text = ' '.join(args)

        if self.length_check(message, msg_text) is not True:
            if self.length_check(message, msg_text) == '150':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars').format(len(msg_text), prefix=server.prefix)))

            elif self.length_check(message, msg_text) == '2000':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars_2000')))

            return

        if pref == '#':
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_perms').format(prefix=server.prefix)))
                return

            c = message.guild.get_channel(scope)

            for hook in await c.webhooks():
                if hook.user.id == self.user.id:
                    webhook = hook.url
                    break

            if webhook is None:
                w = await c.create_webhook(name='Reminders')
                webhook = w.url

        else:
            m = message.guild.get_member(scope)
            s = m.dm_channel
            if s is None:
                await m.create_dm()
                s = m.dm_channel

            scope = s.id

        reminder = Reminder(time=msg_time, channel=scope, message=msg_text, webhook=webhook, method='remind')

        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/success').format(pref, scope, round(msg_time - time.time()))))

        session.add(reminder)
        session.commit()

        logger.info('Registered a new reminder for {}'.format(message.guild.name))


    async def interval(self, message, stripped, server):

        if not self.get_patrons(message.author.id, level=1):
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/donor').format(prefix=server.prefix)))
            return

        args = message.content.split(' ')
        args.pop(0) # remove the command item

        if len(args) < 3:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/no_argument').format(prefix=server.prefix)))
            return

        scope = message.channel.id
        pref = '#'

        if args[0].startswith('<'): # if a scope is provided

            scope, pref = self.parse_mention(message, args[0], server)
            if scope is None:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_tag')))
                return

            args.pop(0)

        while args[0] == '':
            args.pop(0)

        msg_time = self.format_time(args[0], server)

        if msg_time is None or msg_time - time.time() > 1576800000:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_time')))
            return

        args.pop(0)

        while args[0] == '':
            args.pop(0)

        msg_interval = self.format_time(args[0], message.guild.id)

        if msg_interval == None or msg_interval > 1576800000:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/invalid_interval')))
            return

        msg_interval -= time.time()
        msg_interval = round(msg_interval)

        if msg_interval < 8:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/8_seconds')))
            return

        args.pop(0)

        msg_text = ' '.join(args)

        if self.length_check(message, msg_text) is not True:
            if self.length_check(message, msg_text) == '150':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars').format(len(msg_text))))

            elif self.length_check(message, msg_text) == '2000':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/invalid_chars_2000')))

            return

        webhook = None

        if pref == '#':
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_perms')))
                return

            c = message.guild.get_channel(scope)

            for hook in await c.webhooks():
                if hook.user.id == self.user.id:
                    webhook = hook.url
                    break

            if webhook is None:
                w = await c.create_webhook(name='Reminders')
                webhook = w.url

        else:
            m = message.guild.get_member(scope)
            s = m.dm_channel
            if s is None:
                await m.create_dm()
                s = m.dm_channel

            scope = s.id

        reminder = Reminder(time=msg_time, interval=msg_interval, channel=scope, message=msg_text, webhook=webhook, method='interval')

        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'interval/success').format(pref, scope, round(msg_time - time.time()))))

        session.add(reminder)
        session.commit()

        logger.info('Registered a new interval for {}'.format(message.guild.name))


    async def blacklist(self, message, stripped, server):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'admin_required')))
            return

        if len(message.channel_mentions) > 0:
            disengage_all = True

            for mention in message.channel_mentions:
                if mention.id not in server.blacklist['data']:
                    disengage_all = False

            if disengage_all:
                for mention in message.channel_mentions:
                    server.blacklist['data'].remove(mention.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklist/removed_from')))

            else:
                for mention in message.channel_mentions:
                    if mention.id not in server.blacklist['data']:
                        server.blacklist['data'].append(mention.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklist/added_from')))

        else:
            if message.channel.id in server.blacklist['data']:
                server.blacklist['data'].remove(message.channel.id)
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklist/removed')))

            else:
                server.blacklist['data'].append(message.channel.id)
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklist/added')))

        session.commit()


    async def restrict(self, message, stripped, server):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'admin_required')))

        else:
            disengage_all = True
            args = False

            for role in message.role_mentions:
                args = True
                if role.id not in server.restrictions['data']:
                    disengage_all = False
                server.restrictions['data'].append(role.id)

            if disengage_all and args:
                for role in message.role_mentions:
                    server.restrictions['data'].remove(role.id)
                    server.restrictions['data'].remove(role.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'restrict/disabled')))

            elif args:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'restrict/enabled')))

            elif stripped:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'restrict/help')))

            else:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'restrict/allowed').format(' '.join(['<@&' + str(i) + '>' for i in server.restrictions['data']]))))

        session.commit()


    async def todo(self, message, stripped, server):
        if 'todos' in message.content.split(' ')[0]:
            if server is None:
                await message.channel.send(self.get_strings(server, 'todo/server_only').format(prefix='$'))
                return

            location = message.guild.id
            name = message.guild.name
            command = 'todos'
        else:
            location = message.author.id
            name = message.author.name
            command = 'todo'


        if location not in self.todos.keys():
            self.todos[location] = []

        splits = stripped.split(' ')

        todo = self.todos[location]

        if len(splits) == 1 and splits[0] == '':
            msg = ['\n{}: {}'.format(i+1, todo[i]) for i in range(len(todo))]
            if len(msg) == 0:
                msg.append(self.get_strings(server, 'todo/add').format(prefix='$' if server is None else server.prefix, command=command))
            await message.channel.send(embed=discord.Embed(title='{}\'s TODO'.format(name), description=''.join(msg)))

        elif len(splits) >= 2:
            if splits[0] in ['add', 'a']:
                a = ' '.join(splits[1:])
                if len(''.join(todo)) > 1600:
                    await message.channel.send(self.get_strings(server, 'todo/too_long2'))
                    return

                self.todos[location].append(a)
                await message.channel.send(self.get_strings(server, 'todo/added').format(name=a))

            elif splits[0] in ['remove', 'r']:
                try:
                    a = self.todos[location].pop(int(splits[1])-1)
                    await message.channel.send(self.get_strings(server, 'todo/removed').format(a))

                except ValueError:
                    await message.channel.send(self.get_strings(server, 'todo/error_value').format(prefix='$' if server is None else server.prefix, command=command))
                except IndexError:
                    await message.channel.send(self.get_strings(server, 'todo/error_index'))


            else:
                await message.channel.send(self.get_strings(server, 'todo/help').format(prefix='$' if server is None else server.prefix, command=command))

        else:
            if stripped in ['remove*', 'r*', 'clear', 'clr']:
                self.todos[location] = []
                await message.channel.send(self.get_strings(server, 'todo/cleared'))

            else:
                await message.channel.send(self.get_strings(server, 'todo/help').format(prefix='$' if server is None else server.prefix, command=command))

        with open('DATA/todos.json', 'w') as f:
            json.dump(self.todos, f)


    async def delete(self, message, stripped, server):
        if server is not None:
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_perms').format(prefix=server.prefix)))
                return

            li = [ch.id for ch in message.guild.channels] ## get all channels and their ids in the current server
        else:
            li = [message.channel.id]

        await message.channel.send(self.get_strings(server, 'del/listing'))

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

        await message.channel.send(self.get_strings(server, 'del/listed'))

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

        await message.channel.send(self.get_strings(server, 'del/count').format(dels))


    async def look(self, message, stripped, server):

        reminders = session.query(Reminder).filter(Reminder.channel == message.channel.id).all()

        if len(reminders) > 0:
            await message.channel.send(self.get_strings(server, 'look/listing'))

            s = ''
            for rem in reminders:
                string = '\'{}\' *{}* **{}**\n'.format(
                    self.clean_string(rem.message, message.guild),
                    self.get_strings(server, 'look/inter'),
                    datetime.fromtimestamp(rem.time, pytz.timezone('UTC' if server is None else server.timezone)).strftime('%Y-%m-%d %H:%M:%S'))

                if len(s) + len(string) > 2000:
                    await message.channel.send(s)
                    s = string
                else:
                    s += string

            await message.channel.send(s)

        else:
            await message.channel.send(self.get_strings(server, 'look/no_reminders'))


    async def offset_reminders(self, message, stripped, server):
        if not self.perm_check(message, server):
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'remind/no_perms').format(prefix=server.prefix)))

        else:
            t = self.format_time(stripped, server)

            if t is None:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'offset/invalid_time')))

            else:
                t -= time.time()
                reminders = session.query(Reminder).filter(Reminder.channel.in_([x.id for x in message.guild.channels]))

                for r in reminders:
                    r.time += t

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'offset/success').format(t)))


client = BotClient()

client.run(client.config.get('DEFAULT', 'token'), max_messages=50)
