from enum import Enum
import abc
from typing import List, Sequence, Union
from inspect import isawaitable

import functools

import discord
from discord.ext import commands

from kaztron.errors import UnauthorizedUserError, UnauthorizedChannelError, \
    ModOnlyError, AdminOnlyError
from kaztron.utils.discord import get_channel, get_role

import logging

__all__ = ('CheckType', 'Check', 'check_any', 'delete_on_fail', 'delete_message',
           'in_channels', 'mod_channels', 'admin_channels', 'bot_channels', 'dm_only', 'guild_only',
           'has_role', 'mod_only', 'admin_only')
logger = logging.getLogger('kaztron.checks')


ConfigPath = Union[str, Sequence[str]]

ChannelRef = Union[int, str]  # Channel ID or name
ChannelRefList = List[ChannelRef]
ChannelList = List[discord.TextChannel]

RoleRef = Union[int, str]  # Channel ID or name
RoleRefList = List[RoleRef]
RoleList = List[discord.Role]


class CheckType(Enum):
    """
    Identifies the type of check. Used primarily for automatic documentation generation (see
    :mod:`~kaztron.help_formatter`).
    """
    OTHER = 0
    ANY = 1
    U_ROLE = 10
    U_MOD = 11
    U_ADMIN = 12
    C_LIST = 20
    C_MOD = 21
    C_ADMIN = 22
    C_BOT = 23
    C_DM = 24
    C_GUILD = 25


class Check(abc.ABC):
    """
    Base class for KazTron rich checks. These checks contain metadata for auto-documenting the
    checks in help output, as well as other possibilities of inspecting checks on a command.
    """
    def __init__(self, check_type: CheckType, check_data=None):
        self.type = check_type
        self.data = check_data

    @abc.abstractmethod
    def __call__(self, ctx: commands.Context) -> bool:
        raise NotImplementedError()


class CheckAny(Check):
    def __init__(self, *checks):
        self.checks = []
        self.types = set()
        for wrapped in checks:
            try:
                predicate = wrapped.predicate
            except AttributeError:
                raise TypeError(f'{wrapped} must be wrapped by commands.check decorator') from None
            else:
                self.checks.append(predicate)
                self.types.add(predicate.type)
        super().__init__(CheckType.ANY, self.checks)

    async def __call__(self, ctx: commands.Context):
        errors = []
        for check in self.checks:
            try:
                check = check(ctx)
                if isawaitable(check):
                    value = await check
                else:
                    value = check
            except (commands.CheckFailure, commands.CommandError) as e:
                errors.append(e)
            else:
                if value:
                    return True
        # if we're here, all checks failed
        raise commands.CheckAnyFailure(self.checks, errors)


@functools.wraps(commands.check_any)
def check_any(*checks):
    return commands.check(CheckAny(*checks))


class _ChannelDMCheck(Check):
    def __init__(self):
        super().__init__(CheckType.C_PM)

    def __call__(self, ctx: commands.Context):
        if isinstance(ctx.channel, discord.abc.PrivateChannel):
            return True
        else:
            raise commands.PrivateMessageOnly()


class _ChannelGuildCheck(Check):
    def __init__(self):
        super().__init__(CheckType.C_GUILD)

    def __call__(self, ctx: commands.Context):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True


class _ChannelCheck(Check, abc.ABC):
    """
    Base class for command checks for channel. This checks that a given command invocation occurred
    in an allowed channel.
    """
    @abc.abstractmethod
    def get_channels(self, ctx: commands.Context) -> ChannelList:
        raise NotImplementedError

    def is_channel_allowed(self, ctx: commands.Context):
        ch_list = self.get_channels(ctx)
        return discord.utils.get(ch_list, id=ctx.channel.id) is not None or \
               discord.utils.get(ch_list, name=ctx.channel.name) is not None

    def __call__(self, ctx: commands.Context):
        if self.is_channel_allowed(ctx):
            logger.info(f"Validated command allowed in channel {ctx.channel}")
            return True
        else:
            raise UnauthorizedChannelError("Command not allowed in channel.", ctx)


