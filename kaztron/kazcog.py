from typing import Type, Dict, TYPE_CHECKING

import logging
from enum import Enum

import discord
from discord.ext import commands

from kaztron.config import KaztronConfig, ConfigModel, ConfigRoot
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
    :param config_section_view: A custom SectionView for this cog's config section. This is
        provided so you can specify a subclass that has type hinting, converters, defaults, etc.
        configured, which simplifies using the configuration and helps IDE autocompletion.
    :param state_section_view: Same as ``config_section_view``, but for `self.state`.
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
        self._status = CogStatus.NONE  # type: CogStatus

        # config stuff
        self._section = None  # type: str
        self._config = None  # type: SectionView
        self._state = None  # type: SectionView
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
            self.bot.state.cfg_register_model(self._section, state_model)
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
    def cog_state(self) -> ConfigRoot:
        """
        The custom state file set up by :meth:`~.setup_cog_state`. If not set up, returns None.

        The custom state file can be accessed with :attr:`~.cog_state`. It is a full
        :cls:`ConfigRoot` object model for the config file, which supports custom-defined ORM-
        style class definitions for its contents.
        """
        return self._cog_state.root

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

    @commands.Cog.listener('on_connect')
    async def on_connect_set_status(self):
        """ Resets the status to INIT (see #316, #317) and clear config converter caches. """
        self._status = CogStatus.INIT
        if self.config:
            self.config.clear_cache()
        if self.state:
            self.state.clear_cache()

    @commands.Cog.listener('on_ready')
    async def _on_ready_init(self):
        try:
            self._on_ready_validate_config_converters()
            await self.on_ready_validate()
        except Exception as e:
            self._status = CogStatus.ERR_READY
            logger.exception("Error in on_ready event: validation error")
            await self.bot.channel_out.send("[ERROR] Error loading cog {}: {}".format(
                self.qualified_name, logutils.exc_msg_str(e)
            ))
            raise
        else:
            self._status = CogStatus.READY
            logger.info(f"Cog ready: {self.qualified_name}")
        finally:
            self.bot.notify_cog_ready(self)

    def _on_ready_validate_config_converters(self):
        for key in self.config.converter_keys():
            self.config.get(key)
        for key in self.state.converter_keys():
            self.state.get(key)
        logger.debug("Configuration converters validated.")

    async def on_ready_validate(self):
        """
        This method does any needed initialisation and validation of the cog at ``on_ready`` time.
        It should be overridden by subclasses needing to do such validation.

        If init/validation fails, this method must raise an exception. This signals to the cog to
        remain in a disabled state.

        In the case that initialisation steps need to be taken at ``on_ready`` time and failure of
        these steps is unlikely or doesn't need for the cog to remain disabled, it may be preferable
        to define an ``on_ready`` listener instead.

        KazCog will, by default, always FIRST test :attr:`config` and :attr:`state` converters as a
        means of validating configuration, and consider validation to have failed if a converter
        raises an error. It is not necessary to test these in the subclass. However, other
        validation of the config/state may be performed. For this validation to work, converters
        must be set BEFORE ``on_ready`` (e.g. in ``__init__()`` or ``on_connect``.
        """
        pass

    @commands.Cog.listener('on_disconnect')
    async def on_disconnect_cleanup_cog_state(self):
        if self.cog_state:
            self.cog_state.write()
        self._status = CogStatus.SHUTDOWN

    @commands.Cog.listener('on_command_completion')
    async def on_command_completion_save_cog_state(self, _: commands.Context):
        """ On command completion, save cog-local state file. """
        if self.cog_state:
            self.cog_state.write()

    async def cog_before_invoke(self, ctx: commands.Context):
        """
        Cog-local pre-invoke hook. This base implementation logs all commands.

        :param ctx: Context.
        """
        self._cmd_logger.info("{!s}: {}".format(self, logutils.message_log_str(ctx.message)))

    def export_kazhelp_vars(self) -> Dict[str, str]:
        """
        Can be overridden to make dynamic help variables available for structured help ("!kazhelp").
        Returns a dict mapping variable name to values.

        Variable names must start with a character in the set [A-Za-z0-9_].

        Variable values must be strings.

        :return: variable name -> value
        """
        return {}
