# kaztron
from collections import OrderedDict
from .client import KazClient
from .kazcog import KazCog
from .scheduler import Scheduler, TaskInstance, task

__release__ = "3.0"  # release stream, usually major.minor only
__version__ = "3.0.0a1-migrate1x"

bot_info = {
    "version": __version__,
    "links": OrderedDict()
}
bot_info["links"]["Changelog"] = "https://github.com/Worldbuilding/KazTron/releases/tag/v" \
                                 + __version__
bot_info["links"]["Manual"] = "http://worldbuilding.network/kaztron/"
bot_info["links"]["GitHub"] = "https://github.com/Worldbuilding/KazTron"
bot_info["links"]["Bugs/Issues"] = "https://github.com/Worldbuilding/KazTron/issues"

cfg_core_sections = ("core", "logging")

# TODO: move defaults the fuck out of here
cfg_defaults = {
    "core": {
        "name": "UnnamedBot",
        "description": None,
        "extensions": [],
        "extensions_external": [],
        "data_dir": "",
        "info_links": [],
        "formats": {
            "date": "%Y-%m-%d",
            "datetime": "%Y-%m-%d %H:%M",
            "datetime_seconds": "%Y-%m-%d %H:%M:%S",
        },
        "daemon": {
            "enabled": False,
            "pidfile": "kaztron.pid",
            "user": "",
            "group": "",
            "log": "daemon.log",
        },
        "discord": {
            "mod_roles": [],
            "admin_roles": [],
            "mod_channels": [],
            "admin_channels": [],
            "status": [],
        },
    },
    "logging": {
        "file": "kaztron.log",
        "level": "INFO",
        "max_size_kb": 0,
        "max_backups": 0,
        "gzip_backups": True,
        "tags": {
            "discord": "INFO",
            "websockets.protocol": "INFO",
            "kaztron.config": "INFO",
            "kaztron.help_formatter": "INFO",
            "sqlalchemy.engine": "WARNING",
            "asyncprawcore": "INFO"
        }
    }
}
