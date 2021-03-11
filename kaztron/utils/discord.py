import re
from typing import List, Sequence, Iterable

import discord
from discord.ext import commands

from kaztron.config import get_kaztron_config

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


def check_role(rolelist: Iterable[str], message: discord.Message):
    """
    Check if the author of a ``message`` has one of the roles in ``rolelist``.

    :param rolelist: A list of role names.
    :param message: A :cls:``discord.Message`` object representing the message
        to check.
    """
    for role in rolelist:
        if discord.utils.get(message.author.roles, name=role) is not None:
            return True
    else:
        return False


def get_role_by_name(guild: discord.Guild, role_name: str) -> discord.Role:
    """
    Get a role by name. This is a convenience function, providing a ValueError if the role does not
    exist instead of returning None and causing a less clear exception downstream.

    :param guild: Server on which to find the role
    :param role_name: Role name to find
    :return: Discord Role corresponding to the given name
    :raises ValueError: role does not exist
    """
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        raise ValueError("Role '{!s}' not found.".format(role_name))
    return role


def check_mod(ctx: commands.Context):
    """
    Check if the sender of a command is a mod or admin (as defined by the
    roles in the "discord" -> "mod_roles" and "discord" -> "admin_roles" configs).
    """
    config = get_kaztron_config()
    return check_role(config.get("discord", "mod_roles", []), ctx.message) or \
        check_role(config.get("discord", "admin_roles", []), ctx.message)


def check_admin(ctx: commands.Context):
    """
    Check if the sender of a command is an admin (as defined by the
    roles in the "discord" -> "admin_roles" config).
    """
    config = get_kaztron_config()
    return check_role(config.get("discord", "admin_roles", []), ctx.message)


async def remove_role_from_all(role: discord.Role):
    """
    Removes a role from all users on the server who have that role.
    :param role: Role to remove.
    """
    for m in role.members:
        await m.remove_roles(role)


def user_mention(user_id: str) -> str:
    """
    Return a mention of a user that can be sent over a Discord message. This is a convenience
    method for cases where the user_id is known but you don't have or need the full discord.User
    or discord.Member object.
    """
    if not user_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<@{}>'.format(user_id)


def role_mention(role_id: str) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    if not role_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<@&{}>'.format(role_id)


def channel_mention(channel_id: str) -> str:
    """
    Return a mention for a role that can be sent over a Discord message.
    """
    if not channel_id.isnumeric():
        raise ValueError("Discord ID must be numeric")
    return '<#{}>'.format(channel_id)


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
    return "{}{}".format(get_command_prefix(ctx), ctx.command.qualified_name)


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

    return "{}help {}".format(get_command_prefix(ctx), ctx.command.qualified_name)


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


def get_group_help(ctx: commands.Context):
    subcommands = sorted(list(set(ctx.command.commands.values())), key=lambda c: c.name)
    subcommand_strs = ['|'.join([c.name] + list(c.aliases)) for c in subcommands]
    subcommand_list = ', '.join(subcommand_strs)
    return ('Invalid sub-command. Valid subcommands are `{0!s}`. '
            'Use `{1}` or `{1} <subcommand>` for instructions.') \
        .format(subcommand_list, get_help_str(ctx))
