from configparser import SafeConfigParser as ConfigParser
import typing

class Config():
    def __init__(self):
        config = ConfigParser()
        config.read('config.ini')

        self.donor_role: int = int(config.get('DEFAULT', 'patreon_role'))

        self.dbl_token: str = config.get('DEFAULT', 'dbl_token')
        self.token: str = config.get('DEFAULT', 'token')

        self.patreon: bool = config.get('DEFAULT', 'patreon_enabled') == 'yes'
        self.patreon_server: int = int(config.get('DEFAULT', 'patreon_server'))
