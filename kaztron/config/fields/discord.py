from typing import TYPE_CHECKING, Union
from abc import ABC

from dataclasses import dataclass
import discord

from kaztron.config.fields import Field

if TYPE_CHECKING:
    from kaztron import KazClient
    from kaztron.config import DiscordDummy

__all__ = 'GuildChannelField', 'TextChannelField', 'VoiceChannelField', 'CategoryChannelField', \
          'RoleField', 'MemberField'


@dataclass
class DiscordModelField(Field, ABC):
    """
    Field representing a Discord model, specified by name or ID.

    Implement serialize() using the Discord ID value.
    """
    must_exist = True
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
        try:
            return self.client.validate_channel(value)
        except (ValueError, AttributeError):  # AttributeError in case client hasn't been set
            if self.must_exist:
                raise
            return self._convert_dummy(value)


@dataclass
class TextChannelField(GuildChannelField):
    """
    Field representing a text channel, specified by name, by #name or by ID. When writing to file,
    always stores the ID.

    :ivar must_exist: If True, gives a ValueError if the channel is not found. If False, returns a
        :cls:`kaztron.config.DiscordDummy` object wrapping the raw value.
    """

    def convert(self, value) -> Union[discord.TextChannel, 'DiscordDummy']:
        obj = super().convert(value)
        if not isinstance(obj, discord.TextChannel):
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
        obj = super().convert(value)
        if not isinstance(obj, discord.VoiceChannel):
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
        obj = super().convert(value)
        if not isinstance(obj, discord.CategoryChannel):
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
        try:
            return self.client.validate_role(value)
        except (ValueError, AttributeError):  # AttributeError in case client hasn't been set
            if self.must_exist:
                raise
            return self._convert_dummy(value)


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
            if member is None:
                value_str = str(value) if isinstance(value, int) else f"'{value}'"
                raise ValueError(f'Member {value_str} not found')
        except (ValueError, AttributeError):  # AttributeError in case client hasn't been set
            if self.must_exist:
                raise
            return self._convert_dummy(value)
