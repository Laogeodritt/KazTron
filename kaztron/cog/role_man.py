import copy
import logging
from typing import Iterable

import discord
from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.checks import mod_only
from kaztron.utils.discord import get_named_role, get_help_str
from kaztron.utils.logging import message_log_str

logger = logging.getLogger(__name__)


class RoleManager(KazCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.managed_roles = {}

    async def on_ready(self):
        if not self.is_ready:  # first time this is called - not a reconnect
            self.setup_all_config_roles()

        await super().on_ready()

    def add_managed_role(
            self,
            role_name: str,
            join: str,
            leave: str,
            join_msg: str,
            leave_msg: str,
            join_err: str,
            leave_err: str,
            join_doc: str=None,
            leave_doc: str=None,
            join_aliases: Iterable[str] = tuple(),
            leave_aliases: Iterable[str] = tuple(),
            group: commands.Group = None,
            cog_instance=None,
            checks=tuple(),
            **kwargs
    ):
        """
        Add managed roles from other cogs or code. This method should be called after on_ready,
        to ensure that server roles are available to validate against.

        :param role_name: The role to manage.
        :param join: The join command name.
        :param leave: The leave command name.
        :param join_aliases: An iterable of join command aliases. Optional.
        :param leave_aliases: An iterable of leave command aliases. Optional.
        :param join_msg: Message to send when the user successfully joins the role.
        :param leave_msg: Message to send when the user successfully leaves the role.
        :param join_err: Message when the user tries to join but is already member of the role.
        :param leave_err: Message when the user tries to leave but is not a role member.
        :param join_doc: Help string for the join command.
        :param leave_doc: Help string for the leave command.
        :param group: The group to add this command to. Optional.
        :param cog_instance: Cog to group this command under in the help.
        :param checks: Check objects to apply to the command
        :param kwargs: Keyword args to pass the ``discord.ext.commands.command`` decorator. Do not
            include `name`, `aliases`, or `pass_context`. Can also include checks here, e.g., for
            if only certain users should be able to use these commands.

        :raise TypeError: Command already exists
        """

        async def _managed_role_join(self_dummy, ctx: commands.Context):
            logger.debug("join: " + message_log_str(ctx.message)[:256])
            role = get_named_role(ctx.message.server, role_name)

            if role not in ctx.message.author.roles:
                await self.bot.add_roles(ctx.message.author, role)
                logger.info("join: Gave role {} to user {}"
                    .format(role_name, ctx.message.author))
                await self.bot.send_message(ctx.message.author, join_msg)
            else:
                await self.bot.send_message(ctx.message.author, join_err)

            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                logger.warning(("Cannot delete command message '{}': "
                                "forbidden (Discord permissions)")
                    .format(message_log_str(ctx.message)[:256]))
                # let's leave this feature "optional":
                # no need to spam the output channel if the permission intentionally not given

        async def _managed_role_leave(self_dummy, ctx: commands.Context):
            logger.debug("leave: " + message_log_str(ctx.message)[:256])
            role = get_named_role(ctx.message.server, role_name)

            if role in ctx.message.author.roles:
                await self.bot.remove_roles(ctx.message.author, role)
                logger.info("leave: Removed role {} from user {}"
                    .format(role_name, ctx.message.author))
                await self.bot.send_message(ctx.message.author, leave_msg)
            else:
                await self.bot.send_message(ctx.message.author, leave_err)

            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                logger.warning(("Cannot delete command message '{}': "
                                "forbidden (Discord permissions)")
                    .format(message_log_str(ctx.message)[:256]))
                # let's leave this feature "optional":
                # no need to spam the output channel if the permission intentionally not given

        logger.info("Adding managed role {}".format(role_name))

        if not join_doc:
            join_doc = "Join the {} role.".format(role_name)
        if not leave_doc:
            leave_doc = "Leave the {} role.".format(role_name)

        _managed_role_join.__doc__ = join_doc
        _managed_role_leave.__doc__ = leave_doc

        _checked_join = _managed_role_join
        _checked_leave = _managed_role_leave
        for check in checks:
            _checked_join = check(_checked_join)
            _checked_leave = check(_checked_leave)

        if group:
            jc = group.command(
                name=join, aliases=join_aliases,
                pass_context=True, **kwargs)(_checked_join)
            lc = group.command(
                name=leave, aliases=leave_aliases,
                pass_context=True, **kwargs)(_checked_leave)
        else:
            jc = commands.command(
                name=join, aliases=join_aliases,
                ass_context=True, **kwargs)(_managed_role_join)
            lc = commands.command(
                name=leave, aliases=leave_aliases,
                pass_context=True, **kwargs)(_managed_role_leave)

        if not cog_instance:
            cog_instance = self

        jc.instance = cog_instance
        lc.instance = cog_instance

        self.managed_roles[role_name] = (jc, lc)

    def setup_all_config_roles(self):
        logger.info("Setting up managed roles from configuration")
        user_role_map = self.config.get('role_man', 'user_roles', {})
        for name, args in user_role_map.items():
            self.setup_config_role(name, args)

        mod_role_map = self.config.get('role_man', 'mod_roles', {})
        for name, args in mod_role_map.items():
            self.setup_config_role(name, args, [mod_only()])

    def setup_config_role(self, name, role_map, checks: Iterable=tuple()):
        logger.info("Setting up managed role from config: {}".format(name))
        logger.debug("With configuration: {!r}".format(role_map))

        group = role_map.get('group', tuple())
        kwargs = copy.deepcopy(role_map)

        # Recursively get the groups
        logger.debug("Finding group.")
        current_group = self.bot  # type: commands.GroupMixin
        for command_name in group:
            try:
                current_group = current_group.commands[command_name]
            except KeyError:
                # raise discord.ClientException(("Cannot group role management command: parent "
                #                              "command '{0}' does not exist").format(command_name))
                logger.warning("Group '{}' does not exist: making dummy group."
                    .format(command_name))

                async def anonymous_group(dummy_self, ctx: commands.Context):
                    command_list = list(ctx.command.commands.keys())
                    await self.bot.say(('Invalid sub-command. Valid sub-commands are {0!s}. '
                                        'Use `{1}` or `{1} <subcommand>` for instructions.')
                        .format(command_list, get_help_str(ctx)))

                current_group = current_group.group(invoke_without_command=True, pass_context=True)\
                        (anonymous_group)
                current_group.instance = self
            except AttributeError:
                raise discord.ClientException(("Cannot group role management command: parent "
                                              "command '{0.name}' is not a group")
                    .format(current_group))
        else:
            kwargs['group'] = current_group

        kwargs['checks'] = checks

        try:
            self.add_managed_role(role_name=name, **kwargs)
        except TypeError as e:
            raise discord.ClientException("Configuration error for managed role '{}': {}"
                .format(name, e.args[0]))


def setup(bot):
    bot.add_cog(RoleManager(bot))
