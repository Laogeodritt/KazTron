# kaztron
from collections import OrderedDict
from .client import KazClient
from .kazcog import KazCog
from .scheduler import Scheduler, TaskInstance, task

__release__ = "3.0"  # release stream, usually major.minor only
__version__ = "3.0.0a1-migrate1x"

bot_links = (
    client.InfoLink(name="Changelog",
        url="https://github.com/Worldbuilding/KazTron/releases/tag/v" + __version__),
    client.InfoLink(name="Manual", url="http://worldbuilding.network/kaztron/"),
    client.InfoLink(name="GitHub", url="https://github.com/Worldbuilding/KazTron"),
    client.InfoLink(name="Bugs/Issues", url="https://github.com/Worldbuilding/KazTron/issues"),
)

# Core sections that should be ignored during extension loading
cfg_core_sections = ("core", "logging")
