import traceback

import discord
from kaztron.utils.datetime import format_timestamp as _format_timestamp

__all__ = ('message_log_str', 'exc_msg_str', 'exc_log_str', 'tb_log_str')


def message_log_str(message: discord.Message) -> str:
    """
    Convert a :cls:`discord.Message` object to a string suitable for logging or tracing the message.
    Format looks like:

    [2012-01-01 12:34:56] <#channel:username#1234> "Message here"
    """
    return "[{}] <#{!s}:{!s}> {!r}"\
        .format(_format_timestamp(message),
                message.channel, message.author, message.content)


def exc_msg_str(exception, default="") -> str:
    """
    Extract the exception's message, or its str representation, or the default message, in order of
    priority.
    """
    try:
        msg = exception.args[0]
    except (AttributeError, IndexError):
        msg = None

    if not msg or not isinstance(msg, str):
        msg = str(exception).strip()

    return msg if msg else default


def exc_log_str(exception) -> str:
    """
    Format an exception as a "nice" one-liner string (does not include stack trace).
    """
    return "{}: {!s}".format(type(exception).__name__, exception)


def tb_log_str(exception) -> str:
    """
    Format an exception as a full traceback.
    """
    return "".join(traceback.format_exception(None, exception, exception.__traceback__))
