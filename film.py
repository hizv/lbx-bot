import json


def get_link(film_details):
    for link in film_details['links']:
        if link['type'] == 'letterboxd':
            return link['url']


def get_description(film_details, film_stats):
    description = ''
    if 'originalName' in film_details:
        description += f"_{film_details['originalName']}_\n"

    director_str = ''
    for director in film_details['directors']:
        director_str += director['name'] + ', '

    description += director_str[:-2] + '\n'

    if 'rating' in film_stats:
        description += f"{round(film_stats['rating'], 2)} from "
        description += f"{human_count(film_stats['counts']['ratings'])} ratings\n"
    else:
        description += f"Watched by {film_stats['counts']['watches']} people"

    return description


def get_search_result(lbx, film_keywords):
    search_request = {
        'perPage': 1,
        'input': film_keywords,
        'include': 'FilmSearchItem'
    }

    search_response = lbx.search(search_request=search_request)

    # print(json.dumps(search_response, sort_keys=True, indent=4))
    return search_response['items'][0]['film']


def human_count(n):
    m = n / 1000
    if m >= 1:
        return f'{round(m, 1)}k'
    else:
        return n
