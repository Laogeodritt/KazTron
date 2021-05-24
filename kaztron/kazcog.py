from asyncio import iscoroutine
from typing import Type, Dict, Union, Sequence, Callable, Any

import functools
import logging
from enum import Enum

import discord
from discord.ext import commands

from kaztron import KazClient
from kaztron.config import KaztronConfig, SectionView
from kaztron.utils.discord import Limits
from kaztron.utils.embeds import EmbedSplitter
from kaztron.utils import logging as logutils

from kaztron.utils import cogutils

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
                 bot: KazClient,
                 config_section_name: str = None,
                 config_section_view: Type[SectionView] = None,
                 state_section_view: Type[SectionView] = None):
        self._bot = bot
        self._section = None  # type: str
        self._config = None  # type: SectionView
        self._state = None  # type: SectionView
        self._cogstate = None  # type: KaztronConfig
        self._setup_config(config_section_name, config_section_view, state_section_view)

        self._status = CogStatus.NONE  # type: CogStatus

        self._cmd_logger = logging.getLogger("kaztron.commands")

        # wrappers allow for cogs to define event handlers without calling super().on_*()
        self.__wrap_event('connect', self._on_connect_wrapper)
        self.__wrap_event('ready', self._on_ready_wrapper)
        self.bot.before_invoke(self._before_invoke_log_command)
        self.__wrap_event('command_completion', self._on_command_completion_wrapper)
        self.__wrap_event('disconnect', self._on_disconnect_wrapper)

    def _setup_config(self,
                      section: str,
                      config_view: Type[SectionView] = None,
                      state_view: Type[SectionView] = None
                      ):
        self._section = section
        if not self._section:
            return
        if config_view:
            self.bot.config.set_section_view(self._section, config_view)
        if state_view:
            self.bot.state.set_section_view(self._section, state_view)
        self._config = self.bot.config.get_section(self._section)
        self._state = self.bot.state.get_section(self._section)

    @property
    def bot(self) -> KazClient:
        """ The bot/client instance this cog belongs to. """
        return self._bot

    @property
    def config(self) -> SectionView:
        """
        The read-only user configuration for this cog. For the bot-wide config, use
        `self.bot.config` (see :attr:`KazClient.config`).
        """
        return self._config

    @property
    def state(self) -> SectionView:
        """
        The read/write bot state for this cog. This is always a section in the bot-wide state file.
        See also :attr:`~.cogstate` for the custom state file set up by :meth:`~.setup_cogstate`.

        If you want to access the  bot-wide state file, use `self.bot.state`
        (see :attr:`KazClient.state`).
        """
        return self._state

    @property
    def cogstate(self) -> KaztronConfig:
        """
        The custom state file set up by :meth:`~.setup_cogstate`. If not set up, returns None.
        """
        return self._cogstate

    def setup_cogstate(self, name, defaults=None):
        """
        Set up a custom state file for this cog.

        The name specified MUST BE UNIQUE BOT-WIDE. Otherwise, concurrency issues will occur as
        multiple KaztronConfig instances cannot own a single file.

        The custom state file can be accessed with :attr:`~.cogstate`. It is a full KaztronConfig
        instance. If you'd like to set up your own SectionView objects for the sections in this
        file, you can call :meth:`KaztronConfig.set_section_view`.

        :param name: A simple alphanumeric name, to be used as part of the filename.
        :param defaults: Defaults for this state file, as taken by the :cls:`KaztronConfig`
            constructor.
        """
        self._cogstate = KaztronConfig('state-' + name + '.json', defaults)

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

    async def __wrap_event(self, event: str, wrapper: Callable):
        event_meth = 'on_' + event
        try:
            functools.update_wrapper(wrapper, getattr(self, event_meth))
            setattr(self, event_meth, functools.partial(wrapper, getattr(self, event_meth)))
        except AttributeError:
            def noop(*_, **__):
                pass
            setattr(self, event_meth, functools.partial(wrapper, noop))

    async def _on_connect_wrapper(self, f: Callable):
        """ Wrapper for 'connect' events. Resets the status to INIT. See #316, #317. """
        await f()
        self._status = CogStatus.INIT

    async def _on_ready_wrapper(self, f: Callable):
        """
        Wrapper for 'ready' event. Clears KaztronConfig caches, wraps the cog's on_ready with
         exception handling, and notifies bot
        """
        logger.debug(f"{self.qualified_name}: on_ready")
        if self.config:
            self.config.clear_cache()
        if self.state:
            self.state.clear_cache()

        try:
            await f()
        except Exception:
            self._status = CogStatus.ERR_READY
            logger.error(f"Cog error in 'on_ready' event: {self.qualified_name}")
            await self.bot.channel_out.send(
                f"[ERROR] Cog error in `on_ready()` event: {self.qualified_name}"
            )
            raise
        else:
            self._status = CogStatus.READY
            logger.info(f"Cog ready: {self.qualified_name}")
        finally:
            self.bot.notify_cog_ready(self)

    async def _on_disconnect_wrapper(self, f: Callable):
        if self.cogstate:
            self.cogstate.write(True)

        try:
            await f()
        finally:
            self._status = CogStatus.SHUTDOWN

    async def _before_invoke_log_command(self, ctx: commands.Context):
        self._cmd_logger.info("{!s}: {}".format(self, logutils.message_log_str(ctx.message)))

    async def _on_command_completion_wrapper(self, f: Callable, ctx: commands.Context):
        """ On command completion, save state files. """
        try:
            await f(ctx)
        finally:
            if self.cogstate:
                self.cogstate.write(False)

    def export_kazhelp_vars(self) -> Dict[str, str]:
        """
        Can be overridden to make dynamic help variables available for structured help ("!kazhelp").
        Returns a dict mapping variable name to values.

        Variable names must start with a character in the set [A-Za-z0-9_].

        Variable values must be strings.

        :return: variable name -> value
        """
        return {}

    async def send_message(self, destination, contents=None, *, tts=False,
                           embed: Union[discord.Embed, EmbedSplitter] = None,
                           auto_split=True, split='word') -> Sequence[discord.Message]:
        """
        Send a message. This method wraps the :meth:`discord.Client.send_message` method and adds
        automatic message splitting if a message is too long for one line.

        No parsing of Markdown is done for message splitting; this behaviour may break intended
        formatting. For messages which may contain formatting, it is suggested you parse and split
        the message instead of relying on auto-splitting.

        See also :meth:`kaztron.utils.split_chunks_on` and :meth:`kaztron.utils.natural_split` for
        manual control of splitting behaviour. See also :meth:`kaztron.utils.split_code_chunks_on`
        for splitting Markdown code blocks manually.

        See also :cls:`kaztron.utils.embeds.EmbedSplitter` for similar functionality in splitting
        embeds.

        :param destination: he location to send the message (Channel, PrivateChannel, User, etc.)
        :param contents: The content of the message to send. If this is missing, then the ``embed``
            parameter must be present.
        :param tts: Indicates if the message should be sent using text-to-speech.
        :param embed: The rich embed for the content. Also accepts EmbedSplitter instances, for
            automatic splitting - in this case, the EmbedSplitter will be finalized by this method.
        :param auto_split: Whether to auto-split messages that exceed the maximum message length.
        :param split: What to split on: 'word' or 'line'. 'Line' should only be used for messages
            known to contain many line breaks, as otherwise auto-splitting is likely to fail.
        """

        # prepare text contents
        if not contents or not auto_split:
            content_chunks = (contents,)
        else:
            if split == 'word':
                content_chunks = cogutils.strutils.natural_split(contents, Limits.MESSAGE)
            elif split == 'line':
                content_chunks = cogutils.strutils.split_chunks_on(
                    contents, Limits.MESSAGE, split_char='\n')
            else:
                raise ValueError('`split` argument must be \'word\' or \'line\'')

        # prepare embed
        try:
            embed_list = embed.finalize()
        except AttributeError:
            embed_list = (embed,)

        # strategy: output all text chunks before starting to output embed chunks
        # so the last text chunk will have the first embed chunk attached
        # this is because non-split messages usually have the embed appear after the msg -
        # should be fairly rare for both msg and embed to be split
        msg_list = []
        for content_chunk in content_chunks[:-1]:
            msg_list.append(await self.bot.send_message(destination, content_chunk, tts=tts))

        msg_list.append(await self.bot.send_message(
            destination, content_chunks[-1], tts=tts, embed=embed_list[0]
        ))

        for embed_chunk in embed_list[1:]:
            msg_list.append(await self.bot.send_message(destination, tts=tts, embed=embed_chunk))
        return tuple(msg_list)
