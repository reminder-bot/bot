from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy_json import NestedMutableJson, MutableJson
import configparser
import os


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
    message = Column(String(2000))
    channel = Column(BigInteger)
    time = Column(BigInteger)
    interval = Column(Integer)

    webhook = Column(String(200))
    avatar = Column(Text)
    username = Column(String(32))

    method = Column(Text)
    embed = Column(Integer, nullable=True)

    def __repr__(self):
        return '<Reminder "{}" <#{}> {}s>'.format(self.message, self.channel, self.time)


class Server(Base):
    __tablename__ = 'servers'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    prefix = Column( String(5) )
    language = Column( String(2) )
    timezone = Column( String(30) )
    blacklist = Column( NestedMutableJson )
    restrictions = Column( NestedMutableJson )

    def __repr__(self):
        return '<Server {}>'.format(self.id)


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True)
    owner = Column(BigInteger)
    value = Column(Text)


languages = []

for fn in os.listdir(config.get('DEFAULT', 'strings_location')):
    if fn.startswith('strings_'):
        languages.append(fn[8:10])


Strings = Table('strings', Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text),
    *(
        Column('value_{}'.format(lang), Text) for lang in languages
    )
)


if passwd:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=user, passwd=passwd, host=host, db=database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=user, host=host, db=database))
Base.metadata.create_all(bind=engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()
