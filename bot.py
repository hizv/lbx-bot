from discord.ext import commands
from config import SETTINGS
import letterboxd
import logging
from film import get_film_embed

logging.basicConfig(level=logging.INFO)

prefix = '/'
bot = commands.Bot(command_prefix=prefix)
lbx = letterboxd.new(
    api_key=SETTINGS['letterboxd']['api_key'],
    api_secret=SETTINGS['letterboxd']['api_secret']
)


@bot.event
async def on_ready():
    print(f'Logged in {len(bot.guilds)} servers as {bot.user.name}')


@bot.event
async def on_message(message):
    if message.content.startswith('/'):
        print("The message's content was", message.content)
        await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    latency = bot.latency
    await ctx.send(latency)


@bot.command(aliases=['f', '/f'])
async def film(ctx, *, film_keywords):
    verbosity = ctx.invoked_with.count('/')
    embed = get_film_embed(lbx, film_keywords, verbosity)
    if not embed:
        await ctx.send(f"No film found matching: '{film_keywords}'")
    await ctx.send(embed=embed)

bot.run(SETTINGS['token'])
