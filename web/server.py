import os
import re

import jinja2
from aiohttp import web
import asyncio
import aiohttp_jinja2
from aiompd import Client as MPDClient
from loguru import logger as log

from settings import config


async def index(request):
    ws_current = web.WebSocketResponse()
    ws_ready = ws_current.can_prepare(request)
    if not ws_ready.ok:
        return aiohttp_jinja2.render_template(
            "index.html", request, {"stream_url": request.app["stream_url"]}
        )

    await ws_current.prepare(request)

    log.info("joined")

    await ws_current.send_json({"action": "connect"})

    for ws in request.app["websockets"]:
        await ws.send_json({"action": "join"})
    request.app["websockets"].add(ws_current)

    for ws in request.app["websockets"]:
        await ws.send_json({'action': 'count', 'number': len(request.app["websockets"])})

    for msg in request.app['history']:
        await ws_current.send_json(msg)

    while True:
        msg = await ws_current.receive_json()

        try:
            name, text = msg["name"], msg["text"]
        except KeyError:
            await ws_current.send_json({"action": "error"})
            continue
        msg = {"action": "message", "name": name, "text": text}
        for ws in request.app["websockets"]:
            await ws.send_json(msg)
        for youtube_link in re.findall(r"(https:\/\/?(?:www\.)?youtu\.?be\S+)", text):
            await request.app["youtube_queue"].put(youtube_link)
        request.app['history'].append(msg)
        request.app['history'] = request.app['history'][-config.history_len:]

    request.app["websockets"].remove(ws_current)
    for ws in request.aoo["websockets"]:
        await ws.send_json({'action': 'count', 'number': len(request.app["websockets"])})
    log.info("disconnected.")
    for ws in request.app["websockets"]:
        await ws.send_json({"action": "disconnect"})

    return ws_current


async def shell_read(cmd):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return stdout.decode()


async def now_playing_task(app):
    np = None
    queued = []
    while True:
        data = {"action": "np"}
        out = await shell_read(f"{app['mpc_command']} play")
        if not out:
            continue
        out = out.splitlines()
        try:
            data["song"] = out[0]
            data["status"], data["time"], data["progress"] = re.match(
                r"\[(\w+)\].*\s([\d\:\/]+).*\((.+)\%\)", out[1]
            ).groups()
            if data["song"] != np:
                np = data["song"]
                queued = (await shell_read(f"{app['mpc_command']} queued")).splitlines()
            data["queued"] = queued
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
        proc = await asyncio.create_subprocess_exec(
            "youtube-dl",
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
                    {"name": "radiobot", "text": f" added {stdout.decode()}"}
                )


async def create_tasks(app):
    app["youtube_task"] = asyncio.create_task(add_from_youtube_task(app))
    app["now_playing_task"] = asyncio.create_task(now_playing_task(app))


async def init_app():

    app = web.Application()

    app["websockets"] = set()
    host = config.mpd_host
    if config.mpd_password:
        host = f'{config.mpd_password}@{host}'
    app["mpc_command"] = f"mpc --host '{host}' --port {config.mpd_port}"
    app["stream_url"] = os.environ.get(
        "STREAM_URL", os.path.expandvars("http://$HOSTNAME:8080/stream.ogg")
    )
    app["youtube_queue"] = asyncio.Queue()
    app['history'] = []

    app.on_startup.append(create_tasks)
    app.on_shutdown.append(shutdown)

    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(os.path.abspath("templates"))
    )

    app.router.add_get("/", index)

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
