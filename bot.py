import asyncio
from datetime import datetime
import secrets
from discord.ext import commands, tasks
import asyncpg
import discord
import letterboxd
import utils.api as api
from config import SETTINGS, POSTGRES_INFO
from utils.diary import get_diary_embed, get_lid

intents = discord.Intents.default()
intents.members = True

prefix = SETTINGS['prefix']

initial_extensions = ['cogs.film',
                      'cogs.ratings',
                      'cogs.follow']

async def run():
    db = await asyncpg.create_pool(**POSTGRES_INFO)

    bot = Bot(command_prefix=prefix,
              help_command=MyHelp(),
              intents=intents,
              db=db)

    for extension in initial_extensions:
        bot.load_extension(extension)

    await bot.start(SETTINGS['token'])

def extend(entries, items, limit, lid):
    count = 0
    for act in items:
        if count == limit:
            break
        if act['type'] == 'DiaryEntryActivity' and act['member']['id'] == lid:
            entries.append(act)
            count += 1

    return entries

class Bot(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.db = kwargs.pop('db')
        self.lbx = letterboxd.new(
            api_key=SETTINGS['letterboxd']['api_key'],
            api_secret=SETTINGS['letterboxd']['api_secret']
        )
        self.prev_time = datetime.utcnow()
        self.check_feed.start()

    async def on_ready(self):
        print(f'Logged in {len(self.guilds)} servers as {self.user.name}')

    async def on_message(self, message):
        if message.content.startswith(prefix):
            print("The message's content was", message.content)
            await self.process_commands(message)

    async def on_guild_join(self, guild):
        connection = await self.db.acquire()
        async with connection.transaction():
            schema = f'g{guild.id}'
            init_schema = f'''
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE {schema}.films (
            movie_id text COLLATE pg_catalog."default" NOT NULL,
            guild_avg real,
            rating_count smallint,
            CONSTRAINT films_pkey PRIMARY KEY (movie_id)) TABLESPACE pg_default;
ALTER TABLE {schema}.films OWNER to postgres;
CREATE TABLE {schema}.ratings (
    u_lid text COLLATE pg_catalog."default" NOT NULL,
    movie_id text COLLATE pg_catalog."default" NOT NULL,
    rating_id smallint NOT NULL
) TABLESPACE pg_default;
ALTER TABLE {schema}.ratings
    OWNER to postgres;
CREATE TABLE {schema}.users (
    lb_id text COLLATE pg_catalog."default" NOT NULL,
    lid text COLLATE pg_catalog."default",
    uid bigint NOT NULL,
    CONSTRAINT users_pkey PRIMARY KEY (uid)
) TABLESPACE pg_default;
ALTER TABLE {schema}.users
    OWNER to postgres;
'''
            await self.db.execute(init_schema)
            await self.db.execute('INSERT INTO public.guilds (id) VALUES ($1)', guild.id)
        await self.db.release(connection)

    async def on_guild_remove(self, guild):
        conn = await self.db.acquire()
        async with conn.transaction():
            await self.db.execute('DELETE FROM public.guilds WHERE id=$1', guild.id)
        await self.db.release(conn)
    @tasks.loop(minutes=20)
    async def check_feed(self):
        conn = await self.db.acquire()
        async with conn.transaction():
            async for guild in conn.cursor('SELECT id, channel_id FROM public.guilds'):
                channel = self.get_channel(guild[1])
                if not channel:
                    continue
                async for row in conn.cursor(f'SELECT uid, lb_id, lid FROM g{guild[0]}.users'):
                    print(row)
                    user = self.get_user(row[0])
                    if not user:
                        print(row[1])
                        continue

                    ratings_request = {
                        'perPage': 100,
                        'include': 'DiaryEntryActivity',
                        'where': 'OwnActivity',
                    }
                    activity = await api.api_call(
                        path=f'member/{row[2]}/activity',
                        params=ratings_request)
                    if 'items' not in activity:
                        continue

                    entries = extend([], activity['items'], 4, row[2])
                    dids = []
                    for entry in entries:
                        entry_time = datetime.strptime(entry['whenCreated'], '%Y-%m-%dT%H:%M:%SZ')
                        if entry_time > self.prev_time:
                            dids.append(entry['diaryEntry']['id'])
                    if dids:
                        d_embed = await get_diary_embed(dids)
                        d_embed.set_author(
                            name=user.display_name,
                            url=f'https://letterboxd.com/{row[1]}',
                            icon_url=user.avatar_url
                        )
                        await channel.send(embed=d_embed)
        self.prev_time = datetime.utcnow()
        await self.db.release(conn) 

    @check_feed.before_loop
    async def before_feed(self):
        await self.wait_until_ready()

class MyHelp(commands.MinimalHelpCommand):
    async def send_command_help(self, command):
        embed = discord.Embed(title=self.get_command_signature(command))
        embed.add_field(name="Help", value=command.help)
        alias = command.aliases
        if alias:
            embed.add_field(name="Aliases", value=prefix + f", {prefix}".join(alias), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)


loop = asyncio.get_event_loop()
loop.run_until_complete(run())
