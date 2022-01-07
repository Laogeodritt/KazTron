from typing import TYPE_CHECKING, Union
from abc import ABC

from dataclasses import dataclass
import discord

from kaztron.config.fields import Field

if TYPE_CHECKING:
    from kaztron import KazClient
    from kaztron.config import DiscordDummy

__all__ = 'GuildChannelField', 'TextChannelField', 'VoiceChannelField', 'CategoryChannelField', \
          'RoleField', 'MemberField', 'DiscordModelField'


@dataclass
class DiscordModelField(Field, ABC):
    """
    Field representing a Discord model, specified by name or ID.

    Implement serialize() using the Discord ID value.
    """
    # TODO: special handling for not caching dummy objects?
    must_exist: bool = True
    client: 'KazClient' = None

    @staticmethod
    def _convert_dummy(value) -> 'DiscordDummy':
        from kaztron.config import DiscordDummy  # only typechecking importing globally
        if isinstance(value, int):
            return DiscordDummy(id=value)
        elif isinstance(value, str):
            return DiscordDummy(name=value)
        else:
            raise TypeError(value)

    def serialize(self, value) -> int:
        return value.id


@dataclass
class GuildChannelField(DiscordModelField):
    """
    Field representing any guild channel, specified by name, by #name or by ID.
    When writing to file, always stores the ID.

    A Guild channel is a text, voice or category channel that exists in a guild. If the type of
    guild channel must be constrained, use :cls:`TextChannelField`, :cls:`VoiceChannelField` or
    :cls:`CategoryChannelField`.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.abc.GuildChannel, 'DiscordDummy']:
        if isinstance(value, int):
            ch = self.client.get_channel(value)
            errmsg = f"Channel ID {value} not found"
        else:
            ch = discord.utils.get(self.client.get_all_channels(), name=value)
            errmsg = f"Channel #{value} not found"

        if ch is None:
            if self.must_exist and self.client.is_ready():
                raise ValueError(errmsg)
            else:
                ch = self._convert_dummy(value)

        return ch


@dataclass
class TextChannelField(GuildChannelField):
    """
    Field representing a text channel, specified by name, by #name or by ID. When writing to file,
    always stores the ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.TextChannel, 'DiscordDummy']:
        from kaztron.config import DiscordDummy
        obj = super().convert(value)
        if not isinstance(obj, (discord.TextChannel, DiscordDummy)):
            raise TypeError("must be a text channel", value)
        return obj


@dataclass
class VoiceChannelField(GuildChannelField):
    """
    Field representing a voice channel, specified by name, by #name or by ID. When writing to file,
    always stores the ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.VoiceChannel, 'DiscordDummy']:
        from kaztron.config import DiscordDummy
        obj = super().convert(value)
        if not isinstance(obj, (discord.VoiceChannel, DiscordDummy)):
            raise TypeError("must be a voice channel", value)
        return obj


@dataclass
class CategoryChannelField(GuildChannelField):
    """
    Field representing a category channel, specified by name, by #name or by ID. When writing to
    file, always stores the ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.CategoryChannel, 'DiscordDummy']:
        from kaztron.config import DiscordDummy
        obj = super().convert(value)
        if not isinstance(obj, (discord.CategoryChannel, DiscordDummy)):
            raise TypeError("must be a category", value)
        return obj


@dataclass
class RoleField(DiscordModelField):
    """
    Field representing a role, specified by name or by ID. When writing to file, always stores the
    ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.Role, 'DiscordDummy']:
        guild = self.client.guild
        errmsg = 'unknown error'

        if guild is None:
            role = None
        elif isinstance(value, int):
            role = self.client.guild.get_role(value)
            errmsg = f'Role ID {value} not found'
        else:
            role = discord.utils.get(self.client.guild.roles, name=value)
            errmsg = f'Role \'{value}\' not found'

        if role is None:
            if self.must_exist and guild is not None:
                raise ValueError(errmsg)
            role = self._convert_dummy(value)
        return role


@dataclass
class MemberField(DiscordModelField):
    """
    Field representing a Discord Member on the current guild, specified by name or by ID.
    When writing to file, always stores the ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.User, 'DiscordDummy']:
        guild = self.client.guild

        try:
            member = guild.get_member(value) or guild.get_member_named(value)
        except AttributeError:
            member = None

        if member is None:
            if self.must_exist and guild is not None:
                value_str = str(value) if isinstance(value, int) else f"'{value}'"
                raise ValueError(f'Member {value_str} not found')
            member = self._convert_dummy(value)
        return member