class _ChannelListCheck(_ChannelCheck):
    """ Check that a command was invoked in one of a list of permitted channels. """
    def __init__(self, channels: ChannelRefList, check_type=CheckType.C_LIST):
        super().__init__(check_type, channels)

    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return [get_channel(ctx, ch_id) for ch_id in self.data]


class _ChannelConfigCheck(_ChannelCheck):
    def __init__(self, config_path: ConfigPath, check_type=CheckType.C_LIST):
        try:
            self.config_path = config_path.split('.')
        except AttributeError:
            self.config_path = config_path
        super().__init__(check_type, self.config_path)

    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return ctx.cog.config.traverse(*self.config_path)


class _ChannelConfigRootCheck(_ChannelConfigCheck):
    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return ctx.bot.config.root.traverse(*self.config_path)


class _ChannelStateCheck(_ChannelConfigCheck):
    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return ctx.cog.state.traverse(*self.config_path)


class _ChannelCogStateCheck(_ChannelConfigCheck):
    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return ctx.cog.cog_state.traverse(*self.config_path)


class _BotChannelCheck(_ChannelCheck):
    def get_channels(self, ctx: commands.Context) -> ChannelList:
        return [ctx.bot.config.root.core.discord.channel_public]


def in_channels(*,
                channels: ChannelRefList = None,
                config: ConfigPath = None,
                state: ConfigPath = None,
                cog_state: ConfigPath = None):
    """
    Command check decorator: only allow this command to be run in specific channels. This can be
    passed as a list of channel IDs/names or as a config path to such a list (in the config,
    state or cog_state files). Only one argument should be passed per decorator.

    :param channels: List of channel IDs (as integers) and/or names (string, without leading #).
    :param config: A config path in the main configuration file. This path is relative to the
        CURRENT COG's config section, not the root. It can be passed as a dot-separated string
        like ``"a.b.channels"`` or a tuple/list like ``("a", "b", "channels")``.
    :param state: A config path in the global state file. Same as the ``config`` parameter.
    :param cog_state: A config path in the cog's local state file. Same as the ``config`` parameter,
        but relative to the file's root.
    """
    if channels is not None:
        return commands.check(_ChannelListCheck(channels))
    if config is not None:
        return commands.check(_ChannelConfigCheck(config))
    if state is not None:
        return commands.check(_ChannelStateCheck(state))
    if cog_state is not None:
        return commands.check(_ChannelCogStateCheck(cog_state))


def mod_channels():
    """
    A command check that indicates this command can only be called in mod channels, as configured
    in ``config.toml:core.discord.mod_channels``.
    """
    return commands.check(_ChannelConfigRootCheck("core.discord.mod_channels"))


def admin_channels():
    """
    A command check that indicates this command can only be called in admin channels, as configured
    in ``config.toml:core.discord.admin_channels``.
    """
    return commands.check(_ChannelConfigRootCheck("core.discord.admin_channels"))


def bot_channels():
    """
    A command check that indicates this command can only be called in bot channels, as configured
    in ``config.toml:core.discord.public_channel``.
    """
    return commands.check(_BotChannelCheck())


def dm_only():
    """
    A command check that indicates this command must only be invoked in DM. Raises an
    :exc:`commands.PrivateMessageOnly` exception on failure.

    To allow DM or specific channels, use :func:`check_any` along with any channel checks.
    """
    return commands.check(_ChannelDMCheck())


def guild_only():
    """
    A command check that indicates this command must only be used in guild channels, not in
    private messages. Raises an :exc:`commands.NoPrivateMessage` exception on failure.
    """
    return commands.check(_ChannelGuildCheck())


