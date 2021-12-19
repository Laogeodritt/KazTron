from discord.ext import commands

__all__ = ('DiscordErrorCodes', 'BotNotReady', 'BotCogError', 'CogNotLoadedError',
           'UnauthorizedUserError', 'ModOnlyError', 'AdminOnlyError', 'UnauthorizedChannelError')


class DiscordErrorCodes:
    # https://discordapp.com/developers/docs/topics/opcodes-and-status-codes
    CANNOT_PM_USER = 50007


class BotNotReady(commands.CommandError):
    pass


class BotCogError(commands.CommandError):
    pass


class CogNotLoadedError(RuntimeError):
    pass


class UnauthorizedUserError(commands.CheckFailure):
    pass


class ModOnlyError(UnauthorizedUserError):
    pass


class AdminOnlyError(UnauthorizedUserError):
    pass


class UnauthorizedChannelError(commands.CheckFailure):
    pass
