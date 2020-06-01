from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, Boolean, Table, ForeignKey, UniqueConstraint
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, backref
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMINT, SMALLINT, INTEGER as INT, TIMESTAMP, ENUM
import configparser
from datetime import datetime
import typing
import secrets

from consts import ALL_CHARACTERS

Base = declarative_base()

guild_users = Table('guild_users',
                    Base.metadata,
                    Column('guild', INT(unsigned=True), ForeignKey('guilds.id', ondelete='CASCADE'), nullable=False),
                    Column('user', INT(unsigned=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
                    Column('can_access', Boolean, nullable=False, default=False),
                    UniqueConstraint('guild', 'user'),
                    )


class Guild(Base):
    __tablename__ = 'guilds'

    id = Column(INT(unsigned=True), primary_key=True)
    guild = Column(BIGINT(unsigned=True), unique=True)

    prefix = Column(String(5), default='$', nullable=False)
    timezone = Column(String(32), default='UTC', nullable=False)

    name = Column(String(100))

    users = relationship(
        'User', secondary=guild_users,
        primaryjoin=(guild_users.c.guild == id),
        secondaryjoin='(guild_users.c.user == User.id)',
        backref=backref('guilds', lazy='dynamic'), lazy='dynamic'
    )

    # populated later in file
    command_restrictions = None
    roles = None


class CommandAlias(Base):
    __tablename__ = 'command_aliases'

    id = Column(INT(unsigned=True), primary_key=True)

    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'), nullable=False)
    guild = relationship(Guild, backref='aliases')
    name = Column(String(12), nullable=False)

    command = Column(String(2048), nullable=False)

    UniqueConstraint('guild_id', 'name')


class Channel(Base):
    __tablename__ = 'channels'

    id = Column(INT(unsigned=True), primary_key=True)
    channel = Column(BIGINT(unsigned=True), unique=True)

    name = Column(String(100))

    nudge = Column(SMALLINT, nullable=False, default=0)
    blacklisted = Column(Boolean, nullable=False, default=False)

    webhook_id = Column(BIGINT(unsigned=True), unique=True)
    webhook_token = Column(Text)

    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'))
    guild = relationship(Guild, backref='channels')

    def __repr__(self):
        return '<#{}>'.format(self.channel)

    def __str__(self):
        return '<#{}>'.format(self.channel)

    @classmethod
    def get_or_create(cls, finding_channel) -> ('Channel', bool):
        c = session.query(cls).filter(cls.channel == finding_channel.id).first()
        new = False

        if c is None:
            g = session.query(Guild).filter(Guild.guild == finding_channel.guild.id).first()

            gid = None if g is None else g.id

            c = Channel(
                channel=finding_channel.id,
                name=finding_channel.name,
                guild_id=gid
            )

            session.add(c)
            new = True

        else:
            c.name = finding_channel.name

        session.flush()
        return c, new

    async def attach_webhook(self, channel):
        if (self.webhook_token or self.webhook_id) is None:
            hook = await channel.create_webhook(name='Reminders')

            self.webhook_token = hook.token
            self.webhook_id = hook.id


class Role(Base):
    __tablename__ = 'roles'

    id = Column(INT(unsigned=True), primary_key=True)
    name = Column(String(100))

    role = Column(BIGINT(unsigned=True), unique=True, nullable=False)
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'), nullable=False)

    def __eq__(self, v):
        if isinstance(v, int):
            return self.role == v

        elif isinstance(v, Role):
            return self.id == v.id

        else:
            return False

    def __str__(self):
        return '<@&{}>'.format(self.role)


class User(Base):
    __tablename__ = 'users'

    id = Column(INT(unsigned=True), primary_key=True, nullable=False)
    user = Column(BIGINT(unsigned=True), nullable=False, unique=True)

    name = Column(String(37), nullable=False)  # sized off 32 char username + # + 4 char discriminator

    language = Column(String(2), default='EN', nullable=False)
    timezone = Column(String(32))
    allowed_dm = Column(Boolean, default=True, nullable=False)

    patreon = Column(Boolean, nullable=False, default=False)
    dm_channel = Column(INT(unsigned=True), ForeignKey('channels.id', ondelete='SET NULL'), nullable=False)
    channel = relationship(Channel)

    def __repr__(self):
        return self.name or str(self.user)

    def __str__(self):
        return self.name or str(self.user)

    @classmethod
    def from_discord(cls, finding_user):
        return session.query(cls).filter(cls.user == finding_user.id).first()

    async def update_details(self, new_details):
        self.name = '{}#{}'.format(new_details.name, new_details.discriminator)

        if self.dm_channel is None:
            self.dm_channel = (await new_details.create_dm()).id


class Embed(Base):
    __tablename__ = 'embeds'

    id = Column(INT(unsigned=True), primary_key=True)

    title = Column(String(256), nullable=False, default='')
    description = Column(String(2048), nullable=False, default='')
    color = Column(MEDIUMINT(unsigned=True))


class Message(Base):
    __tablename__ = 'messages'

    id = Column(INT(unsigned=True), primary_key=True)

    content = Column(String(2048), nullable=False, default='')

    embed_id = Column(INT(unsigned=True), ForeignKey(Embed.id, ondelete='CASCADE'))
    embed = relationship(Embed)


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(INT(unsigned=True), primary_key=True)
    uid = Column(String(64), default=lambda: Reminder.create_uid(), unique=True)

    name = Column(String(24), default='Reminder')

    message_id = Column(INT(unsigned=True), ForeignKey(Message.id, ondelete='RESTRICT'), nullable=False)
    message = relationship(Message)

    channel_id = Column(INT(unsigned=True), ForeignKey(Channel.id, ondelete='CASCADE'), nullable=True)

    time = Column(INT(unsigned=True))
    enabled = Column(Boolean, nullable=False, default=True)

    avatar = Column(String(512),
                    default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg',
                    nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)

    interval = Column(INT(unsigned=True))

    method = Column(ENUM('remind', 'natural', 'dashboard'))
    set_by = Column(INT(unsigned=True), ForeignKey(User.id, ondelete='SET NULL'), nullable=True)
    set_at = Column(TIMESTAMP, nullable=True, default=datetime.now, server_default='CURRENT_TIMESTAMP()')

    @staticmethod
    def create_uid() -> str:
        full: str = ''
        while len(full) < 64:
            full += secrets.choice(ALL_CHARACTERS)

        return full

    def message_content(self):
        if len(self.message.content) > 0:
            return self.message.content

        elif self.message.embed is not None:
            return self.message.embed.description

        else:
            return ''


Channel.reminders = relationship(Reminder, backref='channel', lazy='dynamic')


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(INT(unsigned=True), primary_key=True)

    user_id = Column(INT(unsigned=True), ForeignKey(User.id, ondelete='CASCADE'))
    user = relationship(User, backref='todo_list')
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'))
    guild = relationship(Guild, backref='todo_list')

    value = Column(String(2000), nullable=False)


class Timer(Base):
    __tablename__ = 'timers'

    id = Column(INT(unsigned=True), primary_key=True)

    start_time = Column(TIMESTAMP, default=datetime.now, server_default='CURRENT_TIMESTAMP()', nullable=False)
    name = Column(String(32), nullable=False)
    owner = Column(BIGINT(unsigned=True), nullable=False)


class Event(Base):
    __tablename__ = 'events'

    id = Column(INT(unsigned=True), primary_key=True)
    time = Column(TIMESTAMP, default=datetime.now, server_default='CURRENT_TIMESTAMP()', nullable=False)

    event_name = Column(ENUM('edit', 'enable', 'disable', 'delete'), nullable=False)
    bulk_count = Column(INT(unsigned=True))

    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'), nullable=False)
    guild = relationship(Guild)

    user_id = Column(INT(unsigned=True), ForeignKey(User.id, ondelete='SET NULL'))
    user = relationship(User)

    reminder_id = Column(INT(unsigned=True), ForeignKey(Reminder.id, ondelete='SET NULL'))


class Language(Base):
    __tablename__ = 'languages'

    id = Column(Integer, primary_key=True)

    name = Column(String(20), nullable=False, unique=True)
    code = Column(String(2), nullable=False, unique=True)

    def get_string(self, string):
        s = session.query(Strings).filter(Strings.c.name == string)
        req = getattr(s.first(), 'value_{}'.format(self.code))

        return req if req is not None else s.first().value_EN

    def __getitem__(self, item):
        return self.get_string(item)


class CommandRestriction(Base):
    __tablename__ = 'command_restrictions'

    id = Column(Integer, primary_key=True)

    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'), nullable=False)
    role_id = Column(INT(unsigned=True), ForeignKey(Role.id, ondelete='CASCADE'), nullable=False)
    role = relationship(Role)
    command = Column(ENUM('todos', 'natural', 'remind', 'interval', 'timer', 'del', 'look'), nullable=False)

    UniqueConstraint('role_id', 'command')


Guild.command_restrictions = relationship(CommandRestriction, backref='guild', lazy='dynamic')
Guild.roles = relationship(Role, backref='guild', lazy='dynamic')

config = configparser.ConfigParser()
config.read('config.ini')
user = config.get('MYSQL', 'USER')
password: typing.Optional[str] = None

try:
    password = config.get('MYSQL', 'PASSWD')
except KeyError:
    password = None

host = config.get('MYSQL', 'HOST')
database = config.get('MYSQL', 'DATABASE')

if password is not None:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(
        user=user, passwd=password, host=host, db=database))

else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(
        user=user, host=host, db=database))

Base.metadata.create_all(bind=engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

languages = session.query(Language.code).all()

Strings = Table('strings', Base.metadata,
                Column('id', Integer, primary_key=True),
                Column('name', Text),
                *(
                    Column('value_{}'.format(lang[0]), Text) for lang in languages
                )
                )

ENGLISH_STRINGS: typing.Optional[Language] = session.query(Language) \
    .filter(Language.code == config.get('DEFAULT', 'local_language')).first()
