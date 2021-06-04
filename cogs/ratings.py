import discord
from discord.ext import commands, menus
import motor.motor_asyncio as motor
from aioshell import run
from config import conn_url, SETTINGS
from utils.film import who_knows_list, top_films_list, get_link
from utils import api

prefix = SETTINGS['prefix']


def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'


class MySource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=20)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        description = '\n'.join(f'{i+1}. {v}'
                                for i, v in enumerate(entries, start=offset))
        return discord.Embed(
            description=description
        )


class SeenSource(menus.ListPageSource):
    def __init__(self, title, details, data):
        super().__init__(data, per_page=20)
        self.title = title
        self.details = details

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        description = '\n'.join(f'{i+1}. {v}'
                                for i, v in enumerate(entries, start=offset))
        embed = discord.Embed(
            title=self.title,
            description=description,
            url=self.details['link']
        )

        avg = self.details['guild_avg']
        r_count = self.details['rating_count']
        w_count = self.details['watch_count']
        footer_text = ''
        if avg != 0.0:
            footer_text += f"{avg:.2f} from {r_count} members"
            if w_count > 0:
                footer_text += ', '
        if w_count > 0:
            footer_text += f"{w_count} watched"
        embed.set_footer(text=footer_text)

        if 'poster_url' in self.details:
            embed.set_thumbnail(url=self.details['poster_url'])

        return embed


class Ratings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(help='Delete all server rating averages')
    async def hard_reset(self, ctx):
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        async with ctx.typing():
            await db.films.delete_many({})
        await ctx.send('Hard reset finished')

    @commands.command(aliases=['ss'], help='Update server ratings. Use restricted to once every two days.')
    @commands.has_guild_permissions(manage_messages=True)
    @commands.cooldown(1, 172800, commands.BucketType.guild)
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

    @ssync.error
    async def ssync_handler(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f'On cooldown, try again in {error.retry_after:.1f}s. Try using usync if just one member')

    @commands.command(aliases=['us'], help='Update user ratings. Mention someone to update their ratings.')
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def usync(self, ctx, member: discord.Member = None):
        db_name = f'g{ctx.guild.id}'
        member = member or ctx.author

        async with ctx.typing():
            await run(f'python3 update.py {db_name} {member.id}')
            await ctx.send(f'Done updating {member.name}')

    @usync.error
    async def usync_handler(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f'On cooldown, try again in {error.retry_after:.1f}s')

    @commands.command(aliases=['wk', 'seen', prefix+'wk'],
                      help='Check *who knows* a film, and their ratings')
    async def whoknows(self, ctx, *, film_keywords):
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]

        if ctx.invoked_with.count(prefix) == 1:
            await usync(ctx, ctx.author)

        title, details, wk_list = await who_knows_list(db, film_keywords)
        if title:
            pages = menus.MenuPages(source=SeenSource(title, details, wk_list), clear_reactions_after=True)
            await pages.start(ctx)
        else:
            await ctx.send(f"No film found matching '{film_keywords}'")

    @commands.command(aliases=['topf'])
    async def top_films(self, ctx, threshold):
        """Get a list of the server's highest rated films.

        Takes the minimum number of ratings as argument.
        NOTE: You need to run ``{prefix}ssync`` if you are using this for the FIRST time.
        """
        threshold = int(threshold)
        if threshold < 1:
            await ctx.send('At least 1 rating')
            return
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        pages = menus.MenuPages(source=MySource
                                (await top_films_list(db, threshold, -1)),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(aliases=['lowf'])
    async def bottom_films(self, ctx, threshold):
        """Get a list of the server's lowest rated films.

        Takes the minimum number of ratings as argument.
        NOTE: You need to run ``{prefix}ssync`` if you are using this for the FIRST time.
        """
        threshold = int(threshold)
        if threshold < 1:
            await ctx.send('At least 1 rating')
            return
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        pages = menus.MenuPages(source=MySource(
            await top_films_list(db, threshold, 1)),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(aliases=['fa', 'fc', 'fd', 'fp', 'fe', 'fw'])
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def filmscrew(self, ctx, *, crew_keywords):
        """Get the server's ratings for a crew by appending

        a (Actor),
        c (Composer),
        d (Director),
        e (Editor),
        p (Producer), or
        w (Writer), to f (films).
        NOTE: filmscrew is just a placeholder for the aliases.
        DO NOT use filmscrew by itself. Use the aliases as follows.
        Can be used once every minute.
    Example: ``{prefix}fd lynch`` to get a list of films directed by David Lynch
        """
        role = ctx.invoked_with[-1].lower()
        search_request = {
            'perPage': 1,
            'input': crew_keywords,
            'include': 'ContributorSearchItem'
        }

        res = await api.api_call('search', params=search_request)
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
            'perPage': 60,
            'type': TYPE_CONTRIB[role]
        }
        res = await api.api_call(f"contributor/{crew['id']}/contributions",
                                 params=contrib_req)
        if 'items' not in res:
            await ctx.send('Connection to Letterboxd failed')
            return

        clist, details = {}, {'cumulative': 0, 'rating_count': 0,
                              'watch_count': 0}
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        role_name = ''
        async with ctx.typing():
            for contrib in res['items']:
                body = ''
                role_name = contrib['type']
                link = get_link(contrib['film'])
                body += f"[{contrib['film']['name']}]({link}) "
                if 'releaseYear' in contrib['film']:
                    body += f"({contrib['film']['releaseYear']}) "
                if db:
                    movie_id = link.split('/')[-2]
                    db_info = await db.films.find_one({'movie_id': movie_id})
                    if db_info:
                        if 'guild_avg' in db_info and db_info['rating_count'] != 0:
                            body += f" **{0.5*db_info['guild_avg']:.2f}** ({db_info['rating_count']})"
                            details['cumulative'] += db_info['guild_avg']*db_info['rating_count']
                            details['rating_count'] += db_info['rating_count']
                            if 'watch_count' in db_info:
                                unrated = db_info['watch_count'] - db_info['rating_count']
                                body += ' ' + '✓'*(unrated if unrated < 6 else 6)
                                details['watch_count'] += db_info['watch_count']
                        elif 'watch_count' in db_info:
                            body += ' ' + '✓'*db_info['watch_count']
                            details['watch_count'] += db_info['watch_count']
                        clist[body] = db_info['guild_avg']
                else:
                    clist[body] = -1

        crew_list = [k for k, v in sorted(
            clist.items(), key=lambda item: item[1], reverse=True)]
        print(crew_list)
        details['link'] = 'https://boxd.it/' + crew['id']
        details['guild_avg'] = details['cumulative']/details['rating_count']
        title=f"{role_name} {crew['name']}"
        pages = menus.MenuPages(source=SeenSource(title, details, crew_list),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @filmscrew.error
    async def filmscrew_handler(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f'On cooldown, try again in {error.retry_after:.1f}s')


    @commands.command()
    async def noah(self, ctx):
        await ctx.send('That is the **worst** opinion I have *EVER*  heard.')

def setup(bot):
    bot.add_cog(Ratings(bot))
