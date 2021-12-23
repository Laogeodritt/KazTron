import discord

from typing import Dict, List
from datetime import timedelta

from kaztron import config as cfg
from kaztron.utils.discord import Limits

__all__ = ['Logging', 'InfoLink', 'BotStatus', 'CoreDaemon', 'CoreConfig', 'CoreDiscord',
           'CoreFormats']


class Logging(cfg.ConfigModel):
    file: str = cfg.StringField(default="kaztron.log")
    level: int = cfg.LogLevelField(default="INFO")
    max_size_kb: int = cfg.IntegerField(default=0)
    max_backups: int = cfg.IntegerField(default=0)
    gzip_backups: bool = cfg.BooleanField(default=False)
    tags: Dict[str, int] = cfg.DictField(type=cfg.LogLevelField(),
        default={
            "discord": "INFO",
            "websockets.protocol": "INFO",
            "kaztron.config": "INFO",
            "kaztron.help_formatter": "INFO",
            "sqlalchemy.engine": "WARNING",
            "asyncprawcore": "INFO"
        })


class InfoLink(cfg.ConfigModel):
    name: str = cfg.StringField(required=True, len=Limits.EMBED_FIELD_NAME)
    url: str = cfg.StringField(required=True, len=Limits.EMBED_FIELD_VALUE - 16)


class BotStatus(cfg.ConfigModel):
    name: str = cfg.StringField(required=True, len=Limits.STATUS)
    emoji = cfg.PrimitiveField(required=False)  # TODO: emoji model?


class CoreFormats(cfg.ConfigModel):
    date: str = cfg.StringField(default="%Y-%m-%d")
    datetime: str = cfg.StringField(default="%Y-%m-%d %H:%M")
    datetime_seconds: str = cfg.StringField(default="%Y-%m-%d %H:%M:%S")


class CoreDaemon(cfg.ConfigModel):
    enabled: bool = cfg.BooleanField(default=False)
    pidfile: str = cfg.StringField(default="pid.lock")
    user: str = cfg.StringField()
    group: str = cfg.StringField()
    log: str = cfg.StringField(default="daemon.log")


class CoreDiscord(cfg.ConfigModel):
    token: str = cfg.StringField(required=True)
    channel_output: discord.TextChannel = cfg.TextChannelField(required=True, lazy=False)
    channel_public: discord.TextChannel = cfg.TextChannelField(required=True, lazy=False)
    channel_issues: discord.TextChannel = cfg.TextChannelField(required=True, lazy=False)
    mod_roles: List[discord.Role] = cfg.ListField(type=cfg.RoleField(), default=[])
    admin_roles: List[discord.Role] = cfg.ListField(type=cfg.RoleField(), default=[])
    mod_channels: List[discord.TextChannel] = cfg.ListField(type=cfg.TextChannelField())
    admin_channels: List[discord.TextChannel] = cfg.ListField(type=cfg.TextChannelField())
    status: List[BotStatus] = cfg.ListField(type=cfg.ConfigModelField(type=BotStatus), default=[])
    status_change_interval: timedelta = cfg.TimeDeltaField(default=timedelta(seconds=0))


class CoreConfig(cfg.ConfigModel):
    name: str = cfg.StringField(required=True)
    description: str = cfg.StringField(default=None)
    data_dir: str = cfg.StringField(default='.')  # TODO: IMPLEMENT ME
    manual_url: str = cfg.StringField(required=False, default="")

    public_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])
    mod_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])

    formats: CoreFormats = cfg.ConfigModelField(type=CoreFormats)
    daemon: CoreDaemon = cfg.ConfigModelField(type=CoreDaemon)
    discord: CoreDiscord = cfg.ConfigModelField(type=CoreDiscord)
