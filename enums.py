from enum import Enum

# enumerate possible error types from the remind and natural commands
class CreateReminderResponse(Enum):
    OK = 0
    LONG_TIME = 1
    LONG_INTERVAL = 2
    SHORT_INTERVAL = 3
    INVALID_TAG = 5


# enumerate possible permission levels for command execution
class PermissionLevels(Enum):
    UNRESTRICTED = 0
    MANAGED = 1
    RESTRICTED = 2


class TimeExtractionTypes(Enum):
    EXPLICIT = 0
    DISPLACEMENT = 1
