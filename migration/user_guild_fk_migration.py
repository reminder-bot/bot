import sys

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Table, ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship

Base = declarative_base()



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