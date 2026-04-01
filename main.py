import os
import shutil
import asyncio
import logging
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

TARGET_DIR = "/home/tgfs/.tgfs"
TARGET_CONFIG = os.path.join(TARGET_DIR, "config.yaml")

os.makedirs(TARGET_DIR, exist_ok=True)

found = None
for root, dirs, files in os.walk("/app"):
    if "config.yaml" in files:
        found = os.path.join(root, "config.yaml")
        break
    if "demo-config.yaml" in files:
        found = os.path.join(root, "demo-config.yaml")
        break

print("=== TGFS DEBUG START ===")
print("FOUND CONFIG =", found)

if found:
    shutil.copyfile(found, TARGET_CONFIG)
    print("COPIED CONFIG TO", TARGET_CONFIG)
else:
    print("NO CONFIG FILE FOUND IN PROJECT")

print("EXISTS AFTER COPY =", os.path.exists(TARGET_CONFIG))

github_token = os.environ.get("GITHUB_TOKEN", "").strip()
print("GITHUB TOKEN PRESENT =", bool(github_token))
print("GITHUB TOKEN LENGTH =", len(github_token))

if os.path.exists(TARGET_CONFIG):
    with open(TARGET_CONFIG, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    metadata = data.get("tgfs", {}).get("metadata", {})
    for channel_id, cfg in metadata.items():
        if isinstance(cfg, dict) and cfg.get("type") == "github_repo":
            cfg["access_token"] = github_token
            print("INJECTED TOKEN FOR", channel_id)
            print("REPO FOR", channel_id, "=", cfg.get("repo"))

    with open(TARGET_CONFIG, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    with open(TARGET_CONFIG, "r", encoding="utf-8") as f:
        verify = yaml.safe_load(f) or {}

    for channel_id, cfg in verify.get("tgfs", {}).get("metadata", {}).items():
        token_len = len((cfg.get("access_token") or "").strip())
        print("VERIFIED TOKEN LENGTH FOR", channel_id, "=", token_len)
        print("VERIFIED REPO FOR", channel_id, "=", cfg.get("repo"))

print("FINAL EXISTS =", os.path.exists(TARGET_CONFIG))
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
