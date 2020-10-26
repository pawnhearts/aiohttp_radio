import re

from aiogram import Bot, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import Dispatcher
from aiogram.dispatcher.webhook import SendMessage, WebhookRequestHandler
from aiogram.types import ChatType
from aiogram.utils.executor import start_webhook

from loguru import logger as logging
from settings import config


# webhook settings
WEBHOOK_URL = f"{config.webhook_host}{config.webhook_path}"


bot = Bot(token=config.bot_token)

dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())



@dp.message_handler(chat_id=config.bot_group_id)
async def echo(message: types.Message):
    if message.document and message.document.file_id:
        f = await bot.get(message.document.file_id)
        print(f)
        print(await bot.download_file(f.file_path))

    for youtube_link in re.findall(
            r"(https:\/\/?(?:www\.)?youtu\.?be\S+)", message.text or ''
    ):
        await bot.web_app["youtube_queue"].put(youtube_link)
    # or reply INTO webhook
    for ws in bot.web_app['websockets']:
        await ws.send_json({"action": "message", "name": message.from_user.username, "text": message.text})
    # return SendMessage(message.chat.id, message.text)


async def init_bot(app):
    print(await bot.set_webhook(WEBHOOK_URL))
    print(await dp.bot.me)
    app['BOT_DISPATCHER'] = dp
    app['bot'] = bot
    bot.web_app = app
    app.router.add_route('*', config.webhook_path, WebhookRequestHandler, name='webhook_handler')


async def on_shutdown(dp):
    logging.warning('Shutting down..')

    await bot.delete_webhook()

    await dp.storage.close()
    await dp.storage.wait_closed()

    logging.warning('Bye!')


