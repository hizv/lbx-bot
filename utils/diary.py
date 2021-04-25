import discord
from markdownify import markdownify
from fuzzywuzzy import process
from .film import get_link
from utils import api

async def get_diary_embed(dids):
    description = ''
    for did in dids:
        d_entry = await api.api_call(path=f'log-entry/{did}')
        film = d_entry['film']
        description += f"**[{film['name']} ({film['releaseYear']})]"
        description += f'({get_link(d_entry)})**\n'
        if 'diaryDetails' in d_entry:
            description += f"**{d_entry['diaryDetails']['diaryDate']}** "
        if 'rating' in d_entry:
            description += ' ' + int(d_entry['rating']) * '★'
            if str(d_entry['rating'])[-1] == '5':
                description += '½ '
        if d_entry['like']:
            description += ' <3'
        if d_entry['diaryDetails']['rewatch']:
            description += ' ↺'
        if 'review' in d_entry:
            if review['containsSpoilers']:
                description += '\n```Contains spoilers```'
            else:
                description += '\n```' + markdownify(d_entry['review']['text'][:1600]) + '```'
        description += '\n'
    embed = discord.Embed(description=description)
    if 'poster' in film:
        embed.set_thumbnail(url=film['poster']['sizes'][-1]['url'])

    return embed

async def get_lid(lbx, lb_id):
    m_result = lbx.search(search_request={
        'include': 'MemberSearchItem',
        'input': lb_id,
        'perPage': 20
    })
    lid_list = { m['member']['username']:m['member']['id'] for m in m_result['items']}
    match = process.extractOne(lb_id, lid_list.keys())
    return lid_list[match[0]]
