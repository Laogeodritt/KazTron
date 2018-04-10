import discord
from discord.ext import commands

import kaztron.utils.datetime as utils_dt
from kaztron.utils.discord import extract_user_id


class NaturalDateConverter(commands.Converter):
    """
    Convert natural language date strings to datetime using the dateparser library.

    Note: If the string contains spaces, the user must include it in quotation marks for it to be
    considered a single argument.
    """
    def convert(self):
        date = utils_dt.parse(self.argument)
        if date is None:
            raise commands.BadArgument("Argument {!r} could not be parsed as a date string"
                .format(self.argument))
        return date


class MemberConverter2(commands.MemberConverter):
    """
    Member converter with slightly more tolerant ID inputs permitted.
    """
    def convert(self):
        try:
            s_user_id = extract_user_id(self.argument)
        except discord.InvalidArgument:
            s_user_id = self.argument
        self.argument = s_user_id
        return super().convert()


class BooleanConverter(commands.Converter):
    """ Convert true/false words to boolean. """
    true_words = ['true', 'yes', '1', 'enabled', 'enable', 'on', 'y', 'ok', 'confirm']
    false_words = ['false', 'no', '0', 'disabled', 'disable', 'off', 'n', 'null', 'none', 'cancel']

    def convert(self):
        arg = self.argument.lower()
        if arg in self.true_words:
            return True
        elif arg in self.false_words:
            return False
        else:
            raise commands.BadArgument("{!r} is not a true/false word.".format(self.argument))
