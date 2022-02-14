import asyncio
import logging
import sys
from typing import Sequence

import discord

import kaztron
from kaztron import KazClient
from kaztron.config import get_kaztron_config, KaztronConfig, get_runtime_config, ConfigKeyError
from kaztron.discord_patches import apply_patches
from kaztron.utils.asyncio import all_tasks

__all__ = ('ErrorCodes', 'run_kaztron', 'get_daemon_context')
logger = logging.getLogger("kaztron.bootstrap")


class ErrorCodes:
    OK = 0
    ERROR = 1
    DAEMON_RUNNING = 4
    DAEMON_NOT_RUNNING = 5
    EXTENSION_LOAD = 7
    CFG_FILE = 17


def run_kaztron(loop: asyncio.AbstractEventLoop):
    """ Set up and run the bot. """

    logger.info("Welcome to KazTron v{}, booting up...".format(kaztron.__version__))

    config = get_kaztron_config()
    state = get_runtime_config()
    try:
        client = create_client(config, state)
        client.load_extension("kaztron.core")
        for name in client.config.get([]).keys():
            if name not in kaztron.cfg_core_sections:  # section is an extension, not core config
                load_all_extensions(client, (name,))
    except Exception:
        logger.exception("Uncaught exception during bot setup. Aborting.")
        raise

    # noinspection PyBroadException
    try:
        token = config.get(("core", "discord", "token"))
        loop.run_until_complete(client.start(token, reconnect=True))
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
        pending = all_tasks(loop=loop)
        gathered = asyncio.gather(*pending, loop=loop, return_exceptions=True)
        # noinspection PyBroadException
        try:
            gathered.cancel()
            loop.run_until_complete(gathered)
            gathered.exception()
        except Exception:
            pass
        # END CONTRIB


def create_client(config: KaztronConfig, state: KaztronConfig) -> KazClient:    # intents
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
    return client


def load_all_extensions(client: KazClient, cfg_path: Sequence[str]):
    cfg_path = tuple(cfg_path)
    cfg_path_str = '.'.join(cfg_path)
    try:
        is_enabled = client.config.get(cfg_path + ('extension',))
        package = client.config.get(cfg_path + ('package',), default='kaztron.cog.' + cfg_path_str)
    except (ConfigKeyError, TypeError):
        return  # this is not a subsection and can be silently skipped

    if not is_enabled:
        logger.warning(f"Skipping disabled extension: '{cfg_path_str}'")
        return

    logger.debug(f"Loading extension: '{cfg_path_str}' (package: '{package}')")
    # noinspection PyBroadException
    try:
        client.load_extension(package)
    except Exception:
        logger.exception(f"Failed to load extension '{cfg_path_str}'")
        sys.exit(ErrorCodes.EXTENSION_LOAD)

    # try loading any subsections as subpackages
    for subsection in client.config.get(cfg_path).keys():
        load_all_extensions(client, cfg_path + (subsection,))


def get_daemon_context(config: KaztronConfig):
    import os
    import pwd
    import grp
    from pathlib import Path
    from daemon import DaemonContext, pidfile

    bot_dir = Path(sys.modules['__main__'].__file__).resolve().parent
    pid = pidfile.TimeoutPIDLockFile(config.get(('core', 'daemon', 'pidfile')), "pid.lock")
    daemon_log = open(config.get(('core', 'daemon', 'log')), 'w+')
    daemon_context = DaemonContext(
        working_directory=str(bot_dir),
        umask=0o002,
        pidfile=pid,
        stdout=daemon_log,
        stderr=daemon_log
    )
    username = config.get(('core', 'daemon', 'user'), None)
    group = config.get(('core', 'daemon', 'group'), None)
    if username:
        pw = pwd.getpwnam(username)
        daemon_context.uid = pw.pw_uid
        daemon_context.gid = pw.pw_gid
        os.environ['HOME'] = pw.pw_dir
    if group:
        daemon_context.gid = grp.getgrnam(group).gr_gid
    return daemon_context
