import asyncio
import logging

import sys
from typing import List, Sequence
import re

import discord
from discord.ext import commands

import kaztron
from kaztron import config as cfg
from kaztron.client import CoreConfig, InfoLink
from kaztron.errors import *
# from kaztron.help_formatter import DiscordHelpFormatter, JekyllHelpFormatter
# from kaztron.rolemanager import RoleManager
from kaztron.utils.cogutils import *
from kaztron.utils.datetime import format_timestamp, format_timedelta
from kaztron.utils.embeds import EmbedSplitter

logger = logging.getLogger(__name__)


class CoreState(cfg.ConfigModel):
    public_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])
    mod_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])


class CoreCog(kaztron.KazCog):
    """!kazhelp

    brief: Essential internal {{name}} functionality, plus bot information and control commands.
    description: |
        Essential {{name}} functionality: core setup and configuration tasks, general-purpose error
        handling for other cogs and commands, etc. It also includes commands for general bot
        information and control. The Core cog cannot be disabled.
    contents:
        - info
        - request
        - jekyllate
    """
    config: CoreConfig
    state: CoreState

    def __init__(self, bot):
        super().__init__(bot, 'core', state_model=CoreState)
        self.bot.event(self.on_error)  # register this as a global event handler, not just local

    async def on_error(self, event, *args, **kwargs):
        exc_info = sys.exc_info()
        if exc_info[0] is KeyboardInterrupt:
            logger.warning("Interrupted by user (SIGINT)")
            raise exc_info[1]
        elif exc_info[0] is asyncio.CancelledError:  # scheduler events, usually
            raise exc_info[1]
        elif exc_info[0] is BotNotReady:
            logger.warning("Event {} called before on_ready: ignoring".format(event))
            return

        log_msg = "{}({}, {})".format(
            event,
            ', '.join(repr(arg) for arg in args),
            ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
        logger.exception("Error occurred in " + log_msg)
        await self.bot.channel_out.send_split("[ERROR] In {}\n\n{}\n\nSee log for details".format(
            log_msg, logutils.exc_log_str(exc_info[1])))

        try:
            message = args[0]
            await message.send(
                "An error occurred! Details have been logged. "
                "Please let the mods know so we can investigate.")
        except IndexError:
            pass
        except AttributeError:
            logger.warning("Couldn't extract channel context from previous error - "
                           "is args[0] not a message?")

    bad_argument_map = {
        'Converting to "int" failed.': 'Parameter must be a whole number (0, 1, 2, -1, etc.).',
        'Converting to "NaturalInteger" failed.':
                    'Parameter must be a whole number (0, 1, 2, -1, etc.).',
        'Converting to "float" failed.': 'Parameter must be a whole or decimal number '
                                         '(0, 1, 2, 3.14, -2.71, etc.)'
    }

    async def on_command_error(self, exc, ctx: commands.Context, force=False):
        """
        Handles all command errors (see the ``discord.ext.commands.errors`` module).
        This method will do nothing if a command is detected to have an error
        handler ("on_error"); if you want on_command_error's default behaviour to
        take over, within a command error handler, you can call this method and
        pass ``force=True``.

        If you define custom command error handlers, note that CommandInvokeError
        is the one you want to handle for arbitrary errors (i.e. any exception
        raised that isn't derived from CommandError will cause discord.py to raise
        a CommandInvokeError from it).
        """
        cmd_string = logutils.message_log_str(ctx.message)
        author_mention = ctx.author.mention + ' '

        if not force and hasattr(ctx.command, "on_error"):
            return

        if ctx is not None and ctx.command is not None:
            usage_str = get_usage_str(ctx)
        else:
            usage_str = '(Unable to retrieve usage information)'

        if isinstance(exc, DeleteMessage):
            try:
                await ctx.message.delete()
                logger.info("on_command_error: Deleted invoking message")
            except discord.errors.DiscordException:
                logger.exception("Can't delete invoking message!")
            exc = exc.cause
        # and continue on to handle the cause of the DeleteMessage...

        if isinstance(exc, commands.CommandOnCooldown):
            await ctx.send(author_mention + "`{}` is on cooldown! Try again in {:.0f} seconds."
                    .format(get_command_str(ctx), max(exc.retry_after, 1.0)))

        elif isinstance(exc, commands.CommandInvokeError):
            root_exc = exc.__cause__ if exc.__cause__ is not None else exc
            if isinstance(root_exc, KeyboardInterrupt):
                logger.warning("Interrupted by user (SIGINT)")
                raise root_exc
            elif isinstance(root_exc, discord.Forbidden) \
                    and root_exc.code == DiscordErrorCodes.CANNOT_PM_USER:
                author: discord.Member = ctx.author
                err_msg = "Can't PM user (FORBIDDEN): {0} {1}".format(
                    author.nick or author.name, author.id)
                logger.warning(err_msg)
                logger.debug(logutils.tb_log_str(root_exc))
                await ctx.send(author_mention +
                    "You seem to have PMs from this server disabled or you've blocked me. "
                     "I need to be able to PM you for this command."
                )
                await self.bot.channel_out.send("[WARNING] " + err_msg)
                return  # we don't want the generic "an error occurred!"
            elif isinstance(root_exc, discord.HTTPException):  # API errors
                err_msg = 'While executing {c}\n\nDiscord API error {e!s}' \
                    .format(c=cmd_string, e=root_exc)
                logger.error(err_msg + "\n\n{}".format(logutils.tb_log_str(root_exc)))
                await self.bot.channel_out.send_split("[ERROR] " + err_msg +
                                                      "\n\nSee log for details")
            else:
                logger.error("An error occurred while processing the command: {}\n\n{}"
                    .format(cmd_string, logutils.tb_log_str(root_exc)))
                await self.bot.channel_out.send_split(
                    "[ERROR] While executing {}\n\n{}\n\nSee logs for details"
                    .format(cmd_string, logutils.exc_log_str(root_exc)))

            # In all cases (except if return early/re-raise)
            await ctx.send(author_mention +
                "An error occurred! Details have been logged. Let a mod know so we can "
                "investigate.")

        elif isinstance(exc, commands.DisabledCommand):
            msg = "Attempt to use disabled command: {}".format(cmd_string)
            logger.warning(msg)
            # No need to log this on Discord - not something mods need to be aware of
            # No need to inform user of this - prevents spam, "disabled" commands could just not
            # exist

        elif isinstance(exc, (ModOnlyError, AdminOnlyError)):
            err_msg = "Unauthorised user for this command ({}): {!r}".format(
                type(exc).__name__, cmd_string
            )
            logger.warning(err_msg)
            await self.bot.channel_out.send('[WARNING] ' + err_msg)

            err_str = logutils.exc_msg_str(exc,
                "Only moderators may use that command." if isinstance(exc, ModOnlyError)
                else "Only administrators may use that command.")
            await ctx.send(author_mention + err_str)

        elif isinstance(exc, (UnauthorizedUserError, commands.CheckFailure)):
            logger.warning(
                "Check failed on command: {!r}\n\n{}".format(cmd_string, logutils.tb_log_str(exc)))
            await self.bot.channel_out.send_split('[WARNING] ' +
                "Check failed on command: {!r}\n\n{}".format(cmd_string, logutils.exc_log_str(exc)))
            err_str = logutils.exc_msg_str(exc,
                "*(Dev note: Implement error handler with more precise reason)*")
            await self.bot.channel_out.send_split(ctx.message.channel, author_mention +
                "You're not allowed to use that command: " + err_str)

        elif isinstance(exc, UnauthorizedChannelError):
            err_msg = "Unauthorised channel for this command: {!r}".format(cmd_string)
            logger.warning(err_msg)
            await self.bot.channel_out.send_split('[WARNING] ' + err_msg)
            err_str = logutils.exc_msg_str(exc, "Command not allowed in this channel.")
            await ctx.send_split(author_mention + "You can't use that command here: " + err_str)

        elif isinstance(exc, commands.NoPrivateMessage):
            msg = "Attempt to use non-PM command in PM: {}".format(cmd_string)
            logger.warning(msg)
            await ctx.send("Sorry, you can't use that command in PM.")
            # No need to log this on Discord, spammy and isn't something mods need to be aware of

        elif isinstance(exc, commands.BadArgument):
            exc_msg = exc.args[0] if len(exc.args) > 0 else '(No error message).'
            msg = "Bad argument passed in command: {}\n{}".format(cmd_string, exc_msg)
            logger.warning(msg)

            # do some user-friendliness message remapping
            exc_msg = self.bad_argument_map[exc_msg]\
                            if exc_msg in self.bad_argument_map else exc_msg

            await ctx.send(author_mention +
                "Invalid parameter(s): {}\n\n**Usage:** `{}`\n\nUse `{}` for help."
                    .format(exc_msg, usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.TooManyArguments):
            msg = "Too many parameters passed in command: {}".format(cmd_string)
            logger.warning(msg)
            await ctx.send(author_mention +
                "Too many parameters.\n\n**Usage:** `{}`\n\nUse `{}` for help."
                    .format(usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, commands.MissingRequiredArgument):
            msg = "Missing required parameters in command: {}".format(cmd_string)
            logger.warning(msg)
            await ctx.send(author_mention +
                "Missing parameter(s).\n\n**Usage:** `{}`\n\nUse `{}` for help."
                    .format(usage_str, get_help_str(ctx)))
            # No need to log user errors to mods

        elif isinstance(exc, BotNotReady):
            try:
                cog_name = exc.args[0]
            except IndexError:
                cog_name = 'unknown'
            logger.warning(f"Attempted to use command while cog is not ready: {cmd_string}")
            await ctx.send(author_mention +
                "Sorry, I'm still loading the {} module! Try again in a few seconds."
                .format(cog_name)
            )

        elif isinstance(exc, BotCogError):
            try:
                cog_name = exc.args[0]
            except IndexError:
                cog_name = 'unknown'
            logger.error("Attempted to use command on cog in error state: {}".format(cmd_string))
            await ctx.send(author_mention +
                "Sorry, an error occurred loading the {} module! Please let a mod/admin know."
                .format(cog_name)
            )

        elif isinstance(exc, commands.CommandNotFound):
            msg = "Unknown command: {}".format(cmd_string)
            # safe to assume commands usually words - symbolic commands are rare
            # and we want to avoid emoticons ('._.', etc.), punctuation ('...') and decimal numbers
            # without leading 0 (.12) being detected
            if ctx.invoked_with and all(c.isalnum() or c == '_' for c in ctx.invoked_with) \
                    and not ctx.invoked_with[0].isdigit():
                logger.warning(msg)
                await ctx.send_split(author_mention + "Sorry, I don't know the command `{}{}`"
                        .format(get_command_prefix(ctx), ctx.invoked_with))

        elif isinstance(exc, commands.UserInputError):
            logger.warning("UserInputError: {}\n{}"
                .format(cmd_string, logutils.tb_log_str(exc)))
            await ctx.send_split('{} {}'.format(author_mention, exc.args[0]))

        else:
            logger.error("Unknown command exception occurred: {}\n\n{}"
                .format(cmd_string, logutils.tb_log_str(exc)))
            await ctx.send(author_mention +
                "An unexpected error occurred while processing a command! "
                "Details have been logged. Let a mod know so we can investigate.")
            await self.bot.channel_out.send(
                ("[ERROR] Unknown error while trying to process command:\n{}\n"
                 "**Error:** {!s}\n\nSee logs for details").format(cmd_string, exc))

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """!
        description: Check if the bot is responsive. This command is designed to be minimalist and
            provide minimal failure points, to allow verifying if the bot is at all responsive.
        """
        await ctx.send(ctx.author.mention + " Pong.")

    @commands.command()
    @checks.mod_only()
    @checks.mod_channels()
    async def version(self, ctx: commands.Context):
        """!kazhelp

        description: Provides technical bot information and links for operators/admins.
        details: Provides detailed version and runtime information on this {{name}} instance.
        """
        em = discord.Embed(color=0x80AAFF, title=self.config.name)
        em.add_field(name="KazTron Core", value="v{}".format(kaztron.__version__), inline=True)
        em.add_field(name="discord.py", value="v{}".format(discord.__version__), inline=True)
        em.add_field(name="Uptime", value=format_timedelta(self.bot.uptime), inline=True)

        em.add_field(name="Loaded Cogs", value=
            '\n'.join(name for name in self.bot.cogs_ready) + '\n' +
            '\n'.join(name + " (std cog)" for name in self.bot.cogs_std)
        )
        em.add_field(name="Load Error", value='\n'.join(name for name in self.bot.cogs_error))
        em.add_field(name="Not Loaded", value='\n'.join(name for name in self.bot.cogs_not_ready))

        for link in self.merge_info_links(kaztron.bot_links, tuple(), with_manual=True):
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        await ctx.send(ctx.author.mention, embed=em)

    @commands.group(invoke_without_command=True)
    async def info(self, ctx: commands.Context):
        """!kazhelp

        description: Provides bot info and useful links.
        details: |
            This command provides the version of the {{name}} instance currently running and links
            to documentation, the GitHub repository, and other resources for bot users.

            TIP: The links can be customised in the configuration or dynamically using the
            {{!info add}} and {{!info rem}} commands.

            NOTE: *For operators and moderators.* Use {{!version}} for technical bot info (like cog
            status) and {{!modinfo}} for mod-specific info links.
        """
        em = EmbedSplitter(color=0x80AAFF, title=self.config.name)
        em.set_footer(text="Can be customised by mods: `.info add` and `.info rem`.")
        links = self.merge_info_links(self.config.public_links, self.state.public_links, True)
        for link in links:
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        for e in em.finalize():
            await ctx.send(ctx.author.mention, embed=e)

    @info.command(name='add')
    @checks.mod_only()
    async def info_add(self, ctx: commands.Context, name: str, url: str):
        """!kazhelp

        description: Add a public link to the {{!info}} command.
        details: If a link of the same name already exists, replaces it.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
            - name: url
              type: str
              description: URL of the linked resource. If it contains spaces, must be surrounded
                by double quotes.
        examples:
            - command: .info add "/r/aww on reddit" https://reddit.com/r/aww
              description: Adds a link to the /r/aww subreddit.
        """
        new_link = InfoLink(name=name, url=url)
        try:  # try to find a link of the same name
            i = next(i for i, v in enumerate(self.state.public_links) if v.name == name)
            self.state.public_links[i] = new_link
        except StopIteration:  # if same name not found
            self.state.public_links.append(new_link)
        await ctx.send(ctx.author.mention + f" Added link '{name}' {url}")

    @info.command(name='rem', aliases=['remove'])
    @checks.mod_only()
    async def info_rem(self, ctx: commands.Context, name: str):
        """!kazhelp

        description: Remove a public link from the {{!info}} command.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
        examples:
            - command: .info rem "/r/aww on reddit"
              description: Remove the link named "/r/aww on reddit".
        """
        try:
            link = next(v for v in self.state.public_links if v.name == name)
            self.state.public_links.remove(link)
        except StopIteration:  # not found
            await ctx.send(ctx.author.mention + f" **ERROR**: No link named '{name}'.")
        else:
            await ctx.send(ctx.author.mention + f" Removed link '{name}' to {link.url}")

    @commands.group(invoke_without_command=True)
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo(self, ctx: commands.Context):
        """!kazhelp
        description: Provides useful links for moderators and bot operators.
        """
        em = EmbedSplitter(color=0x80AAFF, title=self.config.name)
        em.set_footer(text="Can be customised by mods: `.info add` and `.info rem`.")
        links = self.merge_info_links(self.config.mod_links, self.state.mod_links, False)
        for link in links:
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        for e in em.finalize():
            await ctx.send(ctx.author.mention, embed=e)

    @modinfo.command(name='add')
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo_add(self, ctx: commands.Context, name: str, url: str):
        """!kazhelp

        description: Add a link to the {{!modinfo}} command.
        details: If a link of the same name already exists, replaces it.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
            - name: url
              type: str
              description: URL of the linked resource. If it contains spaces, must be surrounded
                by double quotes.
        examples:
            - command: .modinfo add "/r/aww on reddit" https://reddit.com/r/aww
              description: Adds a link to the /r/aww subreddit.
        """
        new_link = InfoLink(name=name, url=url)
        try:  # try to find a link of the same name
            i = next(i for i, v in enumerate(self.state.mod_links) if v.name == name)
            self.state.mod_links[i] = new_link
        except StopIteration:  # if same name not found
            self.state.mod_links.append(new_link)
        await ctx.send(ctx.author.mention + f" Added mod link '{name}' {url}")

    @modinfo.command(name='rem', aliases=['remove'])
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo_rem(self, ctx: commands.Context, name: str):
        """!kazhelp

        description: Remove a link from the {{!modinfo}} command.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
        examples:
            - command: .modinfo rem "/r/aww on reddit"
              description: Remove the link named "/r/aww on reddit".
        """
        try:
            link = next(v for v in self.state.mod_links if v.name == name)
            self.state.mod_links.remove(link)
        except StopIteration:  # not found
            await ctx.send(ctx.author.mention + f" **ERROR**: No mod link named '{name}'.")
        else:
            await ctx.send(ctx.author.mention + f" Removed mod link '{name}' to {link.url}")

    def merge_info_links(self, a: Sequence[InfoLink], b: Sequence[InfoLink], with_manual=False):
        """
        Merge InfoLink lists. If links have the same name, b will overwrite a. If with_manual is
        True, the manual is also added (but may be overwritten by both a and b).
        """
        if with_manual:
            manual = [InfoLink(name='Manual', url=self.config.manual_url)]
            return self.merge_info_links(self.merge_info_links(manual, a), b)

        links = {link.name: link for link in a}
        links.update({link.name: link for link in b})
        return [links.values()]

    @commands.command(pass_context=True, aliases=['bug'])
    @commands.cooldown(rate=3, per=120)
    async def issue(self, ctx, *, content: str):
        """!kazhelp

        description: Submit a bug report or feature request to the {{name}} bot team.
        details: |
            Everyone can use this command, but please make sure that your submission is **clear**,
            and submitted as **one issue per command** (don't split up one issue into several
            commands or submit several issues in one command).

            If you're reporting a bug, include the answers to the questions:

            * What were you trying to do? Include the *exact* command you tried to use, if any.
            * What error messages were given by the bot? *Exact* message.
            * Where and when did this happen? Ideally, link the message itself (message menu >
              Copy Link).

            If you're requesting a feature, make sure to answer these questions:

            * What do you want the feature to do?
            * Why is this useful? Who do you expect will use it? How and where will they use it?

            IMPORTANT: Any submissions made via this system may be tracked publicly. By submitting
            a request via this system, you give us permission to post your username and message,
            verbatim or altered, to a public database for the purpose of project management.

            IMPORTANT: Abuse of this command may be treated like spam, and enforced accordingly.
        examples:
            - command: |
                .request When trying to use the `.roll 3d20` command, I get the message:
                "An error occurred! Details have been logged. Let a mod know so we can investigate."

                This only happens with d20, I've tried d12 and d6 with no problems.
                The last time this happened was here: <direct link to message>
        """
        em = EmbedSplitter(color=0x80AAFF, auto_truncate=True)
        em.set_author(name="User Issue Submission")
        em.add_field(name="User", value=ctx.message.author.mention, inline=True)
        try:
            em.add_field(name="Channel", value=ctx.message.channel.mention, inline=True)
        except AttributeError:  # probably a private channel
            em.add_field(name="Channel", value=ctx.message.channel, inline=True)
        em.add_field(name="Timestamp", value=format_timestamp(ctx.message), inline=True)
        em.add_field(name="Content", value=content, inline=False)
        for e in em.finalize():
            await self.config.discord.channel_issues.send(embed=em)
        await ctx.send(ctx.author.mention + " Your issue was submitted to the bot DevOps team. "
                       "If you have any questions or if there's an urgent problem, "
                       "please feel free to contact the moderators directly.")

    @commands.command(pass_context=True)
    @checks.mod_only()
    @checks.mod_channels()
    async def jekyllate(self, ctx: commands.Context):
        """!kazhelp

        description: Generate Jekyll-compatible markdown documentation for all loaded cogs.
        """
        import os
        import io
        import zipfile

        jekyll = JekyllHelpFormatter(self.bot.kaz_help_parser, self.bot)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
            for cog_name, cog in self.bot.cogs.items():
                logger.info("jekyllate: Generating docs for {}".format(cog_name))
                with z.open(cog_name.lower() + '.md', mode='w') as f:
                    docs = jekyll.format(cog, ctx)
                    docs_b = docs.encode('utf8')
                    f.write(docs_b)

        logger.info("jekyllate: Sending file...")
        buf.seek(0)
        filename = re.sub(r'[^A-Za-z0-9_\- ]', self.config.name) + '-jekyll.zip'
        filename = filename.replace(' ', '-')
        file = discord.File(buf, filename=filename)
        await ctx.send(file=file)


def setup(bot):
    bot.add_cog(CoreCog(bot))
    bot.add_cog(RoleManager(bot))
