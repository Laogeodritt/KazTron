import re
from typing import Union, Optional, TYPE_CHECKING
import functools

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from kaztron.client import CoreDiscord

import logging

logger = logging.getLogger('kaztron.discord')

MSG_MAX_LEN = 2000


class Limits:
    MESSAGE = MSG_MAX_LEN
    EMBED_TOTAL = 6000
    EMBED_TITLE = 256
    EMBED_AUTHOR = 256
    EMBED_DESC = 2048
    EMBED_FOOTER = 2048
    EMBED_FIELD_NAME = 256
    EMBED_FIELD_VALUE = 1024
    EMBED_FIELD_NUM = 25
    NAME = 32
    STATUS = 128


def get_discord_cfg() -> 'CoreDiscord':
    from kaztron.config import get_kaztron_config
    return get_kaztron_config().root.core.discord


def get_role(ctx: commands.Context, role: str) -> Optional[discord.Role]:
    """ Get a role in the current guild by name or ID, or None if not found. """
    if isinstance(role, int):
        r = ctx.guild.get_role(role)
    else:
        r = discord.utils.get(ctx.guild.roles, name=role)
    return r


def get_channel(ctx: commands.Context, ch: Union[str, int]) -> Optional[discord.TextChannel]:
    """ Get a channel in the current guild by name or ID, or None if not found. """
    if isinstance(ch, int):
        ch = ctx.guild.get_channel(ch)
    else:
        ch = discord.utils.get(ctx.guild.channels, name=ch)
    return ch


def user_mention(user_id: str) -> str:
    """
    Return a mention of a user that can be sent over a Discord message. This is a convenience
    method for cases where the user_id is known but you don't have or need the full discord.User
    or discord.Member object.
    """
    if not user_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<@{}>'.format(user_id)


def role_mention(role_id: int) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    return '<@&{:d}>'.format(role_id)


def channel_mention(channel_id: int) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    return '<#{:d}>'.format(channel_id)


_re_user_id = re.compile(r'(?:(?:\\)?<@|@)?!?([0-9]{15,23})>?')
_re_role_id = re.compile(r'(?:(?:\\)?<@&|@&|&)?([0-9]{15,23})>?')


def extract_user_id(input_id: str) -> int:
    """
    Validate and extract a user ID from an input (@mention, raw user ID, etc.).

    This method is intended to validate and sanitise an input provided by a user, e.g., over a
    command. It can accept:

    * Raw ID: '123456789012345678'
    * Mentions:
        * No nickname: '<@123456789012345678>'
        * User has nickname: '<@!123456789012345678>'
    * Attempts to provide a raw ID:
        * '@123456789012345678'
        * '@!123456789012345678'
        * '!123456789012345678'
    * Various errors:
        * <@123456789012345678
        * 123456789012345678>
        * etc.

    User ID parameters from:
    https://github.com/Rapptz/discord.py/blob/1863a1c6636f53592519320a173ec9573c090c0b/discord/ext/commands/converter.py#L83

    :param input_id: The raw input ID.
    :return: The extracted user ID (numerical string).
    :raise discord.InvalidArgument: id is not a recognised user ID format
    """
    if 15 <= len(input_id) <= 23 and input_id.isnumeric():
        return int(input_id)

    try:
        return int(_re_user_id.fullmatch(input_id).group(1))
    except AttributeError:  # no match - fullmatch() returned None
        raise discord.InvalidArgument('Invalid user ID format {!r}'.format(input_id))


def extract_role_id(input_id: str) -> str:
    """
    Similar to :func:`~.extract_user_id` for roles.

    Role mentions are of the form <@&123456789012345678>.

    :param input_id: The raw input ID.
    :return: The extracted user ID (numerical string).
    :raise discord.InvalidArgument: id is not a recognised user ID format
    """
    if 15 <= len(input_id) <= 23 and input_id.isnumeric():
        return input_id

    try:
        return _re_role_id.fullmatch(input_id).group(1)
    except AttributeError:
        raise discord.InvalidArgument('Invalid role ID format {!r}'.format(input_id))


