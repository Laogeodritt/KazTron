"""
Patches for discord.py v1.x.

These are all hacky as hell and I'm not proud of 'em.
"""

import functools
from types import MethodType
from enum import Enum

from discord.ext import commands


class Patches(Enum):
    smart_quotes = 0
    command_logging = 1
    everyone_filter = 2
    mobile_embeds = 3


def apply_patches(client: commands.Bot, excl=tuple()):
    """
    Apply all patches. See the Patches enum.

    :param client: Client to patch.
    :param excl: List of patches to exclude.
    :return:
    """
    if Patches.smart_quotes not in excl:
        patch_smart_quotes(client)
    if Patches.mobile_embeds not in excl:
        patch_mobile_embeds()


def patch_smart_quotes(client: commands.Bot):
    """
    Patch to convert smart quotes to ASCII quotes when processing commands in discord.py

    Because iOS by default is stupid and inserts smart quotes, and not everyone configures their
    mobile device to be SSH-friendly. WTF, Apple, way to ruin basic input expectations across your
    *entire* OS.
    """
    old_process_commands = client.process_commands
    conversion_map = {
        '\u00ab': '"',
        '\u00bb': '"',
        '\u2018': '\'',
        '\u2019': '\'',
        '\u201a': '\'',
        '\u201b': '\'',
        '\u201c': '"',
        '\u201d': '"',
        '\u201e': '"',
        '\u201f': '"',
        '\u2039': '\'',
        '\u203a': '\'',
        '\u2042': '"'
    }

    @functools.wraps(client.process_commands)
    async def new_process_commands(self, message, *args, **kwargs):
        for f, r in conversion_map.items():
            message.content = message.content.replace(f, r)
        return await old_process_commands(message)
    # noinspection PyArgumentList
    client.process_commands = MethodType(new_process_commands, client)


def patch_mobile_embeds():
    """
    Patch to fix a stupid, stupid Android!Discord bug where it doesn't consider Embed fields when
    calculating the width of the embed. Yup. Sigh.

    It results in a minimum-width embed that looks like a grey and coloured vertical line, which
    scrolls forever because all of the field contents are wrapping like hell.
    """
    from discord.embeds import Embed
    from discord.abc import Messageable
    old_send = Messageable.send

    @functools.wraps(Messageable.send)
    async def new_send(self, content=None, **kwargs):
        e = kwargs.get('embed', None)

        def min_len(x):
            return x and x is not Embed.Empty and len(x) >= 80
        hr = r'_' * 80
        hr_ts = r'_' * 60

        if e is not None and e.fields and not (min_len(e.description) or min_len(e.author.name) or
                                               min_len(e.title)):
            if e.footer is None or e.footer.text == Embed.Empty:
                e.set_footer(text=hr if e.timestamp is Embed.Empty else hr_ts)
            elif hr not in e.footer.text:
                e.set_footer(text=hr + '\n' + e.footer.text)
        return await old_send(self, content, **kwargs)
    # noinspection PyArgumentList
    Messageable.send = new_send
