CREATE TABLE reminders.reminders (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    uid VARCHAR(64) UNIQUE NOT NULL,
    
    message VARCHAR(2000) NOT NULL,
    channel BIGINT UNSIGNED NOT NULL,
    `time` INT UNSIGNED DEFAULT 0 NOT NULL,

    `interval` INT UNSIGNED DEFAULT NULL,
    webhook VARCHAR(256),
    enabled BOOLEAN DEFAULT 1 NOT NULL,

    avatar VARCHAR(512) DEFAULT "https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg" NOT NULL,
    username VARCHAR(32) DEFAULT "Reminder" NOT NULL,
    embed MEDIUMINT UNSIGNED,

    method VARCHAR(9),

    PRIMARY KEY (id)
);

CREATE TABLE reminders.guilds (
    guild BIGINT UNSIGNED UNIQUE NOT NULL,

    prefix VARCHAR(5) DEFAULT "$" NOT NULL,
    timezone VARCHAR(32) DEFAULT "UTC" NOT NULL,

    PRIMARY KEY (guild)
);

CREATE TABLE reminders.users (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    user BIGINT UNSIGNED UNIQUE NOT NULL,

    language VARCHAR(2) DEFAULT "EN" NOT NULL,
    timezone VARCHAR(32),
    allowed_dm BOOLEAN DEFAULT 1 NOT NULL,

    dm_channel BIGINT UNSIGNED UNIQUE,
    name VARCHAR(37) UNIQUE,

    PRIMARY KEY (id)
);

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
    FOREIGN KEY (guild_id) REFERENCES guilds(guild) ON DELETE CASCADE
);

CREATE TABLE reminders.command_restrictions (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    
    guild_id BIGINT UNSIGNED NOT NULL,
    role BIGINT UNSIGNED NOT NULL,
    command VARCHAR(16) NOT NULL,

    PRIMARY KEY (id),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild) ON DELETE CASCADE
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