class _RoleCheck(Check, abc.ABC):
    """
    Base class for command checks for invoker's role. This checks that a given command invocation
    was made by a user with a permitted role.
    """
    ERR_MAP = {
        CheckType.U_ROLE: UnauthorizedUserError,
        CheckType.U_MOD: ModOnlyError,
        CheckType.U_ADMIN: AdminOnlyError
    }

    @abc.abstractmethod
    def get_roles(self, ctx: commands.Context) -> RoleList:
        raise NotImplementedError

    def __call__(self, ctx: commands.Context):
        for role in self.get_roles(ctx):
            if role in ctx.author.roles:
                logger.info(f"Authorized user {ctx.author} {ctx.author.id} via role {role.name}")
                return True
        raise self.ERR_MAP[self.type]("Command not allowed in channel.", ctx)


class _RoleListCheck(_RoleCheck):
    """ Check that a command was invoked by a user with one of the listed roles.. """
    def __init__(self, roles: RoleRefList, check_type=CheckType.U_ROLE):
        super().__init__(check_type, roles)

    def get_roles(self, ctx: commands.Context) -> RoleList:
        return [get_role(ctx, ch_id) for ch_id in self.data]


class _RoleConfigCheck(_RoleCheck):
    def __init__(self, config_path: ConfigPath, check_type=CheckType.U_ROLE):
        try:
            self.config_path = config_path.split('.')
        except AttributeError:
            self.config_path = config_path
        super().__init__(check_type, self.config_path)

    def get_roles(self, ctx: commands.Context) -> RoleList:
        return ctx.cog.config.traverse(*self.config_path)


class _RoleConfigRootCheck(_RoleConfigCheck):
    def get_roles(self, ctx: commands.Context) -> RoleList:
        return ctx.bot.config.root.traverse(*self.config_path)


class _RoleStateCheck(_ChannelConfigCheck):
    def get_roles(self, ctx: commands.Context) -> RoleList:
        return ctx.cog.state.traverse(*self.config_path)


class _RoleCogStateCheck(_ChannelConfigCheck):
    def get_roles(self, ctx: commands.Context) -> RoleList:
        return ctx.cog.cog_state.traverse(*self.config_path)


def has_role(roles: RoleRefList):
    """
    A command check that indicates that this command must be invoked by someone with any of a list
    of roles.
    """
    return commands.check(_RoleListCheck(roles))


def mod_only():
    """
    Command check decorator. Only allow mods and admins to execute this command (as defined by the
    roles defined as ``config.toml:core.discord.mod_roles`` and ``.admin_roles``.
    """
    return commands.check(CheckAny(_mod_roles(), _admin_roles()))


def admin_only():
    """
    Command check decorator. Only allow mods to execute this command (as defined by the
    roles defined as ``config.toml:core.discord.mod_roles`` and ``.admin_roles``.
    """
    return _admin_roles()


def _mod_roles():
    return commands.check(_RoleConfigRootCheck('core.discord.mod_roles', CheckType.U_MOD))


def _admin_roles():
    return commands.check(_RoleConfigRootCheck('core.discord.admin_roles', CheckType.U_ADMIN))


def delete_on_fail():
    """
    Command decorator. If a check fails, delete the command invocation message.
    """
    def decorator(cmd):
        if not isinstance(cmd, commands.Command):
            raise ValueError("@delete_on_fail must be above the discord command or group decorator")
        cmd.kt_delete_on_fail = True
    return decorator


def delete_message():
    """ Command decorator. Always delete the command invocation message. """
    def decorator(cmd):
        if not isinstance(cmd, commands.Command):
            raise ValueError("@delete_on_fail must be above the discord command or group decorator")

        func = cmd.callback

        @functools.wraps(func)
        async def delete_invoking_message(ctx: commands.Context, *args, **kwargs):
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                logger.warning(f"Cannot delete invoking message in #{ctx.channel.name}")
                try:
                    ch = ctx.channel
                    await ctx.bot.channel_out.send(
                        f"Cannot delete invoking message in {ch.mention}: {ch.jump_url}")
                except discord.DiscordException:
                    logger.exception("Exception occurred while sending log message.")
            await func(ctx, *args, **kwargs)

        cmd.callback = delete_invoking_message
        return cmd

    return decorator
