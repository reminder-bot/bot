import sys

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table, ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship

Base = declarative_base()


class Embed(Base):
    __tablename__ = 'embeds'

    id = Column(Integer, primary_key=True)

    title = Column(String(256), nullable=False, default='')
    description = Column(String(2048), nullable=False, default='')
    color = Column(Integer)


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)

    content = Column(String(2048), nullable=False, default='')

    embed_id = Column(Integer, ForeignKey(Embed.id))
    embed = relationship(Embed)


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True)
    uid = Column(String(64), unique=True)

    message = Column(String(2000))

    channel = Column(BigInteger)
    time = Column(BigInteger)
    webhook = Column(String(256))
    enabled = Column(Boolean, nullable=False, default=True)

    avatar = Column(String(512),
                    default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg',
                    nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)
    embed = Column(Integer, nullable=True)

    method = Column(String(9))
    interval = Column(Integer)


class ReminderNew(Base):
    __tablename__ = 'reminders_new'

    id = Column(Integer, primary_key=True)
    uid = Column(String(64), unique=True)

    message_id = Column(Integer, ForeignKey(Message.id), nullable=False)
    message = relationship(Message)

    channel = Column(BigInteger)
    time = Column(BigInteger)
    webhook = Column(String(256))
    enabled = Column(Boolean, nullable=False, default=True)

    avatar = Column(String(512),
                    default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg',
                    nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)

    method = Column(String(9))
    interval = Column(Integer)


user = sys.argv[1]
password = sys.argv[2] if len(sys.argv) > 2 else None

if password is not None:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@localhost/reminders?charset=utf8mb4'.format(
        user=user, passwd=password))

else:
    engine = create_engine('mysql+pymysql://{user}@localhost/reminders?charset=utf8mb4'.format(
        user=user))

Base.metadata.create_all(bind=engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

for reminder in session.query(Reminder):
    if reminder.embed:
        r = ReminderNew(
            uid=reminder.uid,
            channel=reminder.channel,
            webhook=reminder.webhook,
            time=reminder.time,
            interval=reminder.interval,
            enabled=reminder.enabled,
            avatar=reminder.avatar,
            username=reminder.username,
            method=reminder.method,
            message=Message(content="", embed=Embed(description=reminder.message, color=reminder.embed, title="")))

    else:
        r = ReminderNew(
            uid=reminder.uid,
            channel=reminder.channel,
            webhook=reminder.webhook,
            time=reminder.time,
            interval=reminder.interval,
            enabled=reminder.enabled,
            avatar=reminder.avatar,
            username=reminder.username,
            method=reminder.method,
            message=Message(content=reminder.message))

    session.add(r)

session.commit()
