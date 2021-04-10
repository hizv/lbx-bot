import asyncio
import hashlib
import hmac
import string
import time
import uuid
import urllib.parse

import aiohttp
from config import SETTINGS

class LetterboxdError(Exception):
    pass

async def api_call(path, params=None, letterboxd=True, is_json=True):
    if not params:
        params = dict()
        api_url = path
    if letterboxd:
        url = SETTINGS['letterboxd']['api_base'] + path
        params['apikey'] = SETTINGS['letterboxd']['api_key']
        params['nonce'] = str(uuid.uuid4())
        params['timestamp'] = int(time.time())
        url += '?' + urllib.parse.urlencode(params)
        api_url = url + '&signature=' +  __sign(url)
    async with aiohttp.ClientSession() as cs:
        async with cs.get(api_url) as r:
            if r.status >= 500 and letterboxd:
                raise LetterboxdError('A request to the Letterboxd API failed.' +
                                    ' This may be due to a server issue.')
            elif r.status >= 400:
                return ''
            if is_json:
                response = await r.json()
            else:
                response = await r.read()
    return response

def __sign(url, body=''):
    # Create the salted bytestring
    signing_bytestring = b'\x00'.join(
        [str.encode('GET'),
         str.encode(url),
         str.encode(body)])
    # applying an HMAC/SHA-256 transformation, using our API Secret
    signature = hmac.new(
        str.encode(SETTINGS['letterboxd']['api_secret']),
        signing_bytestring,
        digestmod=hashlib.sha256)
    # get the string representation of the hash
    signature_string = signature.hexdigest()
    return signature_string
