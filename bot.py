import asyncio
from datetime import datetime
import random
import subprocess
from discord.ext import commands
import discord
import letterboxd
import aiosqlite
from imdbpie import Imdb
from imdb import IMDb
from lists import get_list_id
from config import SETTINGS, CONN_URL
from crew import get_crew_embed
from diary import get_diary_embed, get_lid
from film import get_film_embed, who_knows_embed, top_films_embed
import pymongo

GUILDS, CHANNELS = SETTINGS['guilds'], SETTINGS['channels']
prefix = SETTINGS['prefix']
lbx = letterboxd.new(
    api_key=SETTINGS['letterboxd']['api_key'],
    api_secret=SETTINGS['letterboxd']['api_secret']
)

api = letterboxd.api.API(
    api_base='https://api.letterboxd.com/api/v0',
    api_key=SETTINGS['letterboxd']['api_key'],
    api_secret=SETTINGS['letterboxd']['api_secret']
)


imdb = Imdb()
ia = IMDb()
TRACKING_ACTIVITIES = ['DiaryEntryActivity']

class Bot(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.bg_task = self.loop.create_task(self.check_feed())

    async def check_feed(self):
        await self.wait_until_ready()
        while not self.is_closed():
            prev_time = datetime.utcnow()
            await asyncio.sleep(1500)
            for guild, guild_id in GUILDS.items():
                channel = self.get_channel(CHANNELS[guild])
                async with aiosqlite.connect('lbx.db') as db:
                    async with db.execute(f'SELECT * FROM {guild_id}') as cursor:
                        async for row in cursor:
                            print(row)
                            ratings_request = {
                                'perPage': 100,
                                'include': TRACKING_ACTIVITIES,
                                'where': ['OwnActivity', 'NotIncomingActivity']
                            }
                            res = api.api_call(
                                path=f'member/{row[4]}/activity',
                                params=ratings_request)
                            activity = res.json()
                            entries = extend([], activity['items'], 4)
                            dids = []
                            for entry in entries:
                                entry_time = datetime.strptime(entry['whenCreated'], '%Y-%m-%dT%H:%M:%SZ')
                                if entry_time > prev_time:
                                    dids.append(entry['diaryEntry']['id'])
                            if dids:
                                d_embed = await get_diary_embed(api, dids)
                                d_embed.set_author(
                                    name=row[2],
                                    url=f'https://letterboxd.com/{row[1]}',
                                    icon_url=row[3]
                                )
                                await channel.send(embed=d_embed)


class MyHelp(commands.MinimalHelpCommand):
    async def send_command_help(self, command):
        embed = discord.Embed(title=self.get_command_signature(command))
        embed.add_field(name="Help", value=command.help)
        alias = command.aliases
        if alias:
            embed.add_field(name="Aliases", value=prefix + f", {prefix}".join(alias), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

bot = Bot(command_prefix=prefix,
          help_command=MyHelp())


@bot.event
async def on_ready():
    print(f'Logged in {len(bot.guilds)} servers as {bot.user.name}')


@bot.event
async def on_message(message):
    if message.content.startswith(prefix):
        print("The message's content was", message.content)
        await bot.process_commands(message)


@bot.command(help='search a film, more / for more details',
             aliases=['f', '/f'])
async def film(ctx, *, film_keywords):
    verbosity = ctx.invoked_with.count('/')
    embed = get_film_embed(lbx, film_keywords, verbosity)
    if not embed:
        await ctx.send(f"No film found matching: '{film_keywords}'")
    else:
        await ctx.send(embed=embed)


@bot.command(help='follow user diary')
async def follow(ctx, lb_id, member: discord.Member = None):
    db_name = GUILDS[ctx.guild.name]
    conn_url = CONN_URL[db_name]
    client = pymongo.MongoClient(conn_url)
    db = client[db_name]
    users = db.users

    member = member or ctx.author
    try:
        async with aiosqlite.connect('lbx.db') as db:
            lid = await get_lid(lbx, lb_id)
            await db.execute(f'''INSERT INTO {GUILDS[ctx.guild.name]}
                                VALUES ('{member.id}', '{lb_id}', '{member.name}','{member.avatar_url}', '{lid}')''')
            await db.commit()
        user = {
            "uid": member.id,
            "lb_id": lb_id,
            'username': member.name,
            'avatar_url': str(member.avatar_url),
            'lid': lid
        }
        users.update_one({"lb_id": user["lb_id"]}, {"$set": user}, upsert=True)

        await ctx.send(f"Added {lb_id}.")
    except Exception as e:
        print(e)
        await ctx.send('Error, maybe user already exists')


@bot.command(help='unfollow user diary')
async def unfollow(ctx, lb_id):
    async with aiosqlite.connect('lbx.db') as db:
        await db.execute(f'''DELETE FROM {GUILDS[ctx.guild.name]}
                                WHERE lb_id='{lb_id}'
                            ''')
        await db.commit()
    await ctx.send(f"Removed {lb_id}.")


@bot.command(help='set channel where updates appear')
@commands.has_guild_permissions(manage_channels=True)
async def setchannel(ctx, channel: discord.TextChannel):
    CHANNELS[ctx.guild.name] = channel.id
    await ctx.send(f'Now following updates in {channel.mention}')


@bot.command(help='list followed users', aliases=['/follow'])
async def following(ctx):
    follow_str = ''
    async with aiosqlite.connect('lbx.db') as db:
        async with db.execute(f'SELECT lb_id, username FROM {GUILDS[ctx.guild.name]}') as cursor:
            async for row in cursor:
                follow_str += f'[{row[1]}](https://letterboxd.com/{row[0]}), '

    embed = discord.Embed(
        description=f'Following these users in {bot.get_channel(CHANNELS[ctx.guild.name]).mention}\n' + follow_str[:-2]
    )
    await ctx.send(embed=embed)


@bot.command(help='Get a random film from last 100 items watchlisted')
async def wrand(ctx, *, lb_id=''):
    quantity = int(lb_id) if lb_id.isdigit() and int(lb_id) < 101 else 100
    if not lb_id or lb_id.isdigit():
        async with aiosqlite.connect('lbx.db') as db:
            query = f'''SELECT lb_id FROM {GUILDS[ctx.guild.name]}
                WHERE username = '{ctx.author.name}'
            '''
            async with db.execute(query) as cursor:
                lb_id = (await cursor.fetchone())[0]
    member = lbx.member(member_id=lb_id)

    watchlist_request = {
        'perPage': quantity,
        'memberRelationship': 'InWatchlist',
    }
    watchlist = member.watchlist(watchlist_request=watchlist_request)
    if not watchlist['items']:
        await ctx.send('Private or empty watchlist. Or try using /wrand (number of items in your watchlist)')
        return
    random_film = watchlist['items'][random.randrange(0, quantity)]

    await ctx.send(embed=get_film_embed(lbx, film_id=random_film['id']))


@bot.command(help='Get info about a crew member',
             aliases=['c', '/c'])
async def crew(ctx, *, crew_keywords):
    verbosity = ctx.invoked_with.count('/')

    search_request = {
        'perPage': 1,
        'input': crew_keywords,
        'include': 'ContributorSearchItem'
    }

    res = lbx.search(search_request=search_request)
    res = res['items'][0]['contributor']
    if res:
        await ctx.send(embed=get_crew_embed(imdb, ia, res, verbosity))
    else:
        await ctx.send(f"No one matches '{crew_keywords}'")


@bot.command()
async def lrand(ctx, lb_id, *, keywords):
    lid = await get_lid(lbx, lb_id)
    list_id = await get_list_id(api, lid, keywords)
    if not list_id:
        await ctx.send(f"No matching list for '{keywords}'")
        return
    res = api.api_call(f'list/{list_id}/entries', params={'perPage': 100})
    L = res.json()
    size_L = len(L['items'])
    random_film = L['items'][random.randrange(0, size_L)]['film']
    embed=get_film_embed(lbx, film_id=random_film['id'])
    embed.set_author(name=lb_id, url=f'https://boxd.it/{list_id}')
    await ctx.send(embed=embed)

@bot.command(aliases=['ss'])
@commands.cooldown(1,86400,commands.BucketType.user)
async def ssync(ctx):
    db_name = GUILDS[ctx.guild.name]
    conn_url = CONN_URL[db_name]
    client = pymongo.MongoClient(conn_url)
    db = client[db_name]
    users = db.users

    async with aiosqlite.connect('lbx.db') as db:
        async with db.execute(f'SELECT uid, lb_id, username, avatar_url, lid FROM {db_name}') as cursor:
            async for row in cursor:
                user = {
                    "uid": row[0],
                    "lb_id": row[1],
                    'username': row[2],
                    'avatar_url': row[3],
                    'lid': row[4]
                }
                users.update_one({"lb_id": user["lb_id"]}, {"$set": user}, upsert=True)

    subprocess.Popen(['python3', 'update.py', db_name])


@bot.command(aliases=['us'])
@commands.cooldown(1,3600,commands.BucketType.user)
async def usync(ctx, member: discord.Member = None):
    db_name = GUILDS[ctx.guild.name]
    conn_url = CONN_URL[db_name]
    client = pymongo.MongoClient(conn_url)
    db = client[db_name]
    users = db.users
    member = member or ctx.author

    async with aiosqlite.connect('lbx.db') as db:
            await db.execute(f'''UPDATE {GUILDS[ctx.guild.name]}
                                SET avatar_url='{member.avatar_url}'
                                WHERE uid={member.id}
            ''')
            await db.commit()

    user = {
        'username': member.name,
        'avatar_url': str(member.avatar_url),
    }
    users.update_one({'uid': member.id}, {"$set": user}, upsert=True)

    subprocess.Popen(['python3', 'update.py', db_name, str(member.id)])


@bot.command(aliases=['wk', 'seen'])
async def whoknows(ctx, *, film_keywords):
    db_name = GUILDS[ctx.guild.name]
    conn_url = CONN_URL[db_name]
    client = pymongo.MongoClient(conn_url)
    db = client[db_name]
    embed = who_knows_embed(lbx, db, film_keywords)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No film found matching '{film_keywords}'")

@bot.command(aliases=['topf'])
async def top_films(ctx, threshold):
    threshold = int(threshold)
    if threshold < 1:
        await ctx.send('At least 1 rating')
        return
    db_name = GUILDS[ctx.guild.name]
    conn_url = CONN_URL[db_name]
    client = pymongo.MongoClient(conn_url)
    db = client[db_name]

    await ctx.send(embed=top_films_embed(db, threshold))

@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send('Not...for you.')

def extend(entries, items, limit):
    count = 0
    for act in items:
        if count == limit:
            break
        if act['type'] in TRACKING_ACTIVITIES:
            entries.append(act)
            count += 1

    return entries

bot.run(SETTINGS['token'])
