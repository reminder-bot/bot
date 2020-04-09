import sys

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT, INTEGER as INT
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

Base = declarative_base()


class Guild(Base):
    __tablename__ = 'guilds'

    id = Column(INT(unsigned=True), primary_key=True)
    guild = Column(BIGINT(unsigned=True), unique=True)

    prefix = Column(String(5), default='$', nullable=False)
    timezone = Column(String(32), default='UTC', nullable=False)

    name = Column(String(100))


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


class Blacklist(Base):
    __tablename__ = 'blacklists'

    id = Column(Integer, primary_key=True)

    channel = Column(BigInteger, nullable=False, unique=True)
    guild_id = Column(BigInteger, ForeignKey(Guild.guild, ondelete='CASCADE'), nullable=False)


class ChannelNudge(Base):
    __tablename__ = 'nudge_channels'

    id = Column(Integer, primary_key=True)

    channel = Column(BigInteger, unique=True, nullable=False)
    time = Column(Integer, nullable=False)


class User(Base):
    __tablename__ = 'users'

    id = Column(INT(unsigned=True), primary_key=True, nullable=False)
    user = Column(BIGINT(unsigned=True), nullable=False, unique=True)

    name = Column(String(37), nullable=False)  # sized off 32 char username + # + 4 char discriminator

    language = Column(String(2), default='EN', nullable=False)
    timezone = Column(String(32))
    allowed_dm = Column(Boolean, default=True, nullable=False)

    patreon = Column(Boolean, nullable=False, default=False)
    dm_channel = Column(BIGINT(unsigned=True), nullable=False)


class ReminderOld(Base):
    __tablename__ = 'reminders_old'

    id = Column(Integer, primary_key=True)
    uid = Column(String(64), unique=True)

    message_id = Column(Integer, nullable=False)

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


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(INT(unsigned=True), primary_key=True)
    uid = Column(String(64), unique=True)

    message_id = Column(INT(unsigned=True), nullable=False)

    channel_id = Column(INT(unsigned=True), ForeignKey('channels.id'), nullable=False)

    time = Column(BIGINT(unsigned=True))
    enabled = Column(Boolean, nullable=False, default=True)

    avatar = Column(String(512),
                    default='https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg',
                    nullable=False)
    username = Column(String(32), default='Reminder', nullable=False)

    method = Column(String(9))
    interval = Column(INT(unsigned=True))


class TodoOld(Base):
    __tablename__ = 'todos_old'

    id = Column(Integer, primary_key=True)
    owner = Column(BigInteger, nullable=False)
    value = Column(Text, nullable=False)


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(INT(unsigned=True), primary_key=True)

    user_id = Column(INT(unsigned=True), ForeignKey(User.id))
    guild_id = Column(INT(unsigned=True), ForeignKey(Guild.id))

    value = Column(String(2000), nullable=False)


user = sys.argv[1]
password = sys.argv[2] if len(sys.argv) > 2 else None

if password is not None:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@localhost/reminders?charset=utf8mb4'.format(
        user=user, passwd=password))

else:
    engine = create_engine('mysql+pymysql://{user}@localhost/reminders?charset=utf8mb4'.format(user=user))

Base.metadata.create_all(bind=engine)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

count = 0

print('Processing users...')
for user in session.query(User):
    count += 1

    c = Channel(id=count, channel=user.dm_channel)

    session.add(c)

    user.dm_channel = count

    print(count)

session.commit()

print('Processing todos...')
for todo in session.query(TodoOld):
    u = session.query(User).filter(User.user == todo.owner).first() or \
        session.query(Guild).filter(Guild.guild == todo.owner).first()

    if u is not None:
        if isinstance(u, User):
            t = Todo(value=todo.value, user_id=u.id)
        else:
            t = Todo(value=todo.value, guild_id=u.id)

        session.add(t)

session.commit()

print('Processing blacklists...')
for blacklist in session.query(Blacklist):

    c = session.query(Channel).filter(Channel.channel == blacklist.channel).first()

    if c is None:
        g = session.query(Guild).filter(Guild.guild == blacklist.guild_id).first()

        if g is not None:
            c = Channel(channel=blacklist.channel, guild_id=g.id, blacklisted=True)
            session.add(c)
        else:
            continue
    else:
        c.blacklisted = True

session.commit()

print('Processing nudges...')
for nudge in session.query(ChannelNudge):

    if abs(nudge.time) < 2**15:
        c = session.query(Channel).filter(Channel.channel == nudge.channel).first()

        if c is None:
            c = Channel(channel=nudge.channel, nudge=nudge.time)
            session.add(c)
        else:
            c.nudge = nudge.time

session.commit()

print('Processing reminders...')
for reminder in session.query(ReminderOld):

    if reminder.webhook is not None and len(reminder.webhook) > 0:
        c = session.query(Channel).filter(Channel.channel == reminder.channel).first()

        _, webhook_id, webhook_token = reminder.webhook.rsplit('/', 2)

        if c is None:
            c = Channel(channel=reminder.channel, webhook_id=webhook_id, webhook_token=webhook_token)
            session.add(c)
            session.flush()

        new_reminder = Reminder(
            uid=reminder.uid,
            message_id=reminder.message_id,
            channel_id=c.id,
            time=reminder.time,
            enabled=reminder.enabled,
            avatar=reminder.avatar,
            username=reminder.username,
            method=reminder.method,
            interval=reminder.interval
        )

        session.add(new_reminder)

    else:
        c = session.query(Channel).filter(Channel.channel == reminder.channel).first()

        if c is None:
            c = Channel(channel=reminder.channel)
            session.add(c)
            session.flush()

        new_reminder = Reminder(
            uid=reminder.uid,
            message_id=reminder.message_id,
            channel_id=c.id,
            time=reminder.time,
            enabled=reminder.enabled,
            avatar=reminder.avatar,
            username=reminder.username,
            method=reminder.method,
            interval=reminder.interval
        )

        session.add(new_reminder)

session.commit()
