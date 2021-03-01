from discord import Embed
import wikipedia

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
    embed = Embed(
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
