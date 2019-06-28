from enums import CreateReminderResponse
from models import session, Language

ALL_CHARACTERS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_'

MAX_TIME = 1576800000
MIN_INTERVAL = 8

REMIND_STRINGS = {
    CreateReminderResponse.OK: 'remind/success',
    CreateReminderResponse.LONG_TIME: 'remind/long_time',
    CreateReminderResponse.LONG_INTERVAL: 'interval/long_interval',
    CreateReminderResponse.SHORT_INTERVAL: 'interval/short_interval',
    CreateReminderResponse.INVALID_TAG: 'remind/invalid_tag',
}

NATURAL_STRINGS = {
    CreateReminderResponse.LONG_TIME: 'natural/long_time',
}

ENGLISH_STRINGS = session.query(Language).filter(Language.code == 'EN').first()
