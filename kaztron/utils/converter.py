from discord.ext import commands as _commands

import kaztron.utils.datetime as _utils_dt
from kaztron.utils.discord import get_member as _get_member

# noinspection PyUnresolvedReferences
from discord.ext.commands.converter import *


class NaturalDateConverter(_commands.Converter):
    """
    Convert natural language date strings to datetime using the dateparser library.

    Note: If the string contains spaces, the user must include it in quotation marks for it to be
    considered a single argument.
    """
    async def convert(self, ctx: _commands.Context, argument: str):
        date = _utils_dt.parse(argument)
        if date is None:
            raise _commands.BadArgument("Parameter {!r} could not be parsed as a date string"
                .format(argument))
        return date


class FutureDateRange(_commands.Converter):
    """
    Convert a natural language date range, in the form "date1 to date2". If there is ambiguity to
    the range (e.g. implied year), then it will start in the future.
    """
    async def convert(self, ctx: _commands.Context, argument: str):
        try:
            return _utils_dt.parse_daterange(argument, future=True)
        except ValueError as e:
            raise _commands.BadArgument(e.args[0])


class DateRange(_commands.Converter):
    """
    Convert a natural language date range, in the form "date1 to date2".
    """
    async def convert(self, ctx: _commands.Context, argument: str):
        try:
            return _utils_dt.parse_daterange(argument, future=False)
        except ValueError as e:
            raise _commands.BadArgument(e.args[0])


class MemberConverter2(_commands.Converter):
    """
    Member converter with slightly more tolerant ID inputs permitted.
    """
    async def convert(self, ctx: _commands.Context, argument: str):
        return _get_member(ctx, argument)


class BooleanConverter(_commands.Converter):
    """ Convert true/false words to boolean. """
    true_words = ['true', 'yes', '1', 'enabled', 'enable', 'on', 'y', 'ok', 'confirm']
    false_words = ['false', 'no', '0', 'disabled', 'disable', 'off', 'n', 'null', 'none', 'cancel']

    async def convert(self, ctx: _commands.Context, argument: str):
        arg = argument.lower()
        if arg in self.true_words:
            return True
        elif arg in self.false_words:
            return False
        else:
            raise _commands.BadArgument("{!r} is not a true/false word.".format(argument))


class NaturalInteger(_commands.Converter):
    """
    Integer converter that is tolerant of various natural number input conventions:

    * Commas or periods as digit grouping separators
    * Period or comma as decimal point (identified as an error -> not an integer)
    * '#' prepended to an integer, for ordinals, IDs and list items.

    This converter is tolerant of three common locale conventions, along with normal Python integer
    literals, and attempts a best guess at conversion:

    * 1,000,000 (commas as thousands separator)
    * 1.000.000 (periods as thousands separator)
    * 1 000 000 (spaces as thousands separators)
    * 1000000 (Python integer literal)

    NOTE: The spaces convention may not be very useful, as with most command parameters, the space
    is used to separate parameters. These numbers would need to be enclosed in quotes by the user,
    or input as the final KEYWORD argument to the command, or manually parsed.

    NOTE: Other conventions, such as those that group by 4 digits, are currently not supported.

    There is naturally an ambiguity when it comes to decimal numbers, as the first 2 locales use
    each other's thousands separators. In the case that only one thousand separator is present, this
    converter checks if it's separating a grouping of 3 digits to validate that the input isn't
    an erroneous decimal value:

    * "1.234" interpreted as 1234
    * "1,234" interpreted as 1234
    * "1,22" interpret as a float 1.22 (error)
    * "1.22" interpreted as a float 1.22 (error)

    :raise commands.BadArgument: Cannot interpret as integer. This includes inputs that are detected
        as floating-point.
    """
    async def convert(self, ctx: _commands.Context, argument: str):
        n_str = argument.rstrip(',.').strip('#')
        try:
            return int(n_str)
        except ValueError:
            pass

        # Simple conversion didn't work, try to eliminate if it's a float first
        commas_split = n_str.split(',')
        periods_split = n_str.split('.')
        if (len(commas_split) > 1 and len(periods_split) > 1)\
                or (len(commas_split) == 2 and len(commas_split[1]) != 3)\
                or (len(periods_split) == 2 and len(periods_split[1]) != 3):
            raise _commands.BadArgument("Parameter {!r} must be an integer, not a decimal number."
                .format(n_str))
        if any(len(c) != 3 for c in commas_split[1:])\
                or any(len(c) != 3 for c in periods_split[1:])\
                or any(len(c) != 3 for c in n_str.split(' ')[1:]):
            raise _commands.BadArgument("Cannot convert {!r} to an integer.".format(n_str))

        try:
            return int(n_str.replace(',', '').replace('.', '').replace(' ', ''))
        except ValueError:
            raise _commands.BadArgument("Cannot convert {!r} to an integer.".format(n_str))
