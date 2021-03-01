from fuzzywuzzy import process

async def get_list_id(api, lid, keywords):
    params = {
        'member': lid,
        'memberRelationship': 'Owner',
        'perPage': 50,
        'where': 'Published',
        'sort': 'ListPopularity'
    }

    res = api.api_call('lists', params)
    L_list = { s['name']:s['id'] for s in res.json()['items']}
    match = process.extractOne(keywords, L_list.keys())
    if match[1] > 70:
        return L_list[match[0]]

