import aiohttp
import random
import discord
from discord.ext import commands
from fuzzywuzzy import process
from imdbpie import Imdb
from imdb import IMDb
import motor.motor_asyncio as motor
from parsel import Selector
import wikipedia
from utils import api, diary, film
from config import conn_url, SETTINGS

prefix = SETTINGS['prefix']

def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'

async def get_list_id(lid, keywords):
    params = {
        'member': lid,
        'memberRelationship': 'Owner',
        'perPage': 50,
        'where': 'Published',
        'sort': 'ListPopularity'
    }

    res = await api.api_call('lists', params)
    L_list = { s['name']:s['id'] for s in res['items']}
    match = process.extractOne(keywords, L_list.keys())
    if match[1] > 70:
        return L_list[match[0]]


def get_crew_embed(imdb, ia, res, verbosity=0):
    description = ''
    imdb_id = imdb.search_for_name(res['name'])[0]['imdb_id']
    imdb_bio = ia.get_person(imdb_id[2:], info=['biography'])
    print(imdb_bio.keys())
    if 'mini biography' in imdb_bio:
        description += "```"
        bio = imdb_bio['mini biography'][0]
        bio = bio.split('::', 1)[0]
        description += bio[:250] + '...' if verbosity == 0 else bio
        description += '```'

    if 'birth date' in imdb_bio:
        description += '\n**Born:** ' + imdb_bio['birth date']
        if imdb_bio['birth notes']:
            description += ' ' + imdb_bio['birth notes']
    if 'death date' in imdb_bio:
        description += '\n**Died:** ' + imdb_bio['death date']
        if imdb_bio['death notes']:
            description += ' ' + imdb_bio['death notes']
        # if imdb_bio['death cause']:
        #    description += ' ' + imdb_bio['death cause']
    embed = discord.Embed(
        title=res['name'],
        url=get_link(res),
        description=description
    )
    try:
        embed.set_thumbnail(url=wikipedia.page(res['name']).images[0])
    except Exception as e:
        print(e)

    return embed


def get_link(res):
    for link in res['links']:
        if link['type'] == 'letterboxd':
            return link['url']
    return None



class Film(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.imdb = Imdb()
        self.ia = IMDb()

    @commands.command(help=f'search a film\n{prefix}{prefix}f to also get the synopsis',
                aliases=['f', prefix + 'f'])
    async def film(self, ctx, *, film_keywords):
        verbosity = ctx.invoked_with.count(prefix)
        db = None
        conn = await self.db.acquire()
        async with conn.transaction():
            async for guild in conn.cursor('SELECT id FROM public.guilds'):
                if ctx.guild.id == guild[0]:
                    db_name = f'g{ctx.guild.id}'
                    client = motor.AsyncIOMotorClient(get_conn_url(db_name))
                    db = client[db_name]
        await self.db.release(conn)
        embed = await film.get_film_embed(film_keywords, verbosity, db=db)
        if not embed:
            await ctx.send(f"No film found matching: '{film_keywords}'")
        else:
            await ctx.send(embed=embed)


    @commands.command(help=f'Get info about a crew member\nUse {prefix}c to get a longer bio',
                aliases=['c', prefix + 'c'])
    async def crew(self, ctx, *, crew_keywords):
        verbosity = ctx.invoked_with.count(prefix)

        search_request = {
            'perPage': 1,
            'input': crew_keywords,
            'include': 'ContributorSearchItem'
        }

        res = await api.api_call('search', params=search_request)
        res = res['items'][0]['contributor']
        if res:
            await ctx.send(embed=get_crew_embed(self.imdb, self.ia, res, verbosity))
        else:
            await ctx.send(f"No one matches '{crew_keywords}'")

    @commands.command(help='Sync your watchlist items')
    async def wsync(self, ctx, wsize=''):
        conn = await self.db.acquire()
        query = f'''SELECT lid FROM g{ctx.guild.id}.users
                    WHERE uid = {ctx.author.id}
                '''
        lid = await conn.fetchval(query)
        query = f'''SELECT lb_id FROM g{ctx.guild.id}.users
                    WHERE uid = {ctx.author.id}
                '''
        lb_id = await conn.fetchval(query)
        await self.db.release(conn)

        if not lid:
            await ctx.send(f'Error, try setting your LB ID using {prefix}follow')
            return

        watchlist_request = {
            'perPage': 100,
            'memberRelationship': 'InWatchlist',
        }

        async with ctx.typing():
            async with aiohttp.ClientSession() as cs:
                async with cs.get(f'https://letterboxd.com/{lb_id}/watchlist') as r:
                    if r.status >= 400 and not wsize:
                        await ctx.send(f'Please manually add your watchlist size using {prefix}wsync (size)')
                        return
                    else:
                        selector = Selector(text=await r.text())
                        wsize = int(selector.css('span.watchlist-count')[0].get().split('>')[1].split('\xa0')[0].replace(',', ''))
            watchlist = await api.api_call(f'member/{lid}/watchlist', params=watchlist_request)
            film_ids = [film['id'] for film in watchlist['items']]
            if not watchlist['items']:
                await ctx.send(f'Private or empty watchlist. Or try using {prefix}wrand (number of items in your watchlist)')
                return

            added = len(watchlist['items'])
            while added < wsize:
                added += 100
                watchlist_request['cursor'] = watchlist['next']
                watchlist = await api.api_call(f'member/{lid}/watchlist', params=watchlist_request)
                film_ids += [film['id'] for film in watchlist['items']]

            db_name = f'g{ctx.guild.id}'
            client = motor.AsyncIOMotorClient(get_conn_url(db_name))
            db = client[db_name]
            w_details = { 'wlist': film_ids, 'wsize': wsize}
            await db.users.update_one({
                'lid': lid
            }, {
                '$set': w_details
            })

        await ctx.send(f'Done updating watchlist for {lb_id}')

    @commands.command(help='Get a random film from watchlist')
    async def wrand(self, ctx, start=0, end=0):
        db_name = f'g{ctx.guild.id}'
        client = motor.AsyncIOMotorClient(get_conn_url(db_name))
        db = client[db_name]
        user = await db.users.find_one({'uid': ctx.author.id})
        if not user:
            ctx.send('User not followed')

        if 'wlist' in user:
            wsize = user['wsize']
            if start >= wsize:
                start = wsize-1
            if end == 0 or end > wsize:
                end = wsize
            random_film_id = user['wlist'][random.randrange(start, end)]
            await ctx.send(embed=await film.get_film_embed(film_id=random_film_id))
        else:
            await ctx.send(f'Please run {prefix}wsync')


    @commands.command(help='Example: ``{prefix}lrand frymanjayce tspdt`` for https://letterboxd.com/frymanjayce/list/tspdt-starting-list/')
    async def lrand(self, ctx, lb_id, *, keywords):
        lid = await diary.get_lid(lb_id)
        list_id = await get_list_id(lid, keywords)
        if not list_id:
            await ctx.send(f"No matching list for '{keywords}'")
            return
        L = await api.api_call(f'list/{list_id}/entries', params={'perPage': 100})
        print(L['items'])
        size_L = len(L['items'])
        random_film = L['items'][random.randrange(0, size_L)]['film']
        embed = await film.get_film_embed(film_id=random_film['id'])
        embed.set_author(name=lb_id, url=f'https://boxd.it/{list_id}')
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Film(bot))
