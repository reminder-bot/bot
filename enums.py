from enum import Enum, IntEnum


# enumerate possible error types from the remind and natural commands
class CreateReminderResponse(Enum):
    OK = 0
    LONG_TIME = 1
    LONG_INTERVAL = 2
    SHORT_INTERVAL = 3
    INVALID_TAG = 5
    PAST_TIME = 6


# enumerate possible permission levels for command execution
class PermissionLevels(IntEnum):
    UNRESTRICTED = 0
    MANAGED = 1
    RESTRICTED = 2

    def __str__(self):
        strings = ('', 'no_perms_managed', 'no_perms_restricted')

        return strings[self.value]


class TimeExtractionTypes(Enum):
    EXPLICIT = 0
    DISPLACEMENT = 1
