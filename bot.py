from discord.ext import commands
from config import SETTINGS
import discord
import letterboxd
from film import get_link, get_description, get_search_result

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


@bot.command(aliases=["f"])
async def film(ctx, *, film_keywords):
    film = get_search_result(lbx, film_keywords)
    film_instance = lbx.film(film['id'])
    film_stats = film_instance.statistics()

# print(json.dumps(film, sort_keys=True, indent=4))
# print(json.dumps(film_stats, sort_keys=True, indent=4))

    embed = discord.Embed(
        title=f"{film['name']} ({film['releaseYear']})",
        url=get_link(film),
        description=get_description(film, film_stats)
    )

    if 'poster' in film:
        embed.set_thumbnail(url=film['poster']['sizes'][-1]['url'])
    await ctx.send(embed=embed)

bot.run(SETTINGS['token'])
