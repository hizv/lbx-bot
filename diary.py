import discord
from markdownify import markdownify
from film import get_link

async def get_diary_embed(api, dids):
    description = ''
    for did in dids:
        res = api.api_call(path=f'log-entry/{did}')
        d_entry = res.json()
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
            description += '\n```' + markdownify(d_entry['review']['text']) + '```'
        description += '\n'
    embed = discord.Embed(description=description)
    if 'poster' in film:
        embed.set_thumbnail(url=film['poster']['sizes'][-1]['url'])

    return embed

async def get_lid(lbx, lb_id):
    m_result = lbx.search(search_request={
        'include': 'MemberSearchItem',
        'input': lb_id,
        'perPage': 1
    })
    lid = m_result['items'][0]['member']['id']
    return lid
