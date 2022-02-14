import sys
import asyncio
import logging
from typing import Type, Union
from types import MethodType

import discord
from discord.ext import commands
from discord.ext.commands import Context

from kaztron import KazCog
from kaztron.errors import *
from kaztron.utils.cogutils import *

logger = logging.getLogger(__name__)


class CmdErrStr:
    def __init__(self):
        self.command = ".???"
        self.message = "<#???:???> No message"
        self.traceback = "(no traceback)"
        self.exception = "(unknown exception)"
        self.usage = "(Unable to retrieve usage information)"
        self.help = ".help"


class ErrorHandler:
    error_handlers = {}
    command_error_handlers = {}
    command_invoke_handlers = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def event_handler(cls, exc: Type[BaseException], event=None):
        """
        Decorator for event exception handlers.

        Function signature: async def handler(self, exc: Exception, event: str, *args, **kwargs)

        Arguments are those passed to that event's handler.

        :param exc: Exception class to handle
        :param event: Optional. Only call this handler if triggered on this event. Default: None
            (all events).
        :return:
        """
        def decorator(func):
            cls.error_handlers[(exc, event)] = func
            return func
        return decorator

    @classmethod
    def command_handler(cls, exc: Type[BaseException]):
        """
        Decorator for command exception handlers.

        Function signature: async def handler(self, ctx: Context, exc: Exception, strings)

        :param exc: Exception class to handle
        :return:
        """
        def decorator(func):
            cls.command_error_handlers[exc] = func
            return func
        return decorator

    @classmethod
    def invoke_handler(cls, exc: Type[BaseException]):
        """
        Decorator for command invoke exception handlers.

        Function signature: async def handler(self, ctx: Context, exc: Exception, strings)

        :param exc: Root exception class to handle
        :return:
        """
        def decorator(func):
            cls.command_invoke_handlers[exc] = func
            return func
        return decorator


