from typing import Union, Optional, Dict

import logging
import random
import datetime

import discord
from discord.ext import commands

import kaztron
from kaztron.core_config import *
from kaztron.kazcog import KazCog
from kaztron.errors import *
from kaztron import config as cfg
# from kaztron.help_formatter import CoreHelpParser, DiscordHelpFormatter
from kaztron.scheduler import Scheduler, task

from kaztron.utils.decorators import task_handled_errors

logger = logging.getLogger("kazclient")
KaztronConfig = cfg.KaztronConfig

AnyChannel = Union[discord.TextChannel,     discord.VoiceChannel, discord.DMChannel,
                   discord.CategoryChannel, discord.StoreChannel, discord.GroupChannel]


class KazClient(commands.Bot):
    """
    KazTron bot instance. This is a subclass of :cls:`commands.Bot` and thus :cls:`discord.Client`,
    and can do everything those classes can do. It further implements core features specific to
    KazTron.
    """

    def __init__(self, *args, config: KaztronConfig, client_state: KaztronConfig, **kwargs):
        """ Create the client. Takes the same keyword args as :cls:`commands.Bot` and
         :cls:`discord.Client`, in addition to those described below. """

        self._config = config
        self._state = client_state
        self._guild = None

        if 'description' not in kwargs:
            # don't use ConfigModel yet
            kwargs['description'] = self.config.get(('core', 'description'))
        super().__init__(*args, **kwargs)

        self._is_first_load = True
        self._startup_time = datetime.datetime.utcnow()

        self.add_check(self._command_check_ready)

        self._scheduler = Scheduler(self)

        # self.kaz_help_parser = CoreHelpParser({
        #     'name': self.config.core.get('name')
        # })

        self.setup_config_attributes(self._config)
        self.setup_config_attributes(self._state)
        self._config.root.cfg_register_model('core', CoreConfig, lazy=False)
        self._config.root.cfg_register_model('logging', Logging, lazy=True)

    @property
    def config(self):
        """ Global client read-only configuration. """
        return self._config

    @property
    def core_config(self) -> CoreConfig:
        """ Core bot configuration. """
        return self._config.root.core

    @property
    def state(self):
        """ Global client state and dynamically writable configurations. """
        return self._state

    @property
    def core_cog(self):
        """ Shortcut to access the core KazTron cog. """
        from kaztron.core import CoreCog  # for type annotation/IDE inference
        return self.get_cog('CoreCog')  # type: CoreCog

    @property
    def scheduler(self):
        """ Bot's task scheduler. """
        return self._scheduler

    @property
    def rolemanager(self):
        """ Shortcut to access the Role Manager KazTron cog, a core cog. """
        from kaztron.rolemanager import RoleManager  # for type annotation/IDE inference
        return self.get_cog('RoleManager')  # type: RoleManager

    @property
    def channel_out(self) -> discord.TextChannel:
        """ Configured output channel. If not :meth:`~.is_ready`, returns None. """
        return self.core_config.discord.channel_output

    @property
    def channel_public(self) -> discord.TextChannel:
        """ Configured public output channel. If not :meth:`~.is_ready`, returns None. """
        return self.core_config.discord.channel_public

    @property
    def channel_test(self) -> discord.TextChannel:
        """ Configured test channel. If not :meth:`~.is_ready`, returns None. """
        return self.core_config.discord.channel_test

    @property
    def guild(self) -> Optional[discord.Guild]:
        """
        Convenience property to access the bot's primary guild. Kaztron is designed as a single-
        guild bot and does not generally operate well on multiple guilds. If not :meth:`~.is_ready`,
        returns None. """
        return self._guild

    @property
    def uptime(self) -> datetime.timedelta:
        return datetime.datetime.utcnow() - self._startup_time

    async def on_connect(self):
        if self._is_first_load:
            logger.info("*** CONNECTED TO DISCORD.")
            self._startup_time = datetime.datetime.utcnow()
        else:
            logger.info("*** RECONNECTED.")

    async def on_disconnect(self):
        self.state.write(True)
        self._guild = None
        logger.info("*** Disconnected.")

    async def on_ready(self):
        self.core_config.clear_cache()
        self._guild = self.channel_out.guild
        # TODO: help
        # set global variables for help parser
        # self.kaz_help_parser.variables['output_channel'] = '#' + self.channel_out.name
        # self.kaz_help_parser.variables['test_channel'] = '#' + self.channel_test.name
        # self.kaz_help_parser.variables['public_channel'] = '#' + self.channel_public.name

    async def _on_cogs_ready(self):
        """ Called when all cogs are ready. Logs and sends startup messages. """
        interval = self.core_config.discord.status_change_interval
        if interval.total_seconds() == 0:
            interval = None
        for task in self.scheduler.get_instances(self.task_change_status_message):
            self.scheduler.cancel_task(task)
            await task.wait()
        self.scheduler.schedule_task_in(self.task_change_status_message, in_time=0, every=interval)
        await self._send_startup_messages()

    async def _send_startup_messages(self):
        if len(self.cogs_error) == 0:
            logger.info("=== ALL COGS READY ===")
        else:
            logger.error(f"=== COG READY ERRORS: {len(self.cogs_error):d} ===")

        if self._is_first_load:
            logger.info(f"*** Bot {self.core_config.name} is now ready.")
            logger.info(f"*** Running KazTron v{kaztron.__version__} "
            f"| discord.py v{discord.__version__}")
            logger.info(f"*** Logged in as {self.user.name} <{self.user.id}>")

        try:
            if self._is_first_load:
                await self.channel_out.send(
                    rf"**\*\*\* Bot {self.config.root.core.name} (KazTron v{kaztron.__version__}) "
                    rf"is running.**"
                )
            else:
                await self.channel_out.send(r"**\*\*\* Reconnected.**")
        except discord.HTTPException:
            logger.exception("Error sending startup message to output channel.")

        self._is_first_load = False

    @task(is_unique=True)
    async def task_change_status_message(self):
        if self.core_config.discord.status:
            activity_data = random.choice(self.core_config.discord.status)
            logger.info(f"Setting status to '{activity_data.name}'")
            await self.change_presence(activity=discord.Game(name=activity_data.name))
        else:  # clear the "starting up" message
            logger.info("No statuses set: clearing startup status")
            await self.change_presence(activity=None)

    def all_cogs_ready(self):
        """ Check if all cogs have had on_ready executed (even if they errored). """
        for cog in self.cogs_kaz.values():
            if not (cog.is_ready or cog.is_error):
                return False
        return True

    def notify_cog_ready(self, cog: KazCog):
        """
        Called by a cog to notify this client that a cog's on_ready() has executed (even if an error
        occurred).

        Check if all cogs are ready, and if so, execute post-ready tasks.
        """
        if self.all_cogs_ready():
            self.loop.create_task(self._on_cogs_ready())

    @property
    def cogs_kaz(self) -> Dict[str, KazCog]:
        """ Get all loaded KazCogs. """
        return {name: cog for name, cog in self.cogs.items() if isinstance(cog, KazCog)}

    @property
    def cogs_std(self) -> Dict[str, commands.Cog]:
        """
        Get all loaded standard (non-KazCog) cogs. Specific status information is not available
        for these cogs.
        """
        return {name: cog for name, cog in self.cogs.items() if not isinstance(cog, KazCog)}

    @property
    def cogs_ready(self) -> Dict[str, KazCog]:
        """ Get all KazCogs that are ready and not in error state. """
        return {name: cog for name, cog in self.cogs_kaz.items() if cog.is_ready}

    @property
    def cogs_error(self) -> Dict[str, KazCog]:
        """ Get all KazCogs in error state. """
        return {name: cog for name, cog in self.cogs_kaz.items() if cog.is_error}

    @property
    def cogs_not_ready(self) -> Dict[str, KazCog]:
        """ Get all KazCogs that are not yet ready (or somehow failed without error?). """
        return {name: cog for name, cog in self.cogs_kaz.items()
                if not (cog.is_ready or cog.is_error)}

    async def on_command_completion(self, ctx: commands.Context):
        """ On command completion, save state files. """
        self.state.write(False)

    async def _command_check_ready(self, ctx: commands.Context):
        """ Check if cog is ready. Used as a global check for every command. """
        if isinstance(ctx.cog, KazCog):
            if ctx.cog.is_ready:
                return True
            elif ctx.cog.is_error:
                raise BotCogError(ctx.cog.qualified_name)
            else:
                raise BotNotReady(ctx.cog.qualified_name)
        else:
            return True

    def validate_channel(self, x: Union[int, str]) -> AnyChannel:
        """
        Get a channel by name or ID.

        Similar to :meth:`discord.Client.get_channel`, but raises ValueError if not found.
        :deprecated: 3.0.0
        """
        if isinstance(x, int):
            ch = self.guild.get_channel(x)
        else:
            ch = discord.utils.get(self.guild.channels, name=x)
        if ch is None:
            raise ValueError("Channel {} not found".format(x if isinstance(x, int) else f"'#{x}'"))
        return ch

    def validate_role(self, x: Union[int, str]) -> discord.Role:
        """
        Get a role by name or ID.

        Similar to :meth:`discord.Client.get_role`, but raises ValueError if not found.
        :deprecated: 3.0.0
        """
        if isinstance(x, int):
            role = self.guild.get_role(x)
        else:
            role = discord.utils.get(self.guild.roles, name=x)
        if role is None:
            raise ValueError("Role {} not found".format(x if isinstance(x, int) else f"'{x}'"))
        return role

    def setup_config_attributes(self, config: 'KaztronConfig'):
        """
        Set up any attributes the config system needs at runtime. This is automatically called
        for the default config files (read-only config and state), but should be called on any
        new config files created by the bot which use Discord-related Field types.
        """
        from kaztron.config import DiscordModelField
        config.root.cfg_set_runtime_attributes(DiscordModelField, client=self)

    @task_handled_errors
    async def _parse_help(self):
        return  # TODO: help system
        obj_list = set()
        formatter = self.formatter  # type: DiscordHelpFormatter

        for cog_name, cog in self.cogs.items():
            if cog not in obj_list:
                try:
                    formatter.kaz_preprocess(cog, self.bot)
                    obj_list.add(cog)
                except Exception as e:
                    raise discord.ClientException(
                        "Error while parsing !kazhelp for cog {}".format(cog_name)) \
                        from e

        for command in self.walk_commands():
            if command not in obj_list:
                try:
                    formatter.kaz_preprocess(command, self.bot)
                    obj_list.add(command)
                except Exception as e:
                    raise discord.ClientException("Error while parsing !kazhelp for command {}"
                        .format(command.qualified_name)) from e

        logger.info("=== KAZHELP PROCESSED ===")
