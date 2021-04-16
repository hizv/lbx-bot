import discord
from discord.ext import commands, menus
import pymongo
from utils.diary import get_lid
from config import SETTINGS, CONN_URL, conn_url

GUILDS, CHANNELS = SETTINGS['guilds'], SETTINGS['channels']

def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'


class Follow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(help='Follow your diary. Takes your LB username as input')
    async def follow(self, ctx, lb_id, member: discord.Member = None):
        db_name = f'g{ctx.guild.id}'
        client = pymongo.MongoClient(get_conn_url(db_name))
        db = client[db_name]
        users = db.users

        member = member or ctx.author
        try:
            conn = await self.db.acquire()
            async with conn.transaction():
                lid = await get_lid(self.bot.lbx, lb_id)
                await self.db.execute(f'''INSERT INTO {db_name}.users (uid, lb_id, lid)
                                     VALUES ({member.id}, $1, $2)''', lb_id, lid)
            await self.db.release(conn)

            user = {
                "uid": member.id,
                "lb_id": lb_id,
                'lid': lid
            }
            users.update_one({"lb_id": user["lb_id"]}, {"$set": user}, upsert=True)

            await ctx.send(f"Added {lb_id}.")
        except Exception as e:
            print(e)
            await ctx.send('Error, maybe user already exists')


    @commands.command(help='unfollow user diary')
    async def unfollow(self, ctx, lb_id):
        conn = await self.db.acquire()
        async with conn.transaction():
            await self.db.execute(f'''DELETE FROM g{ctx.guild.id}.users
                                    WHERE lb_id='{lb_id}'
                                ''')
        await self.db.release(conn)
        await ctx.send(f"Removed {lb_id}.")


    @commands.command(aliases=['setchan'], help='set channel where updates appear')
    @commands.has_guild_permissions(manage_channels=True)
    async def setchannel(self, ctx, channel: discord.TextChannel):
        conn = await self.db.acquire()
        async with conn.transaction():
            print(f'UPDATE public.guilds SET channel_id={channel.id} WHERE id={ctx.guild.id}')
            await self.db.execute(f'UPDATE public.guilds SET channel_id={channel.id} WHERE id={ctx.guild.id}')
        await self.db.release(conn)
        await ctx.send(f'Now following updates in {channel.mention}')

    @commands.command(help='list followed users', aliases=['/follow'])
    async def following(self, ctx):
        follow_str = ''
        conn = await self.db.acquire()
        async with conn.transaction():
            async for row in conn.cursor(f'SELECT lb_id, uid FROM g{ctx.guild.id}.users'):
                user = self.bot.get_user(row[1])
                follow_str += f'[{user.display_name}](https://letterboxd.com/{row[0]}), '

        chan_id = await conn.fetchval(f'SELECT channel_id FROM public.guilds WHERE id={ctx.guild.id}')
        await self.db.release(conn)
        embed = discord.Embed(
            description=f'Following these users in {self.bot.get_channel(chan_id).mention}\n' + follow_str[:-2]
        )
        await ctx.send(embed=embed)


    @setchannel.error
    async def setchannel_error(self, ctx, error):
        if isinstance(error, commands.errors.MissingPermissions):
            await ctx.send('Not...for you.')


def setup(bot):
    bot.add_cog(Follow(bot))
