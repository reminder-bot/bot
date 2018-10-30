# Reminder Bot

## A bot for doing reminders

### Installing

#### Deps:

* Python 3.6+
* MySQL
* pymysql, discord.py==1.0.0a, pytz, dateparser, sqlalchemy, sqlalchemy-json

#### Running:

* Ensure the languages folder has your desired language files (a `git submodule init` should get all of them from the official repo, or check https://github.com/reminder-bot/languages for specifics)
* Log into MySQL and execute

```SQL
CREATE DATABASE reminders;
```

* Create file `config.ini` in the same location as `main.py`
* Fill it with the following stub:

```ini
[DEFAULT]
token =
dbl_token =
patreon_server =
patreon_enabled = no
strings_location = ./languages/

[MYSQL]
user = jude
;passwd =
host = localhost
database = reminders
```

* `python3 main.py`