def get_member(ctx: commands.Context, user: str) -> discord.Member:
    """
    Return the :cls:`discord.Member` for a given input identifying a user (ID, mention, name, etc.).
    
    The user must be a member of a visible server. The current server (as determined by context)
    is prioritised in searching.
    
    This function is intended to be robust for various types of inputs that may be input by
    a user to a bot command:
    
    * Simple ID: '123456789012345678'
    * Mentions:
        * No nickname: '<@123456789012345678>'
        * User has nickname: '<@!123456789012345678>'
    * Variations on mentions altered by user:
        * '@123456789012345678'
        * '@!123456789012345678'
        * '!123456789012345678'
    * Search by user name and discriminator:
        * JaneDoe#0921
        * JaneDoe
    
    :return:
    :raises commands.MemberNotFound: user not found
    """

    # try our own extractor as it handles more weird input cases
    # if fail assume it's a name lookup
    result = None
    guild = ctx.guild
    try:
        s_user_id = extract_user_id(user)
    except discord.InvalidArgument:
        # cannot extract ID: assume name lookup
        if guild:
            result = guild.get_member_named(user)
        else:
            for guild in ctx.bot.guilds:  # type: discord.Guild
                result = guild.get_member_named(user)
                if result:
                    break
    else:
        if guild:
            result = guild.get_member(s_user_id) or \
                     discord.utils.get(ctx.message.mentions, id=s_user_id)
        else:
            for guild in ctx.bot.guilds:  # type: discord.Guild
                result = guild.get_member(s_user_id)
                if result:
                    break

    if result is None:
        raise commands.MemberNotFound(user)

    return result


def get_command_prefix(ctx: commands.Context) -> str:
    prefix = ctx.bot.command_prefix
    if callable(prefix):
        prefix = prefix(ctx.bot, ctx.message)
    return prefix


def get_command_str(ctx: commands.Context) -> str:
    """
    Get the command string, with subcommand if passed. Arguments are not included.
    :param ctx:
    :return:
    """
    # apparently in a subcommand, invoked_with == the SUBcommand, invoked_subcommand == None???
    # ... what???

    # cmd_str = "{0.bot.command_prefix}{0.invoked_with}".format(ctx)
    # if ctx.subcommand_passed:
    #    cmd_str += " {0.subcommand_passed}".format(ctx)
    # return cmd_str
    try:
        return f"{get_command_prefix(ctx)}{ctx.command.qualified_name}"
    except AttributeError:
        return ""


def get_help_str(ctx: commands.Context) -> str:
    """
    Gets the help string for the invoked command, with subcommand if passed.
    :param ctx:
    :return:
    """
    # Same remark as above ... what???

    # cmd_str = "{0.bot.command_prefix}help {0.invoked_with}".format(ctx)
    # if ctx.subcommand_passed:
    #     cmd_str += " {0.subcommand_passed}".format(ctx)
    # return cmd_str

    try:
        return f"{get_command_prefix(ctx)}help {ctx.command.qualified_name}"
    except AttributeError:
        return f"{get_command_prefix(ctx)}help"


def get_usage_str(ctx: commands.Context) -> str:
    """
    Retrieves the signature portion of the help page.

    Based on discord.ext.commands.help.HelpCommand.get_command_signature()
    https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/help.py

    Copyright (c) 2015-2021 Rapptz. Distributed under the MIT Licence.
    """
    result = []
    prefix = get_command_prefix(ctx)
    cmd = ctx.command
    parent = cmd.full_parent_name
    if len(cmd.aliases) > 0:
        aliases = '|'.join(cmd.aliases)
        full_name = f'[{cmd.name}|{aliases}]'
    else:
        full_name = cmd.name

    if parent:
        result.append(f'{prefix}{parent} {full_name}')
    else:
        result.append(f'{prefix}{full_name}')

    result.append(cmd.signature)
    return ' '.join(result)


def metagroup(*args, **kwargs):
    """
    Convenience decorator for a discord.ext.commands.group() that does not itself act as a command,
    only a container/category for subcommands. If this group is called alone (instead of calling
    a subcommand), a help message is displayed.

    In addition to the help message, this decorator is syntactic sugar for:

    .. code-block:: html
        @discord.ext.commands.group(invoke_without_command=True, ignore_extra=True, *args, **kwargs)

    Any arguments passed to ``metagroup`` are passed along to the command group decorator.

    The decorated function can be empty (``pass``). However, if needed, it could also have a body:
    it will be executed after showing the help message.
    :param args:
    :param kwargs:
    :return:
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(this, ctx: commands.Context, *args, **kwargs):
            await ctx.reply(get_group_help(ctx))
            return await func(this, ctx, *args, **kwargs)

        group = commands.group(invoke_without_command=True, ignore_extra=True, *args, **kwargs)
        return group(wrapper)
    return decorator


def get_group_help(ctx: commands.Context):
    subcommands = sorted(list(ctx.command.commands), key=lambda c: c.name)
    subcommand_strs = ['|'.join([c.name] + list(c.aliases)) for c in subcommands]
    subcommand_list = ', '.join(subcommand_strs)
    return (f"Oops! You need to specify a valid subcommand for the `{get_command_str(ctx)}` group. "
            f" Valid subcommands are: `{subcommand_list}`. "
            f"Type `{get_help_str(ctx)}` for more info.")
