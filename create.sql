CREATE TABLE reminders.reminders (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE,
    message VARCHAR(2000) NOT NULL,
    channel BIGINT UNSIGNED NOT NULL,
    `time` BIGINT UNSIGNED DEFAULT 0 NOT NULL,
    `interval` INT UNSIGNED,

    webhook VARCHAR(256),
    avatar VARCHAR(512) DEFAULT "https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg" NOT NULL,
    username VARCHAR(32) DEFAULT "Reminder" NOT NULL,
    embed MEDIUMINT UNSIGNED,

    method TEXT,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.servers (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE,
    server BIGINT UNSIGNED UNIQUE,

    prefix VARCHAR(5) DEFAULT "$" NOT NULL,
    language VARCHAR(2) DEFAULT "EN" NOT NULL,
    timezone VARCHAR(30) DEFAULT "UTC" NOT NULL,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.todos (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE,
    owner BIGINT UNSIGNED,
    value TEXT,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.blacklists (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE,
    channel BIGINT UNSIGNED UNIQUE NOT NULL,
    server BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.roles (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE,
    role BIGINT UNSIGNED UNIQUE NOT NULL,
    server BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id)
);
-- MUST RUN to_database.py TO FORM STRING STORES