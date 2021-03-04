from discord import Embed

def get_film_embed(lbx, film_keywords='', verbosity=0, film_id='', db=None):
    if film_keywords:
        film = get_search_result(lbx, film_keywords)
        if not film:
            return None
        film_instance = lbx.film(film['id'])
    if film_id:
        film_instance = lbx.film(film_id)
    film_details = film_instance.details()
    film_stats = film_instance.statistics()

    title = f"{film_details['name']}"
    if 'releaseYear' in film_details:
        title += ' (' + str(film_details['releaseYear']) + ')'
    embed = Embed(
        title=title,
        url=get_link(film_details),
        description=get_description(film_details, film_stats, verbosity, db),
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


def get_description(film_details, film_stats, verbosity=0, db=None):
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
        print('Yo')
        movie_id = get_link(film_details).split('/')[-2]
        db_info = db.films.find_one({'movie_id': movie_id})
        if db_info and 'guild_avg' in db_info:
            description += f"Server: **{db_info['guild_avg']:.2f}** from {db_info['rating_count']}\n"

    if film_details['genres']:
        genre_str = '*'
        for genre in film_details['genres']:
            genre_str += genre['name'] + ', '
        description += genre_str[:-2] + '*'
    if verbosity > 0:
        description += '\n```' + film_details['description'] + '```\n'

    return description


def get_search_result(lbx, film_keywords):
    search_request = {
        'perPage': 1,
        'input': film_keywords,
        'include': 'FilmSearchItem'
    }

    search_response = lbx.search(search_request=search_request)

    if not search_response['items']:
        return None
    return search_response['items'][0]['film']


def who_knows_embed(lbx, db, film_keywords):
    ratings = db.ratings
    films = db.films
    users = db.users
    description = ''

    film_res = get_search_result(lbx, film_keywords)
    if not film_res:
        return None

    link = get_link(film_res)
    movie_id = link.split('/')[-2]

    details = {'name': film_res['name']}
    db_info = films.find_one({'movie_id': movie_id})

    for rating in ratings.find({'movie_id': movie_id}):
        lb_id = rating['lb_id']
        rating_id = rating['rating_id']
        if rating_id == -1:
            rating_id = '✓'
        #user = users.find_one({'lb_id': lb_id})
        description += f"[{lb_id}](https://letterboxd.com/{lb_id}) **{rating_id}**\n"

    title = f"Who knows {film_res['name']}"
    if 'releaseYear' in film_res:
        title += ' (' + str(film_res['releaseYear']) + ')'
        details['releaseYear'] = film_res['releaseYear']

    embed = Embed(
        title=title,
        url=link,
        description=description
    )
    if 'poster' in film_res:
        url = film_res['poster']['sizes'][-1]['url']
        embed.set_thumbnail(url=url)
        details['poster_url'] = url

    if db_info:
        embed.set_footer(text=f"Server average: {db_info['guild_avg']:.2f}")

    films.update_one({'movie_id': movie_id}, {'$set': details}, upsert=True)
    return embed

def top_films_list(db, threshold):
    top_films = db.films.find(
        { 'rating_count': {'$gt': threshold-1}
    }).sort('guild_avg', -1)
    # .aggregate(
    #     [
    #        { '$sort': {'guild_avg': -1 } }
    #     ]
    # )
    topf_short = []
    for film in top_films[:200]:
        movie_id = film['movie_id']
        if 'name' in film:
            movie_id = film['name']
        topf_short.append(f"[{movie_id}](https://letterboxd.com/film/{movie_id}): **{film['guild_avg']:.2f}** ({film['rating_count']})")

    return topf_short

def human_count(n):
    m = n / 1000
    if m >= 1:
        return f'{round(m, 1)}k'
    return n
