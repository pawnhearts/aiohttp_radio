import itertools
import json
import os
import re

import aiohttp
import jinja2
from aiohttp import web
import asyncio
import aiohttp_jinja2
from shlex import split
from loguru import logger as log
from settings import config


async def index(request):
    ws_current = web.WebSocketResponse()
    ws_ready = ws_current.can_prepare(request)
    if not ws_ready.ok:
        return aiohttp_jinja2.render_template(
            "index.vue", request, {"stream_url": request.app["stream_url"]}
        )

    await ws_current.prepare(request)

    log.info("joined")

    await ws_current.send_json({"action": "connect"})

    for ws in request.app["websockets"]:
        await ws.send_json({"action": "join"})
    request.app["websockets"].add(ws_current)

    for msg in request.app["history"]:
        await ws_current.send_json(msg)

    filename, size = "", 0

    while not ws_current.closed:
        try:
            msg = await ws_current.receive_json()
        except TypeError:
            break

        try:
            name, text = msg["name"], msg["text"]
        except KeyError:
            await ws_current.send_json({"action": "error"})
            continue
        msg = {"action": "message", "name": name, "text": text}
        for ws in request.app["websockets"]:
            await ws.send_json(msg)
        for youtube_link in re.findall(
            r"(https:\/\/?(?:www\.)?youtu\.?be\S+)", str(text or "")
        ):
            await request.app["youtube_queue"].put(youtube_link)
        request.app["history"].append(msg)
        while len(request.app["history"]) > config.history_len:
            request.app["history"].pop(0)

    request.app["websockets"].remove(ws_current)
    log.info("disconnected.")
    for ws in request.app["websockets"]:
        await ws.send_json({"action": "disconnect"})

    return ws_current


async def store_mp3_handler(request):

    data = await request.post()

    mp3 = data.get("mp3")
    log.info(mp3)
    if not mp3:
        raise web.HTTPBadRequest

    filename = os.path.basename(mp3.filename)
    log.info(filename)

    if os.path.splitext(filename)[1].lower() not in [".mp3", ".ogg"]:
        raise web.HTTPBadRequest
    with open(filename, "wb") as f:
        f.write(mp3.file.read())
    proc = await asyncio.create_subprocess_exec(
        *split(request.app["mpc_command"]),
        "insert",
        filename,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    log.debug(stdout.decode())
    log.debug(stderr.decode())
    if proc.returncode != 0:
        raise web.HTTPBadRequest

    # for ws in request.app["websockets"]:
    #    await ws.send_json({"name": "radiobot", "text": f"file {filename} uploaded"})

    return web.HTTPFound("/")


async def shell_read(cmd):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return stdout.decode()


async def now_playing_task(app):
    pos = None
    playlist = []
    song = None
    for counter in itertools.cycle(range(15)):  # refresh playlist every 15 seconds
        data = {"action": "np"}
        out = await shell_read(f"{app['mpc_command']} play")
        if not out:
            continue
        out = out.splitlines()
        try:
            data["song"] = out[0]
            if song != data["song"]:
                song = data["song"]
                if app["bot"]:
                    await app["bot"].send_message(
                        config.bot_group_id, f"now playing {song}"
                    )

            data["status"], data["time"], data["progress"] = re.match(
                r"\[(\w+)\].*\s([\d\:\/]+).*\((.+)\%\)", out[1]
            ).groups()
            data["pos"], data["total"] = map(
                int, re.search(r"\#(\d+)\/(\d+)\s", out[1]).groups()
            )
            if data["pos"] != pos or counter == 0:
                pos = data["pos"]
                new_playlist = (
                    await shell_read(f"{app['mpc_command']} playlist")
                ).splitlines()
                if set(new_playlist) - set(playlist):
                    await app["bot"].send_message(
                        config.bot_group_id,
                        f"added to playlist: {', '.join(set(new_playlist) - set(playlist))}",
                    )
                playlist = new_playlist

            data["playlist"] = playlist
            data["number_of_users"] = len(app["websockets"])
        except Exception as e:
            log.exception(e)
        for ws in app["websockets"]:
            await ws.send_json(data)
        await asyncio.sleep(1)


async def add_from_youtube_task(app):
    os.chdir(os.environ.get("MPD_MUSIC_DIR", "/var/lib/mpd/music"))
    while True:
        url = await app["youtube_queue"].get()
        for ws in app["websockets"]:
            await ws.send_json({"name": "radiobot", "text": f"got url {url}"})
        if app["bot"]:
            await app["bot"].send_message(config.bot_group_id, f"got url {url}")
        proc = await asyncio.create_subprocess_exec(
            "youtube-dl",
            "-c",
            "-q",
            "-x",
            "--audio-format",
            "mp3",
            url,
            "--exec",
            f"{app['mpc_command']} update && {app['mpc_command']} insert {{}}",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            for ws in app["websockets"]:
                await ws.send_json(
                    {"name": "radiobot", "text": f"downloaded {stdout.decode()}"}
                )
            if app["bot"]:
                await app["bot"].send_message(config.bot_group_id, f"downloaded {url}")


async def save_history_task(app):
    path = app["history_file"]
    path_tmp = f"{path}.tmp"
    while True:
        await asyncio.sleep(20)
        with open(path_tmp, "w") as f:
            json.dump(app["history"], f)
        os.rename(path_tmp, path)
        log.info(f"History saved to {path}")


def favicon_handler(path):
    with open(path, "rb") as f:
        data = f.read()

    async def handler(request):
        return web.Response(body=data, content_type="image/png")

    return handler


async def create_tasks(app):
    app["youtube_task"] = asyncio.create_task(add_from_youtube_task(app))
    app["now_playing_task"] = asyncio.create_task(now_playing_task(app))
    app["save_history_task"] = asyncio.create_task(save_history_task(app))


async def init_app():

    app = web.Application(client_max_size=config.client_max_size)

    app["websockets"] = set()
    host = config.mpd_host
    if config.mpd_password:
        host = f"{config.mpd_password}@{host}"
    app["history_file"] = os.path.abspath("history.json")
    if os.path.exists(app["history_file"]):
        with open(app["history_file"], "r") as f:
            app["history"] = json.load(f)
    else:
        app["history"] = []
    app["mpc_command"] = f"mpc --host '{host}' --port {config.mpd_port}"
    app["stream_url"] = os.environ.get(
        "STREAM_URL", os.path.expandvars("http://$HOSTNAME:8080/stream.ogg")
    )
    app["youtube_queue"] = asyncio.Queue()

    # app.on_startup.append(create_tasks)
    app.on_shutdown.append(shutdown)
    from bot import init_bot

    app.on_startup.append(init_bot)

    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(os.path.abspath("templates"))
    )

    app.router.add_get("/", index)
    app.router.add_post("/upload", store_mp3_handler),
    app.router.add_static("/static", os.path.abspath("static/"), name="static")
    app.router.add_static("/music", os.path.abspath(config.mpd_music_dir), name="music")
    app.router.add_get(
        "/favicon.ico", favicon_handler(os.path.abspath("static/favicon.ico"))
    )

    return app


async def shutdown(app):
    for ws in app["websockets"]:
        await ws.close()
    app["websockets"].clear()


def main():
    app = init_app()
    web.run_app(app, host=config.listen_host, port=config.listen_port)


if __name__ == "__main__":
    main()
