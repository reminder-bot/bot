from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table, ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import configparser
import os
import time


config = configparser.SafeConfigParser()
config.read('config.ini')
user = config.get('MYSQL', 'USER')
try:
    passwd = config.get('MYSQL', 'PASSWD')
except:
    passwd = None
host = config.get('MYSQL', 'HOST')
database = config.get('MYSQL', 'DATABASE')

Base = declarative_base()

class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True, unique=True)
    uid = Column(String(64))
    
    message = Column(String(2000))
    channel = Column(BigInteger)
    time = Column(BigInteger)
    webhook = Column(String(256))
    enabled = Column(Boolean, nullable=False, default=True)
    
    position = Column(Integer)

    avatar = Column(String(512), default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg', nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)
    embed = Column(Integer, nullable=True)

    method = Column(String(9))


class Interval(Base):
    __tablename__ = 'intervals'

    id = Column(Integer, primary_key=True, unique=True)

    reminder = Column(Integer, ForeignKey('reminders.id'))
    period = Column(Integer)
    position = Column(Integer)


class Server(Base):
    __tablename__ = 'servers'

    id = Column(Integer, primary_key=True)
    server = Column(BigInteger, unique=True)
    
    prefix = Column( String(5), default="$", nullable=False )
    timezone = Column( String(32), default="UTC", nullable=False )


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    user = Column(BigInteger, unique=True, nullable=False)

    language = Column( String(2), default="EN", nullable=False )
    timezone = Column( String(32), nullable=True )
    allowed_dm = Column( Boolean, default=True, nullable=False )


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True)
    owner = Column(BigInteger, nullable=False)
    value = Column(Text, nullable=False)


class Blacklist(Base):
    __tablename__ = 'blacklists'

    id = Column(Integer, primary_key=True)
    channel = Column(BigInteger, nullable=False, unique=True)
    server = Column(BigInteger, nullable=False)


class RoleRestrict(Base):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    role = Column(BigInteger, nullable=False, unique=True)
    server = Column(BigInteger, nullable=False)


class Timer(Base):
    __tablename__ = 'timers'

    id = Column(Integer, primary_key=True)
    start_time = Column(Integer, default=time.time, nullable=False)
    name = Column( String(32), nullable=False )
    owner = Column( BigInteger, nullable=False )


class Language(Base):
    __tablename__ = 'languages'

    id = Column(Integer, primary_key=True)
    name = Column( String(20), nullable=False )
    code = Column( String(2), nullable=False )

    def get_string(self, string):
        s = session.query(Strings).filter(Strings.c.name == string)
        req = getattr(s.first(), 'value_{}'.format(self.code))

        return req if req is not None else s.first().value_EN


class ChannelNudge(Base):
    __tablename__ = 'nudge_channels'

    id = Column(Integer, primary_key=True)
    channel = Column(BigInteger, unique=True, nullable=False)
    time = Column(Integer, nullable=False)


if passwd:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=user, passwd=passwd, host=host, db=database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=user, host=host, db=database))
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