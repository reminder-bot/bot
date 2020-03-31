USE reminders;

CREATE TABLE reminders.guilds (
    id INT UNSIGNED UNIQUE NOT NULL AUTO_INCREMENT,
    guild BIGINT UNSIGNED UNIQUE NOT NULL,

    prefix VARCHAR(5) DEFAULT '$' NOT NULL,
    timezone VARCHAR(32) DEFAULT 'UTC' NOT NULL,

    name VARCHAR(100),

    PRIMARY KEY (id)
);

CREATE TABLE reminders.users (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    user BIGINT UNSIGNED UNIQUE NOT NULL,

    language VARCHAR(2) DEFAULT 'EN' NOT NULL,
    timezone VARCHAR(32),
    allowed_dm BOOLEAN DEFAULT 1 NOT NULL,

    patreon BOOL NOT NULL DEFAULT 0,
    dm_channel BIGINT UNSIGNED UNIQUE,
    name VARCHAR(37) UNIQUE,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.roles (
    id INT UNSIGNED UNIQUE NOT NULL AUTO_INCREMENT,
    role BIGINT UNSIGNED UNIQUE NOT NULL,

    guild_id INT UNSIGNED NOT NULL,

    name VARCHAR(100),

    PRIMARY KEY (id),
    FOREIGN KEY (guild_id) REFERENCES reminders.guilds(id) ON DELETE CASCADE
);

CREATE TABLE reminders.channels (
    id INT UNSIGNED UNIQUE NOT NULL AUTO_INCREMENT,
    channel BIGINT UNSIGNED UNIQUE NOT NULL,

    name VARCHAR(100),

    webhook_id BIGINT UNSIGNED UNIQUE,
    webhook_token TEXT,

    guild_id INT UNSIGNED NOT NULL,

    PRIMARY KEY (id),
    FOREIGN KEY (guild_id) REFERENCES reminders.guilds(id) ON DELETE CASCADE
);

CREATE TABLE reminders.embeds (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,

    title VARCHAR(256) NOT NULL DEFAULT '',
    description VARCHAR(2048) NOT NULL DEFAULT '',
    color MEDIUMINT UNSIGNED NOT NULL DEFAULT 0x0,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.messages (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,

    content VARCHAR(2048) NOT NULL DEFAULT '',
    embed_id INT UNSIGNED,

    PRIMARY KEY (id),
    FOREIGN KEY (embed_id) REFERENCES reminders.embeds(id)
);

CREATE TABLE reminders.reminders (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    uid VARCHAR(64) UNIQUE NOT NULL,
    
    message_id INT UNSIGNED NOT NULL,

    channel_id INT UNSIGNED,
    user_id INT UNSIGNED,

    `time` INT UNSIGNED DEFAULT 0 NOT NULL,
    `interval` INT UNSIGNED DEFAULT NULL,

    enabled BOOLEAN DEFAULT 1 NOT NULL,

    avatar VARCHAR(512) DEFAULT 'https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg' NOT NULL,
    username VARCHAR(32) DEFAULT 'Reminder' NOT NULL,

    method VARCHAR(9),

    PRIMARY KEY (id),
    FOREIGN KEY (message_id) REFERENCES reminders.messages(id),
    FOREIGN KEY (channel_id) REFERENCES reminders.channels(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES reminders.users(id) ON DELETE CASCADE
);

CREATE TRIGGER message_cleanup AFTER DELETE ON reminders.reminders
FOR EACH ROW
    DELETE FROM reminders.messages WHERE id = OLD.message_id;

CREATE TRIGGER embed_cleanup AFTER DELETE ON reminders.messages
FOR EACH ROW
    DELETE FROM reminders.embeds WHERE id = OLD.embed_id;

CREATE TABLE reminders.todos (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    owner BIGINT UNSIGNED NOT NULL,
    value TEXT,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.blacklists (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,

    channel BIGINT UNSIGNED UNIQUE NOT NULL,
    guild_id BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id),
    FOREIGN KEY (guild_id) REFERENCES reminders.guilds(guild) ON DELETE CASCADE
);

CREATE TABLE reminders.command_restrictions (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    
    guild_id BIGINT UNSIGNED NOT NULL,
    role BIGINT UNSIGNED NOT NULL,
    command VARCHAR(16) NOT NULL,

    PRIMARY KEY (id),
    FOREIGN KEY (guild_id) REFERENCES reminders.guilds(guild) ON DELETE CASCADE
);

CREATE TABLE reminders.timers (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    start_time INT UNSIGNED DEFAULT (UNIX_TIMESTAMP()) NOT NULL,
    name VARCHAR(32) NOT NULL,
    owner BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.nudge_channels (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    channel BIGINT UNSIGNED UNIQUE NOT NULL,
    `time` INT NOT NULL,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.languages (
    id SMALLINT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    name VARCHAR(20) NOT NULL,
    code VARCHAR(2) NOT NULL,

    PRIMARY KEY (id)
);
-- MUST RUN to_database.py TO FORM STRING STORES