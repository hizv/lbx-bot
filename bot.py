from discord.ext import commands
import discord
from config import SETTINGS
import letterboxd
from film import get_film_embed
import feedparser
import aiosqlite
from datetime import datetime
from time import mktime
import asyncio


GUILDS = {'Korean Fried Chicken': 'kfc', '/daiIy/': 'daily'}
CHANNELS = {'Korean Fried Chicken': 729555600119169045,
            '/daiIy/': 534812902658539520}
prefix = '/'
lbx = letterboxd.new(
    api_key=SETTINGS['letterboxd']['api_key'],
    api_secret=SETTINGS['letterboxd']['api_secret']
)


class Bot(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bg_task = self.loop.create_task(self.check_feed())

    async def check_feed(self):
        prev_time = datetime.utcnow()
        await self.wait_until_ready()
        while not self.is_closed():
            for guild, guild_id in GUILDS.items():
                channel = self.get_channel(CHANNELS[guild])
                async with aiosqlite.connect('lbx.db') as db:
                    async with db.execute(f'SELECT * FROM {guild_id}') as cursor:
                        async for row in cursor:
                            rss_url = f'https://letterboxd.com/{row[1]}/rss'
                            entries = feedparser.parse(rss_url)['entries'][:5]
                            for entry in entries:
                                entry_time = datetime.fromtimestamp(mktime(entry['published_parsed']))
                                if entry_time > prev_time:
                                    embed = discord.Embed(
                                        title=entry['title'],
                                        url=entry['link'],
                                        description='```' + entry['summary'].split('<p>')[-1].split('</p>')[0] + '```'
                                    )
                                    embed.set_thumbnail(url=entry['summary'].split('''"''')[1])
                                    embed.set_author(
                                        name=row[2],
                                        url=f'https://letterboxd.com/{row[1]}',
                                        icon_url=row[3]
                                        )
                                    await channel.send(embed=embed)
            prev_time = datetime.utcnow()
            await asyncio.sleep(150)


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
    member = member or ctx.author
    try:
        async with aiosqlite.connect('lbx.db') as db:
            await db.execute(f'''INSERT INTO {GUILDS[ctx.guild.name]}
                                VALUES ('{member.id}', '{lb_id}', '{member.name}','{member.avatar_url}')''')
            await db.commit()
        await ctx.send(f"Added {lb_id}.")
    except Exception:
        await ctx.send(f'User already exists')


@bot.command(help='unfollow user diary')
async def unfollow(ctx, lb_id):
    async with aiosqlite.connect('lbx.db') as db:
        await db.execute(f'''DELETE FROM {GUILDS[ctx.guild.name]}
                                WHERE lb_id='{lb_id}''')
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
async def wrand(ctx, *, lb_id):
    quantity = int(lb_id) if lb_id.isdigit() and int(lb_id) < 101 else 100
    if not len(lb_id) or lb_id.isdigit():
        query = f'''SELECT lb_id FROM {GUILDS[ctx.guild.name]}
                WHERE username = '{ctx.author.name}'
            '''
        async with aiosqlite.connect('lbx.db') as db:
            async with db.execute(query) as cursor:
                lb_id = (await cursor.fetchone())[0]
    m_result = lbx.search(search_request={
        'include': 'MemberSearchItem', 'input': lb_id, 'perPage': 1})
    if not m_result:
        await ctx.send('User not found.')
        return
    member = lbx.member(member_id=m_result['items'][0]['member']['id'])

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

@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send('Not...for you.')

bot.run(SETTINGS['token'])
