from tinyconf.deserializers import IniDeserializer
from tinyconf.fields import IntegerField, Field, BooleanField
from tinyconf.section import Section


class Config(IniDeserializer):
    patreon_role = IntegerField()
    patreon_server = IntegerField()
    patreon_enabled = BooleanField()

    dbl_token = Field()
    token = Field(strict=True)

    local_timezone = Field(default='UTC')

    DEFAULT = Section(patreon_role, patreon_server, patreon_enabled, dbl_token, token, local_timezone)
