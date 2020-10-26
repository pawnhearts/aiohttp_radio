from aiohttp import ClientSession
from bs4 import BeautifulSoup


_cache = {}


async def fetch_art(filename):
    if filename in _cache:
        return _cache[filename]
    filename = filename.rsplit('-', 1)[0]
    async with ClientSession() as client:
        res = client.get('https://yandex.ru/images/search?from=tabbar', {'text': filename})
        soup = BeautifulSoup(await res.text())
        try:
            src = 'https:{}'.format(soup.find('a', {'class':'serp-item__link'}).find('img')['src'])
            _cache[filename] = src
            return src
        except (AttributeError, KeyError):
            return