class ErrorHandlerCog(ErrorHandler, KazCog):
    def __init__(self, bot):
        super().__init__(bot, 'core')
        self.bot.event(self.on_error)  # register this as a global event handler, not just local

    async def on_error(self, event, *args, **kwargs):
        exc_info = sys.exc_info()
        if exc_info[0] is KeyboardInterrupt:
            logger.warning("Interrupted by user (SIGINT)")
            raise exc_info[1]
        elif exc_info[0] is asyncio.CancelledError:  # scheduler events, usually
            raise exc_info[1]
        elif exc_info[0] is BotNotReady:
            logger.warning(f"{exc_info[1].args[0]}: Event {event} called before on_ready: ignoring")
            return

        # global logging of error
        log_msg = "{}({}, {})".format(
            event,
            ', '.join(repr(arg) for arg in args),
            ', '.join(key + '=' + repr(value) for key, value in kwargs.items()))
        logger.exception("Error occurred in " + log_msg)
        await self.bot.channel_out.send_split("[ERROR] In {}\n\n{}\n\nSee log files.".format(
            log_msg, logutils.exc_log_str(exc_info[1])))

        try:
            handler = MethodType(self.error_handlers[(exc_info[0], event)], self)
        except KeyError:
            try:
                handler = MethodType(self.error_handlers[(exc_info[0], None)], self)
            except KeyError:
                handler = self.default_error_handler

        await handler(exc_info[1], event, *args, **kwargs)

    async def default_error_handler(self, exc: BaseException, event: str, *args, **kwargs):
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

    @KazCog.listener(ready_only=False)
    async def on_command_error(self, ctx: commands.Context, exc: Exception, force=False):
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
        strings = CmdErrStr()
        strings.command = get_command_str(ctx)
        strings.message = logutils.message_log_str(ctx.message)
        strings.traceback = logutils.tb_log_str(exc)
        strings.exception = logutils.exc_log_str(exc)
        strings.help = get_help_str(ctx)

        if not force and hasattr(ctx.command, "on_error"):
            return

        if ctx is not None and ctx.command is not None:
            strings.usage = get_usage_str(ctx)

        # find first matching handler in dict
        for exctype, f in self.command_error_handlers.items():
            if isinstance(exc, exctype):
                handler = MethodType(f, self)
                break
        else:
            handler = self.default_command_handler

        try:
            await handler(ctx, exc, strings)
        finally:
            # if set, delete the message
            try:
                if ctx.command.kt_delete_on_fail:
                    await ctx.message.delete()
                    logger.info("on_command_error: Deleted invoking message.")
            except AttributeError:
                pass  # kt_delete_on_fail not set: this is fine
            except discord.errors.DiscordException:
                logger.exception("Can't delete invoking message!")
                try:
                    ch = ctx.channel
                    await ctx.bot.channel_out.send(
                        f"Cannot delete invoking message in {ch.mention}: {ch.jump_url}")
                except discord.DiscordException:
                    logger.exception("Exception occurred while sending log message.")

    @ErrorHandler.command_handler(commands.CommandOnCooldown)
    async def cooldown_handler(self, ctx: Context, exc: commands.CommandOnCooldown, s: CmdErrStr):
        await ctx.reply(f"`{s.command}` is on cooldown! "
                        f"Try again in {max(exc.retry_after, 1.0):.0f} seconds.")

    @ErrorHandler.command_handler(commands.CommandInvokeError)
    async def command_invoke_dispatcher(self, ctx: Context, exc: commands.CommandInvokeError,
                                        s: CmdErrStr):
        """
        Handles all command invoke errors. Extracts the root exception of the invoke error and
        dispatches to an appropriate sub-handler.
        """
        root_exc = exc.__cause__ if exc.__cause__ is not None else exc
        s.traceback = logutils.tb_log_str(root_exc)
        s.exception = logutils.exc_log_str(root_exc)

        # find first matching handler in dict
        for exctype, f in self.command_invoke_handlers.items():
            if isinstance(root_exc, exctype):
                handler = MethodType(f, self)
                break
        else:
            handler = self.default_invoke_handler

        await handler(ctx, root_exc, s)

    @ErrorHandler.invoke_handler(KeyboardInterrupt)
    async def keyboard_interrupt_handler(self, ctx: Context, exc: KeyboardInterrupt, s: CmdErrStr):
        logger.warning("Interrupted by user (SIGINT)")
        raise exc

    @ErrorHandler.invoke_handler(discord.Forbidden)
    async def forbidden_handler(self, ctx: Context, exc: discord.Forbidden, s: CmdErrStr):
        if exc.code == DiscordErrorCodes.CANNOT_PM_USER:
            author: discord.Member = ctx.author
            err_msg = f"Can't PM user (FORBIDDEN): {author!s} {author.id}"
            logger.warning(err_msg)
            logger.debug(s.traceback)
            await ctx.reply(
                "You seem to have PMs from this server disabled or you've blocked me. "
                "Please make sure I can PM you to use this command.")
            await self.bot.channel_out.send("[WARNING] " + err_msg)
        else:
            await self.http_exception_handler(ctx, exc, s)

    @ErrorHandler.invoke_handler(discord.HTTPException)
    async def http_exception_handler(self, ctx: Context, exc: discord.HTTPException, s: CmdErrStr):
        # API errors
        err_msg = f'While executing command {s.command}: Discord API error {exc!s}'
        logger.error(err_msg + "\n\n" + s.traceback)
        await self.bot.channel_out.send_split(f"[ERROR] {err_msg}\n\nSee log files.")
        await ctx.reply("An error occurred! Let a mod know so we can investigate.")

    async def default_invoke_handler(self, ctx: Context, exc: Exception, s: CmdErrStr):
        logger.error(f"While executing command {s.command}\n\n{s.traceback}")
        await self.bot.channel_out.send_split(
            f"[ERROR] While executing command {s.command}: {s.exception}\n\nSee log files.")
        await ctx.reply("An error occurred! Let a mod know so we can investigate.")

    @ErrorHandler.command_handler(commands.DisabledCommand)
    async def disabled_command_handler(self, ctx: Context, exc: commands.CommandOnCooldown,
                                       s: CmdErrStr):
        # No need to log this on Discord - not something mods need to be aware of
        # No need to inform user of this - prevents spam, "disabled" commands could just not exist
        msg = f"Attempt to use disabled command: {s.command}"
        logger.warning(msg)

    @ErrorHandler.command_handler(ModOnlyError)
    @ErrorHandler.command_handler(AdminOnlyError)
    async def mod_only_handler(self, ctx: Context, exc: Union[ModOnlyError, AdminOnlyError],
                               s: CmdErrStr):
        if isinstance(exc, ModOnlyError):
            errname = "user not a moderator"
        elif isinstance(exc, AdminOnlyError):
            errname = "user not an admin"
        else:
            errname = "user not ???"

        err_msg = f"Unauthorised user for this command ({s.command}): {errname}"
        logger.warning(err_msg)
        await self.bot.channel_out.send('[WARNING] ' + err_msg)

        err_str = logutils.exc_msg_str(exc,
            "Only moderators may use that command." if isinstance(exc, ModOnlyError) else
            "Only administrators may use that command.")
        await ctx.reply(err_str)

    @ErrorHandler.command_handler(UnauthorizedUserError)
    @ErrorHandler.command_handler(commands.CheckFailure)
    async def check_handler(self, ctx: Context,
                            exc: Union[UnauthorizedUserError, commands.CheckFailure],
                            s: CmdErrStr):
        err_msg = f"Check failed on command: {s.command!r}"
        logger.warning(f'{err_msg}\n\n{s.traceback}')
        await self.bot.channel_out.send_split(f'[WARNING] {err_msg}\n\n{s.exception}')

        err_str = logutils.exc_msg_str(exc,
            "*(Dev note: Implement error handler with more precise reason)*")
        await ctx.reply("Sorry, you're not allowed to use that command: " + err_str)

    @ErrorHandler.command_handler(UnauthorizedChannelError)
    async def channel_handler(self, ctx: Context, exc: UnauthorizedChannelError, s: CmdErrStr):
        err_msg = "Unauthorised channel for this command: {!r}".format(s.command)
        logger.warning(err_msg)
        await self.bot.channel_out.send_split('[WARNING] ' + err_msg)
        err_str = logutils.exc_msg_str(exc, "Command not allowed in this channel.")
        await ctx.reply("Sorry, you can't use that command in this channel: " + err_str)

    @ErrorHandler.command_handler(commands.NoPrivateMessage)
    async def pm_handler(self, ctx: Context, exc: commands.NoPrivateMessage, s: CmdErrStr):
        # No need to log this on Discord, spammy and isn't something mods need to be aware of
        logger.warning(f"Attempt to use non-PM command in PM: {s.command}")
        await ctx.send("Sorry, you can't use that command in PM.")

    bad_argument_map = {
        'Converting to "int" failed.':
            'Parameter must be a whole number (`0`, `1`, `2`, `-1`, etc.).',
        'Converting to "NaturalInteger" failed.':
            'Parameter must be a whole number (`0`, `1`, `2`, `-1`, etc.).',
        'Converting to "float" failed.':
            'Parameter must be a whole or decimal number (`0`, `1`, `3.14`, `-2.71`, etc.)'
    }

    @ErrorHandler.command_handler(commands.BadArgument)
    async def bad_arg_handler(self, ctx: Context, exc: commands.BadArgument, s: CmdErrStr):
        exc_msg = logutils.exc_msg_str(exc, '(No error message).')
        log_msg = f"Bad argument passed in command: {s.command}\n{exc_msg}"
        logger.warning(log_msg)

        # do some user-friendliness message remapping
        exc_msg = self.bad_argument_map[exc_msg] if exc_msg in self.bad_argument_map else exc_msg
        await ctx.reply(
            f"Oops! I don't understand some of the information you typed for this command: "
            f"{exc_msg} "
            f"Check that you've typed it correctly, or type {s.help} for help. "
            f"**Usage:** `{s.usage}`\n\n")
        # No need to log a user mistake to mods

    @ErrorHandler.command_handler(commands.TooManyArguments)
    async def num_args_handler(self, ctx: Context, exc: commands.TooManyArguments, s: CmdErrStr):
        msg = f"Too many parameters passed in command: {s.command}"
        logger.warning(msg)
        await ctx.reply(
            f"Oops! You gave too many parameters for this command. "
            f"Check that you've typed it correctly, or type {s.help} for help. "
            f"**Usage:** `{s.usage}`")
        # No need to log a user mistake to mods

    @ErrorHandler.command_handler(commands.MissingRequiredArgument)
    async def missing_args_handler(self, ctx: Context, exc: commands.MissingRequiredArgument,
                                   s: CmdErrStr):
        msg = f"Missing required parameters in command: {s.command}"
        logger.warning(msg)
        await ctx.reply(
            f"Oops! You didn't specify enough information for this command. "
            f"Add the missing parameters, or type {s.help} for help. "
            f"**Usage:** `{s.usage}`")
        # No need to log a user mistake to mods

    @ErrorHandler.command_handler(BotNotReady)
    async def bot_not_ready_handler(self, ctx: Context, exc: BotNotReady, s: CmdErrStr):
        try:
            cog_name = exc.args[0]
        except IndexError:
            cog_name = 'unknown'
        logger.warning(f"Attempted to use command while cog {cog_name} is not ready: {s.command}")
        await ctx.reply(
            f"Sorry, I'm still loading the {cog_name} module! Try again in a few seconds.")

    @ErrorHandler.command_handler(BotCogError)
    async def bot_cog_handler(self, ctx: Context, exc: BotCogError, s: CmdErrStr):
        try:
            cog_name = exc.args[0]
        except IndexError:
            cog_name = 'unknown'
        logger.error(f"Attempted to use command on cog in error state: {s.command}")
        await ctx.reply(
            f"Sorry, an error occurred loading the {cog_name} module! Please tell a mod/admin.")

    @ErrorHandler.command_handler(commands.CommandNotFound)
    async def not_found_handler(self, ctx: Context, exc: commands.CommandNotFound, s: CmdErrStr):
        msg = f"Unknown command: {s.command}"
        # safe to assume commands usually words - symbolic commands are rare
        # and we want to avoid emoticons ('._.', etc.), punctuation ('...') and decimal numbers
        # without leading 0 (.12) being detected
        if ctx.invoked_with and all(c.isalnum() or c in '_-' for c in ctx.invoked_with) \
                and not ctx.invoked_with[0].isdigit():
            logger.warning(msg)
            await ctx.reply(f"Sorry, I don't know the command `{ctx.invoked_with}`. "
                            f"Did you type it correctly?")

    @ErrorHandler.command_handler(commands.UserInputError)
    async def user_input_handler(self, ctx: Context, exc: commands.UserInputError, s: CmdErrStr):
        logger.warning(f"UserInputError: {s.command}\n{s.traceback}")
        await ctx.reply(exc.args[0])

    async def default_command_handler(self, ctx: Context, exc: Exception, s: CmdErrStr):
        logger.error(f"Unknown command exception occurred: {s.message}\n\n{s.traceback}")
        await ctx.reply("An unexpected error occurred! Let a mod know so we can investigate.")
        await self.bot.channel_out.send(
            f"[ERROR] Unknown error while trying to process command:\n{s.message}\n"
            f"**Error:** {exc!s}\n\nSee log files.")
