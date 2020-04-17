from enums import CreateReminderResponse
from discord import AllowedMentions

ALL_CHARACTERS: str = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_'

MAX_TIME: int = 1576800000
DAY_LENGTH: int = 86400

MAX_TIME_DAYS: int = MAX_TIME // DAY_LENGTH
MIN_INTERVAL: int = 800

REMIND_STRINGS: dict = {
    CreateReminderResponse.OK: 'remind/success',
    CreateReminderResponse.LONG_TIME: 'remind/long_time',
    CreateReminderResponse.LONG_INTERVAL: 'interval/long_interval',
    CreateReminderResponse.SHORT_INTERVAL: 'interval/short_interval',
    CreateReminderResponse.INVALID_TAG: 'remind/invalid_tag',
    CreateReminderResponse.PAST_TIME: 'remind/past_time',
}

NATURAL_STRINGS: dict = {
    CreateReminderResponse.LONG_TIME: 'natural/long_time',
}

NoMention: AllowedMentions = AllowedMentions(everyone=False, roles=False, users=False)