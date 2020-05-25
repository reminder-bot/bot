-- replace external guild IDs with internal guild IDs
alter table command_restrictions add column guild_id1 int unsigned;
alter table command_restrictions add foreign key (guild_id1) references guilds(id) on delete cascade;
update command_restrictions c inner join guilds g on c.guild_id = g.guild set c.guild_id1 = g.id;
alter table command_restrictions rename column guild_id to guild_id_old;
alter table command_restrictions rename column guild_id1 to guild_id;
alter table command_restrictions modify column guild_id int unsigned not null;

-- move role IDs to reference the roles table
insert ignore into roles (role, guild_id) select role, guild_id from command_restrictions;
alter table command_restrictions add column role_id int unsigned;
alter table command_restrictions add foreign key (role_id) references roles(id) on delete cascade;
update command_restrictions c inner join roles r on c.role = r.role set c.role_id = r.id;
alter table command_restrictions modify column role_id int unsigned not null;
alter table command_restrictions add unique (`role_id`, `command`);