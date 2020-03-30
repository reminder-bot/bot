from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table, ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMINT, INTEGER as INT
import configparser
import time
import typing
import secrets

from consts import ALL_CHARACTERS

Base = declarative_base()


class Guild(Base):
    __tablename__ = 'guilds'

    id = Column(INT(unsigned=True), primary_key=True)
    guild = Column(BIGINT(unsigned=True), unique=True)

    prefix = Column( String(5), default='$', nullable=False )
    timezone = Column( String(32), default='UTC', nullable=False )

    command_restrictions = relationship('CommandRestriction', backref='guild', lazy='dynamic')


class Channel(Base):
    __tablename__ = 'channels'

    id = Column(INT(unsigned=True), primary_key=True)
    channel = Column(BIGINT(unsigned=True), unique=True)
    name = Column(String(100))

    webhook_id = Column(BIGINT(unsigned=True), unique=True)
    webhook_token = Column(Text)

    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id, ondelete='CASCADE'), nullable=False)
    guild = relationship(Guild)


class Role(Base):
    __tablename__ = 'roles'

    id = Column(INT(unsigned=True), primary_key=True)
    role = Column(BIGINT(unsigned=True), unique=True, nullable=False)
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id), nullable=False)

    name = Column(String(100))


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, nullable=False)
    user = Column(BigInteger, nullable=False)

    language = Column( String(2), default='EN', nullable=False )
    timezone = Column( String(32), nullable=True )
    allowed_dm = Column( Boolean, default=True, nullable=False )

    patreon = Column( Boolean, nullable=False, default=False )
    dm_channel = Column(BigInteger)
    name = Column(String(37))  # sized off 32 char username + # + 4 char discriminator

    def __repr__(self):
        return self.name or str(self.user)

    def __str__(self):
        return self.name or str(self.user)


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

    channel_id = Column(INT(unsigned=True), ForeignKey(Channel.id), nullable=False)
    channel = relationship(Channel, backref='reminders')

    user_id = Column(INT(unsigned=True), ForeignKey(User.id), nullable=False)
    user = relationship(User)

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


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True)
    owner = Column(BigInteger, nullable=False)
    value = Column(Text, nullable=False)


class Blacklist(Base):
    __tablename__ = 'blacklists'

    id = Column(Integer, primary_key=True)

    channel = Column(BigInteger, nullable=False, unique=True)
    guild_id = Column(BigInteger, ForeignKey(Guild.guild, ondelete='CASCADE'), nullable=False)


class Timer(Base):
    __tablename__ = 'timers'

    id = Column(Integer, primary_key=True)

    start_time = Column(Integer, default=time.time, nullable=False)
    name = Column( String(32), nullable=False )
    owner = Column( BigInteger, nullable=False )


class Language(Base):
    __tablename__ = 'languages'

    id = Column(Integer, primary_key=True)

    name = Column( String(20), nullable=False, unique=True )
    code = Column( String(2), nullable=False, unique=True )

    def get_string(self, string):
        s = session.query(Strings).filter(Strings.c.name == string)
        req = getattr(s.first(), 'value_{}'.format(self.code))

        return req if req is not None else s.first().value_EN


class ChannelNudge(Base):
    __tablename__ = 'nudge_channels'

    id = Column(Integer, primary_key=True)

    channel = Column(BigInteger, unique=True, nullable=False)
    time = Column(Integer, nullable=False)


class CommandRestriction(Base):
    __tablename__ = 'command_restrictions'

    id = Column(Integer, primary_key=True)

    guild_id = Column(BigInteger, ForeignKey(Guild.guild, ondelete='CASCADE'), nullable=False)
    role = Column(BigInteger, nullable=False)
    command = Column(String(16))


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
