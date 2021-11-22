import typing
import discord
from discord.ext import commands, menus
import motor.motor_asyncio as motor
from utils.diary import get_lid
from config import SETTINGS, conn_url

prefix = SETTINGS['prefix']


class MySource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=20)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        description = '\n'.join(f'{i+1}. {v}'
                                for i, v in enumerate(entries, start=offset))
        return discord.Embed(
            title=f'Will sync the following users on {prefix}ssync:',
            description=description
        )


def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'


class Follow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command()
    async def follow(self, ctx, lb_id, member: discord.Member = None):
        """Follow your diary.

        Takes your LB username as input.
        Examples:
        1. To add yourself if your Letterboxd username is 'mp4': ``{prefix}follow mp4``
        2.To add someone besides you, you need to ping them too: ``{prefix}follow mp4 @chieko``
        """
        db_name = f'g{ctx.guild.id}'
        member = member or ctx.author
        try:
            conn = await self.db.acquire()
            async with conn.transaction():
                lid = await get_lid(lb_id)
                await self.db.execute(f'''INSERT INTO {db_name}.users (uid, lb_id, lid)
                                     VALUES ({member.id}, $1, $2)''',
                                      lb_id, lid)
            user = {
                "uid": member.id,
                "lb_id": lb_id,
                'lid': lid
            }
            client = motor.AsyncIOMotorClient(get_conn_url(db_name))
            db = client[db_name]
            users = db.users

            await users.update_one({"lb_id": user["lb_id"]},
                                   {"$set": user}, upsert=True)

            await ctx.send(f"Added {lb_id}.")
            await self.bot.get_cog('Ratings').usync(ctx, member)
        except Exception as e:
            print(e)
            await ctx.send(f'Error, if following somebody besides you, try ``{prefix}follow {lb_id} @them``')
        finally:
            await self.db.release(conn)


    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def unfollow(self, ctx, arg: typing.Union[discord.Member, str]):
        '''Unfollow user.

        '''
        db_name = f'g{ctx.guild.id}'
        lb_id = arg

        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]

        conn = await self.db.acquire()
        async with conn.transaction():
            if isinstance(arg, discord.Member):
                query = f'''SELECT lb_id FROM {db_name}.users
                WHERE uid={arg.id}
                '''
                lb_id = await conn.fetchval(query)
            await self.db.execute(f'''DELETE FROM {db_name}.users
                                    WHERE lb_id='{lb_id}'
                                ''')
        await self.db.release(conn)

        async with ctx.typing():
            await db.users.delete_many({'lb_id': lb_id})
            user_ratings = db.ratings.find({'lb_id': lb_id})
            async for rating in user_ratings:
                await db.films.delete_one({'movie_id': rating['movie_id']})

            await db.ratings.delete_many({'lb_id': lb_id})
        await ctx.send(f"Removed {lb_id}.")


    @commands.command(aliases=['setchan'], help='Set the channel where updates appear.', enabled=False)
    @commands.has_guild_permissions(manage_channels=True)
    async def setchannel(self, ctx, channel: discord.TextChannel):
        conn = await self.db.acquire()
        async with conn.transaction():
            print(f'UPDATE public.guilds SET channel_id={channel.id} WHERE id={ctx.guild.id}')
            await self.db.execute(f'UPDATE public.guilds SET channel_id={channel.id} WHERE id={ctx.guild.id}')
        await self.db.release(conn)
        await ctx.send(f'Now following updates in {channel.mention}')

    @commands.command(help='List followed users', aliases=[f'{prefix}follow'])
    async def following(self, ctx):
        follow_list = []

        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        async for user in db.users.find({}):
            discord_user = self.bot.get_user(int(user['uid']))
            lb_id = user['lb_id']
            display_name = lb_id if not discord_user else discord_user.display_name
            follow_list.append(f'{display_name}: [{lb_id}](https://letterboxd.com/{lb_id})')


        pages = menus.MenuPages(source=MySource(follow_list),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @setchannel.error
    async def setchannel_error(self, ctx, error):
        if isinstance(error, commands.errors.MissingPermissions):
            await ctx.send('Not...for you.')


def setup(bot):
    bot.add_cog(Follow(bot))
