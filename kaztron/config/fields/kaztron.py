from . import Field, ConfigPrimitive

import logging


class LogLevelField(Field):
    log_level_map = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
    }

    def convert(self, value: str):
        """ Convert a log level name to its value for the ``logging`` module. """
        return self.log_level_map[value.upper()]

    def serialize(self, value: int):
        """ Serialise a log level value using getLevelName. Unknown levels are returned as
        "Level %i" % value. """
        return logging.getLevelName(value)
