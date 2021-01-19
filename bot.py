from discord.ext import commands
import discord
from config import SETTINGS
import letterboxd
import logging
from film import get_film_embed
import feedparser
import aiosqlite
from datetime import datetime
from time import mktime
import asyncio

logging.basicConfig(filename='log.txt',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO)

GUILDS = {'Korean Fried Chicken': 'kfc', '/daiIy/': 'daily'}
CHANNELS = {'kfc': 729555600119169045,
            'daily': 534812902658539520}
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
            for guild in GUILDS.values():
                channel = self.get_channel(CHANNELS[guild])
                logging.info(f'GUILD, CHANNEL: {guild} {channel}')
                async with aiosqlite.connect('lbx.db') as db:
                    async with db.execute(f'SELECT * FROM {guild}') as cursor:
                        async for row in cursor:
                            rss_url = f'https://letterboxd.com/{row[1]}/rss'
                            entries = feedparser.parse(rss_url)['entries'][:5]
                            for entry in entries:
                                entry_time = datetime.fromtimestamp(mktime(entry['published_parsed']))
                                logging.info(f"{entry['title']} {entry_time} {prev_time}")
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


bot = Bot(command_prefix=prefix)


@bot.event
async def on_ready():
    print(f'Logged in {len(bot.guilds)} servers as {bot.user.name}')


@bot.event
async def on_message(message):
    if message.content.startswith(prefix):
        print("The message's content was", message.content)
        await bot.process_commands(message)

@bot.command(aliases=['f', '/f'])
async def film(ctx, *, film_keywords):
    verbosity = ctx.invoked_with.count('/')
    embed = get_film_embed(lbx, film_keywords, verbosity)
    if not embed:
        await ctx.send(f"No film found matching: '{film_keywords}'")
    else:
        await ctx.send(embed=embed)


@bot.command()
async def follow(ctx, lb_id):
    async with aiosqlite.connect('lbx.db') as db:
        await db.execute(f'''INSERT INTO {GUILDS[ctx.guild.name]}
                                VALUES ('{ctx.author.id}', '{lb_id}', '{ctx.author.name}','{ctx.author.avatar_url}')''')
        await db.commit()
    await ctx.send(f"Added {lb_id}.")


@bot.command()
async def unfollow(ctx, lb_id):
    async with aiosqlite.connect('lbx.db') as db:
        await db.execute(f'''DELETE FROM {GUILDS[ctx.guild.name]}
                                WHERE uid='{ctx.author.id}''')
        await db.commit()
    await ctx.send(f"Removed {lb_id}.")


@bot.command()
@commands.has_guild_permissions(manage_channels=True)
async def setchannel(ctx, channel: discord.TextChannel):
    CHANNELS[GUILDS[ctx.guild.name]] = channel.id
    await ctx.send(f'Now following updates in {channel.mention}')

@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send('Not...for you.')
bot.run(SETTINGS['token'])
