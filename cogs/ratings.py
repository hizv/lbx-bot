import discord
from discord.ext import commands, menus
import pymongo
from aioshell import run
from config import conn_url
from utils.film import who_knows_embed, top_films_list


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

    @commands.command(aliases=['ss'], help='Sync server ratings. Use restricted to once every four days.')
    @commands.cooldown(1,345600,commands.BucketType.user)
    async def ssync(self, ctx):
        db_name = f'g{ctx.guild.id}'
        client = pymongo.MongoClient(get_conn_url(db_name))
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
                users.update_one({"lb_id": user["lb_id"]}, {"$set": user}, upsert=True)
        await self.db.release(conn)

        async with ctx.typing():
            r = await run(f'python3 update.py {db_name}')
            await ctx.send(f'Done updating {ctx.guild.name}')

    @commands.command(aliases=['us'], help='Sync user ratings. Can take other user as argument.')
    @commands.cooldown(1,3600,commands.BucketType.user)
    async def usync(self, ctx, member: discord.Member = None):
        db_name = f'g{ctx.guild.id}'
        member = member or ctx.author

        async with ctx.typing():
            await run(f'python3 update.py {db_name} {member.id}')
            await ctx.send(f'Done updating {member.name}')


    @commands.command(aliases=['wk', 'seen', '/wk'])
    async def whoknows(self, ctx, *, film_keywords):
        db_name = f'g{ctx.guild.id}'
        client = pymongo.MongoClient(get_conn_url(db_name))
        db = client[db_name]

        if ctx.invoked_with.count('/') == 1:
            await usync(ctx, ctx.author)

        embed = who_knows_embed(self.bot.lbx, db, film_keywords)
        if embed:
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"No film found matching '{film_keywords}'")

    @commands.command(aliases=['topf'])
    async def top_films(self, ctx, threshold):
        threshold = int(threshold)
        if threshold < 1:
            await ctx.send('At least 1 rating')
            return
        db_name = f'g{ctx.guild.id}'
        client = pymongo.MongoClient(get_conn_url(db_name))
        db = client[db_name]
        pages = menus.MenuPages(source=MySource(top_films_list(db, threshold)), clear_reactions_after=True)
        await pages.start(ctx)


def setup(bot):
    bot.add_cog(Ratings(bot))
