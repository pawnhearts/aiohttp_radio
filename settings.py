import os, socket


class Config:
    def __init__(self):
        for key, value in self.__class__.__dict__.values():
            if key.startswith('_'):
                continue
            setattr(self, key, self.__annotations__[key](os.environ.get(key.upper(), value)))

    mpd_music_dir: str = '/var/lib/mpd/music'
    mpd_host: str = '127.0.0.1'
    mpd_port: int = 6600
    mpd_password: str = ''
    stream_url: str = 'http://{hostname}:8000/stream.off'.format(hostname=socket.gethostname())
    listen_host: str = '0.0.0.0'
    listen_port: int = 8080
    history_len: int = 30


config = Config()
