from aiohttp import web



from mpd import MPDClient
client = MPDClient()
client.connect("mpd", 6600)
#client.password('666')
client.add('/1.mp3')
client.random(1)
client.play()
#client.update()


async def hello(request):
    return web.Response(text=repr(client.status()))

app = web.Application()
app.add_routes([web.get('/', hello)])
web.run_app(app)
# youtube-dl -x --audio-format mp3 

