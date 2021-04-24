import discord
from discord.ext import commands, menus
import motor.motor_asyncio as motor
from aioshell import run
from config import conn_url, SETTINGS
from utils.film import who_knows_embed, top_films_list, get_link
from utils import api

prefix = SETTINGS['prefix']

def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'

class MySource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=20)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        description = '\n'.join(f'{i+1}. {v}' for i, v in enumerate(entries, start=offset))
        return discord.Embed(
            description=description
        )

class Ratings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.lbx = bot.lbx

    @commands.command(aliases=['ss'], help='Update server ratings. Use restricted to once every four days.')
    @commands.cooldown(1, 345600, commands.BucketType.guild)
    async def ssync(self, ctx):
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        users = db.users

        conn = await self.db.acquire()
        async with conn.transaction():
            async for row in conn.cursor(f'SELECT uid, lb_id, lid FROM {db_name}.users'):
                user = {
                    "uid": row[0],
                    "lb_id": row[1],
                    'lid': row[2]
                }
                await users.update_one({"lb_id": user["lb_id"]}, {"$set": user}, upsert=True)
        await self.db.release(conn)

        async with ctx.typing():
            r = await run(f'python3 update.py {db_name}')
            await ctx.send(f'Done updating {ctx.guild.name}')

    @commands.command(aliases=['us'], help='Update user ratings. Mention someone to update their ratings.')
    @commands.cooldown(1,3600,commands.BucketType.user)
    async def usync(self, ctx, member: discord.Member = None):
        db_name = f'g{ctx.guild.id}'
        member = member or ctx.author

        async with ctx.typing():
            await run(f'python3 update.py {db_name} {member.id}')
            await ctx.send(f'Done updating {member.name}')


    @commands.command(aliases=['wk', 'seen', prefix+'wk'],
                      help='Check *who knows* a film, and their ratings')
    async def whoknows(self, ctx, *, film_keywords):
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]

        if ctx.invoked_with.count(prefix) == 1:
            await usync(ctx, ctx.author)

        embed = await who_knows_embed(self.bot.lbx, db, film_keywords)
        if embed:
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"No film found matching '{film_keywords}'")

    @commands.command(aliases=['topf'],
                      help='''Get a list of the server's highest rated films. Takes the minimum number of ratings as argument.
                      NOTE: You need to run ``{prefix}ssync`` if you are using this for the FIRST time.''')
    async def top_films(self, ctx, threshold):
        threshold = int(threshold)
        if threshold < 1:
            await ctx.send('At least 1 rating')
            return
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        pages = menus.MenuPages(source=MySource(await top_films_list(db, threshold)), clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(aliases=['fa', 'fc', 'fd', 'fp', 'fe', 'fw'],
                      help=f'''NOTE: filmscrew is just a placeholder for the aliases. DO NOT USE filmscrew by itself. Use the aliases as follows.
                      Get the server's ratings for a crew by appending
                      a (Actor),
                      c (Composer),
                      d (Director),
                      e (Editor),
                      p (Producer), or
                      w (Writer), to f (films).
                      Can be used once every minute.
                      Example: ``{prefix}fd lynch`` to get a list of films directed by David Lynch''')
    @commands.cooldown(1,20,commands.BucketType.user)
    async def filmscrew(self, ctx, *, crew_keywords):
        role = ctx.invoked_with[-1].lower()
        search_request = {
            'perPage': 1,
            'input': crew_keywords,
            'include': 'ContributorSearchItem'
        }

        res = self.lbx.search(search_request=search_request)
        crew = res['items'][0]['contributor']
        if not crew:
            await ctx.send(f'Nobody found matching {crew_keywords}')
            return

        TYPE_CONTRIB = {
            'a': 'Actor',
            'c': 'Composer',
            'd': 'Director',
            'e': 'Editor',
            'p': 'Producer',
            'w': 'Writer',
        }

        contrib_req = {
            'perPage': 20,
            'type': TYPE_CONTRIB[role]
        }
        res = await api.api_call(f"contributor/{crew['id']}/contributions", params=contrib_req)
        if 'items' not in res:
            await ctx.send('Connection to Letterboxd failed')
            return

        body = ''
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        role_name = ''
        async with ctx.typing():
            for contrib in res['items']:
                role_name = contrib['type']
                link = get_link(contrib['film'])
                details = {'name': contrib['film']['name']}
                body += f"[{contrib['film']['name']}]({link}) "
                if 'releaseYear' in contrib['film']:
                    body += f"({contrib['film']['releaseYear']}) "
                if db:
                    movie_id = link.split('/')[-2]
                    db_info = await db.films.find_one({'movie_id': movie_id})
                    if db_info:
                        if 'guild_avg' in db_info and db_info['rating_count'] != 0:
                            body += f" **{0.5*db_info['guild_avg']:.2f}** ({db_info['rating_count']})"
                            if 'watch_count' in db_info:
                                unrated = db_info['watch_count'] - db_info['rating_count']
                                body += ' ' + '✓'*unrated
                        elif 'watch_count' in db_info:
                            body += ' ' + '✓'*db_info['watch_count']
                body += '\n'

        embed = discord.Embed(
            title=f"{role_name} {crew['name']}",
            description=body
        )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Ratings(bot))
