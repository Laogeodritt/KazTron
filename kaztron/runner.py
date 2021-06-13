import asyncio
import logging
import sys

import discord
from discord.ext import commands

import kaztron
from kaztron import KazClient
from kaztron.config import get_kaztron_config, KaztronConfig, get_runtime_config
from kaztron.discord_patches import apply_patches

__all__ = ('ErrorCodes', 'run', 'get_daemon_context')
logger = logging.getLogger("kaztron.bootstrap")


class ErrorCodes:
    OK = 0
    ERROR = 1
    DAEMON_RUNNING = 4
    DAEMON_NOT_RUNNING = 5
    EXTENSION_LOAD = 7
    CFG_FILE = 17


def run(loop: asyncio.AbstractEventLoop):
    """ Set up and run the bot. """

    logger.info("Welcome to KazTron v{}, booting up...".format(kaztron.__version__))

    config = get_kaztron_config()
    state = get_runtime_config()

    # intents
    intents = discord.Intents.default()
    intents.members = True
    intents.typing = False
    intents.presences = False
    intents.integrations = False
    intents.webhooks = False
    intents.invites = False

    # create bot instance (+ some custom hacks)
    client = KazClient(
        config=config,
        client_state=state,

        # Client arguments
        intents=intents,
        chunk_guilds_at_startup=True,
        status=discord.Status.idle,
        activity=discord.Game(" some startup boops..."),
        # disallow @everyone/@here by default; per-msg override via allowed_mentions param to send()
        allowed_mentions=discord.AllowedMentions(everyone=False),

        # Bot arguments
        command_prefix='.',
        pm_help=True,
        # formatter=DiscordHelpFormatter(kaz_help_parser, show_check_failure=True)
        # help_command=
        )
    apply_patches(client)

    # Load core extension (core + rolemanager)
    client.load_extension("kaztron.core")

    # Load extensions
    startup_extensions = config.get("core", "extensions", default=tuple())
    for extension in startup_extensions:
        logger.debug(f"Loading extension: '{extension}'")
        # noinspection PyBroadException
        try:
            client.load_extension("kaztron.cog." + extension)
        except Exception:
            logger.exception(f"Failed to load extension '{extension}'")
            sys.exit(ErrorCodes.EXTENSION_LOAD)

    external_extensions = config.get("core", "extensions_external", default=tuple())
    for extension in external_extensions:
        logger.debug(f"Loading external extension: {extension}")
        # noinspection PyBroadException
        try:
            client.load_extension(extension)
        except Exception:
            logger.exception(f"Failed to load external extension '{extension}'")
            sys.exit(ErrorCodes.EXTENSION_LOAD)

    # noinspection PyBroadException
    try:
        loop.run_until_complete(client.start(config.get("discord", "token"), reconnect=True))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        logger.debug("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.info("Client closed.")
        sys.exit(ErrorCodes.OK)
    except Exception:
        logger.exception("Uncaught exception during bot execution")
        logger.debug("Waiting for client to close...")
        loop.run_until_complete(client.close())
        logger.info("Client closed.")
        raise
    finally:
        logger.debug("Cancelling pending tasks...")
        # BEGIN CONTRIB
        # Modified from code from discord.py.
        #
        # Source: https://github.com/Rapptz/discord.py/blob/
        # 09bd2f4de7cccbd5d33f61e5257e1d4dc96b5caa/discord/client.py#L517
        #
        # Original code Copyright (c) 2015-2016 Rapptz. MIT licence.
        pending = asyncio.Task.all_tasks(loop=loop)
        gathered = asyncio.gather(*pending, loop=loop, return_exceptions=True)
        # noinspection PyBroadException
        try:
            gathered.cancel()
            loop.run_until_complete(gathered)
            gathered.exception()
        except Exception:
            pass
        # END CONTRIB


def get_daemon_context(config: KaztronConfig):
    import os
    import pwd
    import grp
    from pathlib import Path
    from daemon import DaemonContext, pidfile

    bot_dir = Path(sys.modules['__main__'].__file__).resolve().parent
    pid = pidfile.TimeoutPIDLockFile(config.get('core', 'daemon_pidfile'))
    daemon_log = open(config.get('core', 'daemon_log'), 'w+')
    daemon_context = DaemonContext(
        working_directory=str(bot_dir),
        umask=0o002,
        pidfile=pid,
        stdout=daemon_log,
        stderr=daemon_log
    )
    username = config.get('core', 'daemon_user', None)
    group = config.get('core', 'daemon_group', None)
    if username:
        pw = pwd.getpwnam(username)
        daemon_context.uid = pw.pw_uid
        daemon_context.gid = pw.pw_gid
        os.environ['HOME'] = pw.pw_dir
    if group:
        daemon_context.gid = grp.getgrnam(group).gr_gid
    return daemon_context
