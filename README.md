# Reminder Bot

## A bot for doing reminders

### Installing

#### Deps:

* MySQL 8+
* Python 3.8+
* pymysql, discord.py>=1.3.0a, pytz, dateparser, sqlalchemy, tinyconf, aiohttp
* libmysqlclient21 and libmysqlclient-dev
* Rust 1.42 with Cargo (for compilation only)

#### Optional Deps:

* Mypy (for static type checking if modifying code)

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
patreon_enabled = no
patreon_server =
patreon_role =
strings_location = ./languages/
local_timezone = UTC
local_language = EN
ignore_bots = 1

[SHARDS]
min_shard = 0
max_shard = 0
shard_count = 1

[MYSQL]
user = 
;passwd =
host = localhost
database = reminders
```

* Insert values into `token` and `user` for your MySQL setup and your bot's authorization token (can be found at https://discordapp.com/developers/applications)
* Set `local_timezone` to a time region that is representative of your local time. For example, for the UK this is *Europe/London*
* `python3 main.py` to test all that's okay

* Clone down the postman (https://github.com/reminder-bot/postman-rs)
* Move to the directory and perform `cargo build --release` to compile it
* Create a file `.env` and fill with the following:

```
DISCORD_TOKEN="auth token as above"
DATABASE_URL="mysql://user:passwd@localhost/reminders"
INTERVAL=15
```
N: You can change `INTERVAL` to be higher for less CPU usage or lower for reminders that are more on time. Any value less than 15 is fairly excessive; the live bot uses 5. Interval is the number of seconds between checking for reminders.

N: **ON OLDER VERSIONS ONLY** Modifying the `THREADS` value is NOT recommended. This increases the amount of threads used for sending reminders. If you're sending many reminders in a single interval, increase this value. The live bot uses 1. New versions only run on one thread with asynchronous capability provided by Tokio and Reqwest

* Run the release binary in `./target/release` alongside the python file.
