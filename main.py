import os
import shutil
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_CONFIG = os.path.join(BASE_DIR, "demo-config.yaml")
TARGET_DIR = "/home/tgfs/.tgfs"
TARGET_CONFIG = os.path.join(TARGET_DIR, "config.yaml")

print("=== TGFS DEBUG START ===")
print("BASE_DIR =", BASE_DIR)
print("FILES =", os.listdir(BASE_DIR))
print("SOURCE_CONFIG =", SOURCE_CONFIG)
print("SOURCE_EXISTS =", os.path.exists(SOURCE_CONFIG))

os.makedirs(TARGET_DIR, exist_ok=True)

if os.path.exists(SOURCE_CONFIG):
    shutil.copyfile(SOURCE_CONFIG, TARGET_CONFIG)
    print("COPIED CONFIG TO", TARGET_CONFIG)
else:
    print("CONFIG NOT FOUND")

print("TARGET_EXISTS =", os.path.exists(TARGET_CONFIG))
print("=== TGFS DEBUG END ===")

try:
    import uvloop  # type: ignore[import]
    uvloop.install()
except ImportError:
    logging.warning("uvloop is not installed, using default event loop")

from uvicorn.config import Config as UvicornConfig
from uvicorn.server import Server

from tgfs.app import create_app
from tgfs.config import Config, get_config
from tgfs.core import Client, Clients
from tgfs.telegram import PyrogramAPI, TDLibApi, TelethonAPI, pyrogram, telethon


async def create_clients(config: Config) -> Clients:
    if config.telegram.lib == "pyrogram":
        tdlib_api = TDLibApi(
            account=(
                PyrogramAPI(await pyrogram.login_as_account(config))
                if config.telegram.account
                else None
            ),
            bots=[PyrogramAPI(bot) for bot in await pyrogram.login_as_bots(config)],
        )
    else:
        tdlib_api = TDLibApi(
            account=(
                TelethonAPI(await telethon.login_as_account(config))
                if config.telegram.account
                else None
            ),
            bots=[TelethonAPI(bot) for bot in await telethon.login_as_bots(config)],
        )

    clients: Clients = {}

    for channel_id in config.telegram.private_file_channel:
        metadata_cfg = config.tgfs.metadata[channel_id]
        clients[metadata_cfg.name] = await Client.create(
            channel_id,
            metadata_cfg,
            tdlib_api,
            (
                config.telegram.account.used_to_upload
                if config.telegram.account
                else False
            ),
        )

    return clients


async def run_server(app, host: str, port: int, name: str) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Starting %s server on %s:%s", name, host, port)

    server_config = UvicornConfig(
        app,
        host=host,
        port=port,
        loop="none",
        log_level="info",
    )
    server = Server(config=server_config)
    await server.serve()


async def main() -> None:
    config = get_config()
    clients = await create_clients(config)
    app = create_app(clients, config)
    await run_server(app, config.tgfs.server.host, config.tgfs.server.port, "TGFS")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
