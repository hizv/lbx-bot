from discord import Embed
from utils.api import api_call

async def get_film_embed(film_keywords='', verbosity=0, film_id='', db=None):
    if film_keywords:
        film = await get_search_result(film_keywords)
        if not film:
            return None
        film_id = film['id']
    film_details = await api_call(f'film/{film_id}')
    film_stats = await api_call(f'film/{film_id}/statistics')

    title = f"{film_details['name']}"
    if 'releaseYear' in film_details:
        title += ' (' + str(film_details['releaseYear']) + ')'

    description = await get_description(film_details, film_stats, verbosity, db)
    embed = Embed(
        title=title,
        url=get_link(film_details),
        description=description
    )

    if 'poster' in film_details:
        embed.set_thumbnail(url=film_details['poster']['sizes'][-1]['url'])
    if 'runTime' in film_details:
        runtime = film_details['runTime']
        hours = runtime // 60
        minutes = runtime % 60
        if hours > 0:
            embed.set_footer(text=f'\n{hours} hour {minutes} min')
        else:
            embed.set_footer(text=f'{runtime} min')
    return embed


def get_link(film_details):
    for link in film_details['links']:
        if link['type'] == 'letterboxd':
            return link['url']
    return None


async def get_description(film_details, film_stats, verbosity=0, db=None):
    description = ''
    if 'originalName' in film_details:
        description += f"_{film_details['originalName']}_\n"

    if film_details['contributions']:
        director_str = '**'
        for contribution in film_details['contributions']:
            if contribution['type'] == 'Director':
                for director in contribution['contributors']:
                    director_str += director['name'] + ', '
        description += director_str[:-2] + '** '

    country_str = ''
    if 'countries' in film_details:
        for count_ry, country in enumerate(film_details['countries']):
            if count_ry == 3:
                break
            if verbosity == 0 and count_ry == 2:
                break
            country_str += country['name'] + ', '

        description += country_str[:-2]

    if 'rating' in film_stats:
        description += f"\n**{film_stats['rating']:.2f}** from "
        description += f"{human_count(film_stats['counts']['ratings'])} ratings, "
    else:
        description += '\n'
    description += f"{human_count(film_stats['counts']['watches'])} watched\n"

    if db:
        movie_id = get_link(film_details).split('/')[-2]
        db_info = await db.films.find_one({'movie_id': movie_id})
        if db_info and 'guild_avg' in db_info:
            description += f"Server: **{0.5*db_info['guild_avg']:.2f}** from {db_info['rating_count']}\n"

    if film_details['genres']:
        genre_str = '*'
        for genre in film_details['genres']:
            genre_str += genre['name'] + ', '
        description += genre_str[:-2] + '*'
    if verbosity > 0:
        description += '\n```' + film_details['description'] + '```\n'

    return description


async def get_search_result(film_keywords):
    search_request = {
        'perPage': 1,
        'input': film_keywords,
        'include': 'FilmSearchItem'
    }

    search_response = await api_call('search', params=search_request)

    if not search_response['items']:
        return None
    return search_response['items'][0]['film']


async def who_knows_list(db, film_keywords):
    ratings = db.ratings
    films = db.films
    users = db.users

    film_res = await get_search_result(film_keywords)
    if not film_res:
        return None

    link = get_link(film_res)
    movie_id = link.split('/')[-2]

    details = {'name': film_res['name'], 'link': link}
    db_info = await films.find_one({'movie_id': movie_id})

    total, r_count, ur_count = 0, 0, 0
    wk_list = []
    async for rating in ratings.find({'movie_id': movie_id}):
        lb_id = rating['lb_id']
        rating_id = rating['rating_id']
        if rating_id == -1:
            rating_id = '✓'
            ur_count += 1
        else:
            total += rating_id
            r_count += 1
        wk_list.append(f"[{lb_id}](https://letterboxd.com/{lb_id}) **{rating_id}**")

    title = f"Who knows {film_res['name']}"
    if 'releaseYear' in film_res:
        title += ' (' + str(film_res['releaseYear']) + ')'
        details['releaseYear'] = film_res['releaseYear']

    if 'poster' in film_res:
        url = film_res['poster']['sizes'][-1]['url']
        details['poster_url'] = url

    avg = total/r_count if r_count > 0 else 0
    details['movie_id'] = movie_id
    details['guild_avg'] = avg
    details['rating_count'] = r_count
    details['watch_count'] = r_count + ur_count
    await films.update_one({'movie_id': movie_id}, {"$set": details}, upsert=True)

    return title, details, wk_list

async def top_films_list(db, threshold):
    top_films = db.films.find(
        { 'rating_count': {'$gt': threshold-1}
    }).sort('guild_avg', -1)

    topf_short = []
    counter = 0
    async for film in top_films:
        if counter == 200:
            break
        movie_id = film['movie_id']
        movie_name = film['name'] if 'name' in film else ' '.join([r.capitalize() for r in movie_id.split('-') if not r.isdigit()])
        topf_short.append(f"[{movie_name}](https://letterboxd.com/film/{movie_id}): **{film['guild_avg']:.2f}** ({film['rating_count']})")
        counter += 1

    return topf_short

def human_count(n):
    m = n / 1000
    if m >= 1:
        return f'{round(m, 1)}k'
    return n
