import os, socket, inspect, re


class Config:
    def __init__(self):
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in map(str.strip, f):
                    line = re.match(r'''(.*)=['"]?([^"']+)"?$''', line)
                    if line:
                        key, value = line.groups()
                        if key not in os.environ:
                            os.environ[key] = value
        for key, value in inspect.getmembers(Config):
            if key.startswith("_"):
                continue
            setattr(
                self, key, self.__annotations__[key](os.environ.get(key.upper(), value))
            )

    mpd_music_dir: str = "/var/lib/mpd/music"
    mpd_host: str = "127.0.0.1"
    mpd_port: int = 6600
    mpd_password: str = ""
    stream_url: str = "http://{hostname}:8000/stream.off".format(
        hostname=socket.gethostname()
    )
    webhook_host: str = "https://{hostname}".format(
        hostname=socket.gethostname()
    )
    webhook_path: str = "/bot"
    bot_token: str = ''
    bot_group_id: int = 0
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    history_len: int = 30
    client_max_size: int = 100 * 1024 * 1024  # 100mb


config = Config()
