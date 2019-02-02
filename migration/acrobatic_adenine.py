from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy_json import NestedMutableJson
import configparser
import json


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


class ServerOld(Base):
    __tablename__ = 'servers_old'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    prefix = Column( String(5) )
    language = Column( String(2) )
    timezone = Column( String(30) )
    blacklist = Column( NestedMutableJson )
    restrictions = Column( NestedMutableJson )


class ReminderOld(Base):
    __tablename__ = 'reminders_old'

    id = Column(Integer, primary_key=True, unique=True)
    message = Column(Unicode(2000))
    channel = Column(BigInteger)
    time = Column(BigInteger)
    interval = Column(Integer)

    webhook = Column(String(200))
    avatar = Column(Text)
    username = Column(String(32))

    method = Column(Text)
    embed = Column(Integer, nullable=True)


class Interval(Base):
    __tablename__ = 'intervals'

    id = Column(Integer, primary_key=True, unique=True)

    reminder = Column(Integer, ForeignKey('reminders.id'))
    period = Column(Integer)
    position = Column(Integer)



with open('todos.json', 'r') as f:
    todos = json.load(f)
    todos = {int(x) : y for x, y in todos.items()}


if passwd:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=user, passwd=passwd, host=host, db=database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=user, host=host, db=database))
Base.metadata.create_all(bind=engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

for server in session.query(ServerOld):
    blacklist = server.blacklist['data']
    for channel in set(blacklist):
        b = Blacklist(channel=channel, server=server.id)
        session.add(b)

    restrictions = server.restrictions['data']

    print(restrictions)
    for restriction in set(restrictions):
        r = RoleRestrict(role=restriction, server=server.id)
        session.add(r)

session.commit()


for reminder in session.query(ReminderOld).filter(Reminder.interval != None):
    i = Interval(reminder=reminder.id, period=reminder.interval, position=0)
    session.add(i)

session.commit()

for key, value in todos.items():
    for v in value:
        t = Todo(owner=key, value=v)
        session.add(t)

session.commit()