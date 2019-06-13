# Reminder Bot

## A bot for doing reminders

### Installing

#### Deps:

* Python 3.6+
* MySQL
* pymysql, [discord.py==1.2.2j](https://github.com/jellywx/discord.py), pytz, dateparser, sqlalchemy, sqlalchemy-json
* Rust 1.31 with Cargo

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
user = 
;passwd =
host = localhost
database = reminders
```

* Insert values into `token` and `user` for your MySQL setup and your bot's authorization token (can be found at https://discordapp.com/developers/applications)
* `python3 main.py` to test all that's okay

* Clone down the postman (https://github.com/reminder-bot/postman-rs)
* Move to the directory and perform `cargo build --release` to compile it
* Create a file `.env` and fill with the following:

```
DISCORD_TOKEN="auth token as above"
SQL_URL="mysql://user:passwd@localhost/reminders"
INTERVAL=15
THREADS=1
```
N: You can change `INTERVAL` to be higher for less CPU usage or lower for reminders that are more on time. Any value less than 15 is fairly excessive; the live bot uses 5. Modifying the `THREADS` value is NOT recommended. This increases the amount of threads used for sending reminders. If you're sending many reminders in a single interval, increase this value. The live bot uses 1.

* Run the release binary in `./target/release` alongside the python file.