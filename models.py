from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table, ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, backref
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMINT, SMALLINT, INTEGER as INT
import configparser
import time
import typing
import secrets

from consts import ALL_CHARACTERS

Base = declarative_base()

guild_users = Table('guild_users',
                    Base.metadata,
                    Column('guild', INT(unsigned=True), ForeignKey('guilds.id')),
                    Column('user', INT(unsigned=True), ForeignKey('users.id')),
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
    async def get_or_create(cls, finding_channel) -> ('Channel', bool):
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
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id), nullable=False)


class User(Base):
    __tablename__ = 'users'

    id = Column(INT(unsigned=True), primary_key=True, nullable=False)
    user = Column(BIGINT(unsigned=True), nullable=False, unique=True)

    name = Column(String(37), nullable=False)  # sized off 32 char username + # + 4 char discriminator

    language = Column(String(2), default='EN', nullable=False)
    timezone = Column(String(32))
    allowed_dm = Column(Boolean, default=True, nullable=False)

    patreon = Column(Boolean, nullable=False, default=False)
    dm_channel = Column(INT(unsigned=True), ForeignKey('channels.id'), nullable=False)
    channel = relationship(Channel)

    def __repr__(self):
        return self.name or str(self.user)

    def __str__(self):
        return self.name or str(self.user)

    @classmethod
    def from_discord(cls, finding_user):
        return session.query(cls).filter(cls.user == finding_user.id).first()

    @classmethod
    async def get_or_create(cls, finding_user) -> ('User', bool):
        u = session.query(User).filter(User.user == finding_user.id).first()
        channel_id = (await finding_user.create_dm()).id
        new = False

        c = session.query(Channel).filter(Channel.channel == channel_id).first()

        if c is None:
            c = Channel(channel=channel_id)
            session.add(c)
            session.flush()

        if u is None:
            u = User(user=finding_user.id, dm_channel=c.id, name='{}#{}'.format(
                finding_user.name, finding_user.discriminator))
            session.add(u)
            new = True

        session.flush()
        return u, new

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

    embed_id = Column(INT(unsigned=True), ForeignKey(Embed.id))
    embed = relationship(Embed)


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(INT(unsigned=True), primary_key=True)
    uid = Column(String(64), default=lambda: Reminder.create_uid(), unique=True)

    message_id = Column(INT(unsigned=True), ForeignKey(Message.id), nullable=False)
    message = relationship(Message)

    channel_id = Column(INT(unsigned=True), ForeignKey(Channel.id), nullable=True)

    time = Column(BIGINT(unsigned=True))
    enabled = Column(Boolean, nullable=False, default=True)

    avatar = Column(String(512),
                    default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg',
                    nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)

    method = Column(String(9))
    interval = Column(INT(unsigned=True))

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

    user_id = Column(INT(unsigned=True), ForeignKey(User.id))
    user = relationship(User, backref='todo_list')
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id))
    guild = relationship(Guild, backref='todo_list')

    value = Column(String(2000), nullable=False)


class Timer(Base):
    __tablename__ = 'timers'

    id = Column(Integer, primary_key=True)

    start_time = Column(Integer, default=time.time, nullable=False)
    name = Column(String(32), nullable=False)
    owner = Column(BigInteger, nullable=False)


class Language(Base):
    __tablename__ = 'languages'

    id = Column(Integer, primary_key=True)

    name = Column(String(20), nullable=False, unique=True)
    code = Column(String(2), nullable=False, unique=True)

    def get_string(self, string):
        s = session.query(Strings).filter(Strings.c.name == string)
        req = getattr(s.first(), 'value_{}'.format(self.code))

        return req if req is not None else s.first().value_EN


class CommandRestriction(Base):
    __tablename__ = 'command_restrictions'

    id = Column(Integer, primary_key=True)

    guild_id = Column(BigInteger, ForeignKey(Guild.guild, ondelete='CASCADE'), nullable=False)
    role = Column(BigInteger, nullable=False)
    command = Column(String(16))


Guild.command_restrictions = relationship(CommandRestriction, backref='guild', lazy='dynamic')

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

ENGLISH_STRINGS: typing.Optional[Language] = session.query(Language).filter(Language.code == 'EN').first()
