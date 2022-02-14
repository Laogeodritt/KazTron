import functools
from typing import Type, Dict, List, Tuple, Optional, TYPE_CHECKING

import logging
from enum import Enum

import discord
from discord.ext import commands

from kaztron.config import KaztronConfig, ConfigModel, ConfigRoot
from kaztron.errors import BotNotReady
from kaztron.utils import logging as logutils

if TYPE_CHECKING:
    from kaztron import KazClient

logger = logging.getLogger(__name__)


class CogStatus(Enum):
    INIT = 0
    READY = 1
    SHUTDOWN = 2
    ERR_READY = -1


class KazCog(commands.Cog):
    """
    Base class for KazTron. Provides convenience access to various core structures like
    configuration, as well as some bot state control.

    CoreCog installs a global check that only allows commands once on_ready has been called for
    that cog. However, in event handlers like on_message(), this check is not automatically handled:
    you can either use the :meth:`ready_only()` decorator or call :meth:`~.is_ready()`.

    :param bot: The discord bot instance that this cog is attached to.
    :param config_section_name: The name of this cog's config section. Should be a valid Python
        identifier. Optional but recommended: if this is not specified, the `self.config` and
        `self.state` convenience properties will not be available.
    :param config_model: The ConfigModel class for this cog's configuration.
    :param state_model: Same as ``config_model``, but for `self.state`.
    """

    def __init__(self,
                 bot: 'KazClient',
                 config_section_name: str = None,
                 config_model: Type[ConfigModel] = None,
                 state_model: Type[ConfigModel] = None):
        # dependencies
        self._bot = bot
        self._cmd_logger = logging.getLogger("kaztron.commands")

        # state variables
        self._status = CogStatus.INIT  # type: CogStatus

        # config stuff
        self._section = None  # type: str
        self._config = None  # type: ConfigModel
        self._state = None  # type: ConfigModel
        self._cog_state = None  # type: KaztronConfig
        self._setup_config(config_section_name, config_model, state_model)

    def _setup_config(self, section: str,
                      config_model: Type[ConfigModel],
                      state_model: Type[ConfigModel]
                      ):
        self._section = section
        if not self._section:
            return
        if config_model:
            self.bot.config.root.cfg_register_model(self._section, config_model)
        if state_model:
            self.bot.state.root.cfg_register_model(self._section, state_model)
        self._config = self.bot.config.root.get(self._section)
        self._state = self.bot.state.root.get(self._section)

    @property
    def bot(self) -> 'KazClient':
        """ The bot/client instance this cog belongs to. """
        return self._bot

    @property
    def config(self) -> ConfigModel:
        """
        The read-only user configuration for this cog. For the bot-wide config, use
        `self.bot.config` (see :attr:`KazClient.config`).
        """
        return self._config

    @property
    def state(self) -> ConfigModel:
        """
        The read/write bot state for this cog. This is always a section in the bot-wide state file.
        See also :attr:`~.cog_state` for the custom state file set up by :meth:`~.setup_cog_state`.

        If you want to access the  bot-wide state file, use `self.bot.state`
        (see :attr:`KazClient.state`).
        """
        return self._state

    @property
    def cog_state(self) -> Optional[ConfigRoot]:
        """
        The custom state file set up by :meth:`~.setup_cog_state`. If not set up, returns None.

        The custom state file can be accessed with :attr:`~.cog_state`. It is a full
        :cls:`ConfigRoot` object model for the config file, which supports custom-defined ORM-
        style class definitions for its contents.
        """
        try:
            return self._cog_state.root
        except AttributeError:
            return None

    def setup_cog_state(self, name, defaults=None):
        """
        Set up a custom state file for this cog.

        The name specified MUST BE UNIQUE BOT-WIDE. Otherwise, concurrency issues will occur as
        multiple KaztronConfig instances cannot own a single file.

        The custom state file can be accessed with :attr:`~.cog_state`. It is a full
        :cls:`ConfigRoot` object model for the config file, which supports custom-defined ORM-
        style class definitions for its contents.

        :param name: A simple alphanumeric name, to be used as part of the filename.
        :param defaults: Defaults for this state file, as taken by the :cls:`KaztronConfig`
            constructor.
        """
        self._cog_state = KaztronConfig('state-' + name + '.json', defaults)
        self.bot.setup_config_attributes(self._cog_state)

    @property
    def status(self):
        """ Current cog readiness status. """
        return self._status

    @property
    def is_ready(self):
        """
        Check if the cog is ready. This may not have the same value as `self.bot.is_ready()`,
        depending on whether this cog's on_ready event has been called yet, and whether it succeeded
        or raised an exception.
        """
        return self._status == CogStatus.READY

    @property
    def is_error(self):
        """ Check if the cog encountered an error while processing the ``on_ready`` event. """
        return self._status == CogStatus.ERR_READY

    @classmethod
    def listener(cls, name=None, ready_only=None):
        """A decorator that marks a function as a listener.

        This is the cog equivalent of :meth:`.Bot.listen`.

        :param name: The name of the event being listened to. If not provided, it defaults to the
        function's name.
        :param ready_only: If True, will only run when the cog is ready. If False, will run no
        matter the current cog state. If not specified, default is True for most events. For events
        on_connect, on_shard_connect, on_disconnect, on_shard_disconnect, on_ready, on_shard_ready,
        on_resumed, on_shard_resumed, on_error, default is False.
        :raises TypeError: The function is not a coroutine function or a string was not passed as
        the name.
        """

        # KazCog.listener() adds two features:
        # - An on_ready check, which can be enabled/disabled explicitly or auto-enabled depending
        #   on the event type.
        # - Capture of on_ready and on_resume events to ensure that errors raised will be reflected
        #   in the cog's lifecycle status.

        parent_listener = super().listener(name)
        ready_only_decorator = cls._ready_only_event(autodetect=(ready_only is None))
        ready_patch = cls._patch_on_ready_events

        if ready_only or ready_only is None:
            return lambda f: ready_patch(ready_only_decorator(parent_listener(f)))
        else:  # not a ready_only event
            return parent_listener

    @classmethod
    def _ready_only_event(cls, autodetect):
        """
        Decorator to filter event listener based on whether the cog is ready.
        :param autodetect: If True, will check the event name to determine whether the event should
            be filtered by cog readiness or not.
        """

        def autodetect_ready_only(func):
            NON_READY_EVENTS = ("on_connect", "on_shard_connect",
                                "on_disconnect", "on_shard_disconnect",
                                "on_ready", "on_shard_ready",
                                "on_resumed", "on_shard_resumed",
                                "on_error")
            # check if we need to unwrap a staticmethod - see discord.Cog.listener()
            if isinstance(func, staticmethod):
                func = func.__func__

            # now check the registered listener names for non-ready-only event names
            for listener_name in func.__cog_listener_names__:
                if listener_name in NON_READY_EVENTS:
                    return False
            else:
                return True

        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                if not args[0].is_ready:
                    raise BotNotReady(type(args[0]).__name__)
                return await func(*args, **kwargs)
            if (not autodetect) or (autodetect and autodetect_ready_only(func)):
                return wrapper
            else:
                return func
        return decorator

    @classmethod
    def _patch_on_ready_events(cls, func):
        """
        Removes on_ready/on_resume events from the listener list and registers them separately for
        KazCog-specific lifecycle management. This method must run BEFORE the discord.py Cog
        metaclass's __new__ method runs. Effectively, this means it is best applied as a decorator.
        """
        actual_func = func
        if isinstance(func, staticmethod):
            actual_func = func.__func__
        if actual_func.__cog_listener__:
            for event_name in ('on_ready', 'on_resume'):
                if event_name in actual_func.__cog_listener_names__:
                    try:
                        actual_func.__kazcog_listener_names__.append(event_name)
                    except AttributeError:
                        actual_func.__kazcog_listener_names__ = [event_name]
                    actual_func.__cog_listener_names__.remove(event_name)
        return func

    @commands.Cog.listener('on_connect')
    async def on_connect_set_status(self):
        """ Resets the status to INIT (see #316, #317). """
        self._status = CogStatus.INIT

    @commands.Cog.listener('on_ready')
    async def _on_ready_init(self):
        await self._on_ready_init_inner('on_ready')

    @commands.Cog.listener('on_resume')
    async def _on_resume_init(self):
        await self._on_ready_init_inner('on_resume')

    async def _on_ready_init_inner(self, event: str):
        logger.debug(event)
        try:
            self._on_ready_validate_config()
            for attr_name in dir(self):  # find and execute any on_ready/on_resume events in cog
                if attr_name.startswith('__') or attr_name.endswith('__'):
                    continue
                func = getattr(self, attr_name)
                if not callable(func) or not hasattr(func, '__kazcog_listener_names__'):
                    continue
                if event in func.__kazcog_listener_names__:
                    await func()
        except Exception:
            self._status = CogStatus.ERR_READY
            await self.bot.channel_out.send(
                f"[ERROR] Cog {self.qualified_name} failed to load ({event})")
            # no logger: error handler will handler that part
            raise
        else:
            self._status = CogStatus.READY
            logger.info(f"Cog ready: {self.qualified_name}")
        finally:
            self.bot.notify_cog_ready(self)

    def _on_ready_validate_config(self):
        # clear_cache() also re-converts non-lazy keys, providing a first layer of validation
        if self.config:
            logger.debug(f"{self.qualified_name}: clearing config cache...")
            self.config.clear_cache()
        if self.state:
            logger.debug(f"{self.qualified_name}: clearing config-state cache...")
            self.state.clear_cache()

    @commands.Cog.listener('on_disconnect')
    async def on_disconnect_cleanup_cog_state(self):
        if self.cog_state:
            self.cog_state.cfg_write()
        self._status = CogStatus.SHUTDOWN

    @commands.Cog.listener('on_command_completion')
    async def on_command_completion_save_cog_state(self, _: commands.Context):
        """ On command completion, save cog-local state file. """
        if self.cog_state:
            self.cog_state.cfg_write()

    async def cog_before_invoke(self, ctx: commands.Context):
        """
        Cog-local pre-invoke hook. This base implementation logs all commands. Can be overridden.

        :param ctx: Context.
        """
        self._cmd_logger.info(f"{self.qualified_name}: {logutils.message_log_str(ctx.message)}")

    def export_kazhelp_vars(self) -> Dict[str, str]:
        """
        Can be overridden to make dynamic help variables available for structured help ("!kazhelp").
        Returns a dict mapping variable name to values.

        Variable names must start with a character in the set [A-Za-z0-9_].

        Variable values must be strings.

        :return: variable name -> value
        """
        return {}
