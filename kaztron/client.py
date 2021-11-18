from typing import Union, Optional, List, Dict

import logging
import random
from datetime import timedelta

import discord
from discord.ext import commands

import kaztron
from kaztron.kazcog import KazCog
from kaztron.errors import *
from kaztron import config as cfg
# from kaztron.help_formatter import CoreHelpParser, DiscordHelpFormatter
from kaztron.scheduler import Scheduler, task

from kaztron.utils.decorators import task_handled_errors
from kaztron.utils.discord import Limits

logger = logging.getLogger("kazclient")
KaztronConfig = cfg.KaztronConfig

AnyChannel = Union[discord.TextChannel,     discord.VoiceChannel, discord.DMChannel,
                   discord.CategoryChannel, discord.StoreChannel, discord.GroupChannel]


class InfoLink(cfg.ConfigModel):
    name: str = cfg.StringField(required=True, len=Limits.EMBED_FIELD_NAME)
    url: str = cfg.StringField(required=True, len=Limits.EMBED_FIELD_VALUE - 16)


class BotStatus(cfg.ConfigModel):
    name: str = cfg.StringField(required=True, len=Limits.STATUS)
    emoji = cfg.PrimitiveField(required=False)  # TODO: emoji model?


class CoreFormats(cfg.ConfigModel):
    date: str = cfg.StringField(default="%Y-%m-%d")
    datetime: str = cfg.StringField(default="%Y-%m-%d %H:%M")
    datetime_seconds: str = cfg.StringField(default="%Y-%m-%d %H:%M:%S")


class CoreDaemon(cfg.ConfigModel):
    enabled: bool = cfg.BooleanField(default=False)
    pidfile: str = cfg.StringField(default="pid.lock")
    user: str = cfg.StringField()
    group: str = cfg.StringField()
    log: str = cfg.StringField(default="daemon.log")


class CoreDiscord(cfg.ConfigModel):
    token: str = cfg.StringField(required=True)
    channel_output: discord.TextChannel = cfg.TextChannelField(required=True)
    channel_public: discord.TextChannel = cfg.TextChannelField(required=True)
    channel_issues: discord.TextChannel = cfg.TextChannelField(required=True)
    mod_roles: List[discord.Role] = cfg.ListField(type=cfg.RoleField(), default=[])
    admin_roles: List[discord.Role] = cfg.ListField(type=cfg.RoleField(), default=[])
    mod_channels: List[discord.TextChannel] = cfg.ListField(type=cfg.TextChannelField())
    admin_channels: List[discord.TextChannel] = cfg.ListField(type=cfg.TextChannelField())
    status: List[BotStatus] = cfg.ListField(type=cfg.ConfigModelField(type=BotStatus), default=[])
    status_change_interval: timedelta = cfg.TimeDeltaField(default=timedelta(seconds=0))


class CoreConfig(cfg.ConfigModel):
    name: str = cfg.StringField(required=True)
    description: str = cfg.StringField(default=None)
    data_dir: str = cfg.StringField(default='.')  # TODO: IMPLEMENT ME
    # TODO: merge the kaztron.__init__ defaults
    info_links: List[InfoLink] = cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])
    formats: CoreFormats = cfg.ConfigModelField(type=CoreFormats)  # TODO: CHECK THIS IS READ CORRECTLY (utils?)
    daemon: CoreDaemon = cfg.ConfigModelField(type=CoreDaemon)
    discord: CoreDiscord = cfg.ConfigModelField(type=CoreDiscord)


class Logging(cfg.ConfigModel): # TODO: CHECK THAT THIS IS PROPERLY SET UP
    file: str = cfg.StringField(default="kaztron.log")
    level: str = cfg.StringField(default="INFO")  # TODO: enum?
    max_size_kb: int = cfg.IntegerField(default=0)
    max_backups: int = cfg.IntegerField(default=0)
    tags: Dict[str, str] = cfg.DictField(type=cfg.StringField(),  # TODO: enum?
        default={
            "discord": "INFO",
            "websockets.protocol": "INFO",
            "kaztron.config": "INFO",
            "kaztron.help_formatter": "INFO",
            "sqlalchemy.engine": "WARNING",
            "asyncprawcore": "INFO"
        })


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

        if 'description' not in kwargs:
            # don't use ConfigModel yet
            kwargs['description'] = self.config.get(('core', 'description'))
        super().__init__(*args, **kwargs)

        self._is_first_load = True

        self.add_check(self._command_check_ready)

        self._scheduler = Scheduler(self)

        # self.kaz_help_parser = CoreHelpParser({
        #     'name': self.config.core.get('name')
        # })

        self.setup_config_attributes(self._config)
        self.setup_config_attributes(self._state)
        self._config.root.cfg_register_model('core', CoreConfig)
        self._config.root.cfg_register_model('logging', Logging)

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
        try:
            return self.channel_out.guild
        except AttributeError:  # not yet ready
            return None

    async def on_connect(self):
        if self._is_first_load:
            logger.info("*** CONNECTED TO DISCORD.")
        else:
            logger.info("*** RECONNECTED.")

    async def on_disconnect(self):
        self.state.write(True)
        logger.info("*** Disconnected.")

    async def on_ready(self):
        pass
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
        self.scheduler.schedule_task_in(self.task_change_status_message, in_time=0, every=interval)
        await self._send_startup_messages()

    async def _send_startup_messages(self):
        cog_errors = sum(1 for c in self.cogs.values() if c.is_error)
        if cog_errors == 0:
            logger.info("=== ALL COGS READY ===")
        else:
            logger.error(f"=== COG READY ERRORS: {cog_errors:d} ===")

        if self._is_first_load:
            logger.info(f"*** Bot {self.core_config.name} is now ready.")
            logger.info(f"*** Running KazTron v{kaztron.__version__} "
            f"| discord.py v{discord.__version__}")
            logger.info(f"*** Logged in as {self.user.name} <{self.user.id}>")

        try:
            if self._is_first_load:
                await self.channel_out.send(
                    rf"**\*\*\* Bot {self.config.core.name} (KazTron v{kaztron.__version__}) "
                    rf"is running.**"
                )
            else:
                await self.channel_out.send(r"**\*\*\*Reconnected.**")
        except discord.HTTPException:
            logger.exception("Error sending startup message to output channel.")

        self._is_first_load = False

    @task(is_unique=True)
    async def task_change_status_message(self):
        if self.core_config.discord.status:
            activity_data = random.choice(self.core_config.discord.status)
            await self.change_presence(activity=discord.Game(name=activity_data.name))
        else:  # clear the "starting up" message
            await self.change_presence(activity=None)

    def all_cogs_ready(self):
        """ Check if all cogs have had on_ready executed (even if they errored). """
        registered_cogs = {cog for cog in self.cogs.values() if isinstance(cog, KazCog)}
        ready_cogs = {cog for cog in registered_cogs if cog.is_ready or cog.is_error}
        return registered_cogs == ready_cogs

    def notify_cog_ready(self, cog: KazCog):
        """
        Called by a cog to notify this client that a cog's on_ready() has executed (even if an error
        occurred).

        Check if all cogs are so ready, and execute post-ready tasks.
        """
        if self.all_cogs_ready():
            self.loop.create_task(self._on_cogs_ready())

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
