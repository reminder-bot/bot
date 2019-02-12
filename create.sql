CREATE TABLE reminders.reminders (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    hashpack VARCHAR(64) UNIQUE NOT NULL,
    message VARCHAR(2000) NOT NULL,
    channel BIGINT UNSIGNED NOT NULL,
    `time` BIGINT UNSIGNED DEFAULT 0 NOT NULL,
    position TINYINT UNSIGNED DEFAULT NULL,

    webhook VARCHAR(256),
    avatar VARCHAR(512) DEFAULT "https://raw.githubusercontent.com/reminder-bot/logos/master/Remind_Me_Bot_Logo_PPic.jpg" NOT NULL,
    username VARCHAR(32) DEFAULT "Reminder" NOT NULL,
    embed MEDIUMINT UNSIGNED,

    method TEXT,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.intervals (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,

    reminder INT UNSIGNED NOT NULL,
    period INT UNSIGNED NOT NULL,
    position TINYINT UNSIGNED NOT NULL DEFAULT 0,

    CONSTRAINT reminder_period_cx
    FOREIGN KEY reminder_period_fk (reminder)
    REFERENCES reminders (id)
    ON DELETE CASCADE,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.servers (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    server BIGINT UNSIGNED UNIQUE NOT NULL,

    prefix VARCHAR(5) DEFAULT "$" NOT NULL,
    language VARCHAR(2) DEFAULT "EN" NOT NULL,
    timezone VARCHAR(30) DEFAULT "UTC" NOT NULL,

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
    server BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id)
);

CREATE TABLE reminders.roles (
    id INT UNSIGNED AUTO_INCREMENT UNIQUE NOT NULL,
    role BIGINT UNSIGNED UNIQUE NOT NULL,
    server BIGINT UNSIGNED NOT NULL,

    PRIMARY KEY (id)
);
-- MUST RUN to_database.py TO FORM STRING STORES