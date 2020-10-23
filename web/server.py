import os
import re
from json import JSONDecodeError

import aiohttp
import jinja2
from aiohttp import web
from asyncio.subprocess import Process, PIPE
import asyncio
import aiohttp_jinja2
from loguru import logger as log

youtube_queue = asyncio.Queue()


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

    while True:
        msg = await ws_current.receive_json()

        if msg.type == aiohttp.WSMsgType.text:
            try:
                name, text = msg["name"], msg["text"]
            except KeyError:
                await ws_current.send_json({"action": "error"})
                continue
            for ws in request.app["websockets"]:
                if ws is not ws_current:
                    await ws.send_json({"action": "sent", "name": name, "text": text})
            for youtube_link in re.findall(
                r"(?:https?:\/\/)?(?:www\.)?youtu\.?be(?:\.com)?\/?.*(?:watch|embed)?(?:.*v=|v\/|\/)([\w\-_]+)\&?",
                text,
            ):
                await youtube_queue.put(youtube_link)
        else:
            break

    request.app["websockets"].remove(ws_current)
    log.info("disconnected.")
    for ws in request.app["websockets"].values():
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
        data = {}
        out = await shell_read(f"{app['mpc_command']} play")
        if not out:
            continue
        out = out.splitlines()
        try:
            data["song"] = out[0]
            data["status"], data["time"], data["progress"] = re.match(
                r"\[(\w+)\].*\s([\d\:\/]+).*\((.+)\)", out[2]
            ).groups()
            if data["song"] != np:
                np = data["song"]
                queued = shell_read(f"{app['mpc_command']} queued").splitlines()
            data["queued"] = queued
        except Exception as e:
            log.exception(e)
        for ws in app["websockets"]:
            await ws.send_json(data)
        await asyncio.sleep(1)


async def add_from_youtube_task(app):
    os.chdir(os.environ.get("MPD_MUSIC_DIR", "/var/lib/mpd/music"))
    while True:
        url = await youtube_queue.get()
        for ws in app["websockets"]:
            await ws.send_json({"name": "radiobot", "text": f"got url {url}"})
        proc = await asyncio.create_subprocess_exec(
            "youtube-dl",
            "-q",
            "-x",
            "--audio-format",
            "mp3",
            url,
            "--exec-",
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
    app["mpc_command"] = f"mpc --host {os.environ.get('MPD_HOST', '127.0.0.1')}"
    app["stream_url"] = os.environ.get(
        "STREAM_URL", os.path.expandvars("http://$HOSTNAME:8080/stream.ogg")
    )

    app.on_startup.append(create_tasks)
    app.on_shutdown.append(shutdown)

    aiohttp_jinja2.setup(app, loader=jinja2.PackageLoader("aiohttp_radio", "templates"))

    app.router.add_get("/", index)

    return app


async def shutdown(app):
    for ws in app["websockets"]:
        await ws.close()
    app["websockets"].clear()


def main():
    app = init_app()
    web.run_app(app)


if __name__ == "__main__":
    main()
