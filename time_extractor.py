import pytz
from datetime import datetime
from time import time as unix_time

from enums import TimeExtractionTypes


class InvalidTime(Exception):
    pass


class TimeExtractor:
    def __init__(self, string, timezone=None):
        self.timezone: str = timezone

        if len(string) > 0:
            self.inverted: bool = string[0] == '-'
        else:
            self.inverted: bool = False

        if self.inverted:
            self.time_string: str = string[1:]

        else:
            self.time_string: str = string

        if '/' in string or ':' in string:
            self.process_type = TimeExtractionTypes.EXPLICIT

        else:
            self.process_type = TimeExtractionTypes.DISPLACEMENT

    def extract_exact(self) -> int:  # produce a timestamp
        return int(self._process_spaceless())

    def extract_displacement(self) -> int:  # produce a relative time
        return int(round(self._process_spaceless() - unix_time()))

    def _process_spaceless(self) -> float:
        if self.process_type == TimeExtractionTypes.EXPLICIT:
            try:
                d = self._process_explicit()
            except ValueError:
                raise InvalidTime()
            return d

        else:
            d = self._process_displacement()
            return unix_time() + d

    def _process_explicit(self) -> float:  # processing times that dictate a specific time
        date = datetime.now(pytz.timezone(self.timezone))

        for clump in self.time_string.split('-'):
            if '/' in clump:
                a = clump.split('/')
                if len(a) == 2:
                    date = date.replace(month=int(a[1]), day=int(a[0]))
                elif len(a) == 3:
                    date = date.replace(year=int(a[2]), month=int(a[1]), day=int(a[0]))

            elif ':' in clump:
                a = clump.split(':')
                if len(a) == 2:
                    date = date.replace(hour=int(a[0]), minute=int(a[1]))
                elif len(a) == 3:
                    date = date.replace(hour=int(a[0]), minute=int(a[1]), second=int(a[2]))
                else:
                    raise InvalidTime()

            else:
                date = date.replace(day=int(clump))

        return date.timestamp()

    def _process_displacement(self) -> int:  # processing times that dictate a time relative to now
        current_buffer = '0'
        seconds = 0
        minutes = 0
        hours = 0
        days = 0

        for char in self.time_string:

            if char == 's':
                seconds = int(current_buffer)
                current_buffer = '0'

            elif char == 'm':
                minutes = int(current_buffer)
                current_buffer = '0'

            elif char == 'h':
                hours = int(current_buffer)
                current_buffer = '0'

            elif char == 'd':
                days = int(current_buffer)
                current_buffer = '0'

            else:
                try:
                    int(char)
                    current_buffer += char
                except ValueError:
                    raise InvalidTime()

        full = seconds + (minutes * 60) + (hours * 3600) + (days * 86400) + int(current_buffer)

        if self.inverted:
            full = -full

        return full
