"""
Patches for discord.py v1.x.

These are all hacky as hell and I'm not proud of 'em.
"""

from typing import Union, Sequence, List

import functools
from types import MethodType
from enum import Enum

import discord
from discord.ext import commands

from kaztron.utils.cogutils import Limits, strutils
from kaztron.utils.embeds import EmbedSplitter


class Patches(Enum):
    smart_quotes = 0
    # command_logging = 1
    # everyone_filter = 2
    mobile_embeds = 3
    send_split = 4


def apply_patches(client: commands.Bot, excl: Sequence[Patches] = tuple()):
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
    if Patches.send_split not in excl:
        patch_messageable_send_split()


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
    async def new_process_commands(_self, message):
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


def patch_messageable_send_split():
    from discord.abc import Messageable

    async def send_split(self, contents=None, *,
                         embed: Union[discord.Embed, EmbedSplitter] = None,
                         file: discord.File = None, files: List[discord.File] = None,
                         split_lines=False, **kwargs) -> Sequence[discord.Message]:
        """
        Send a message. This method wraps the :meth:`discord.Messageable.send()` method and adds
        automatic message splitting if the contents are too long for one message.

        No parsing of Markdown is done for message splitting; this behaviour may break intended
        formatting. For messages which may contain formatting, it is suggested you parse and split
        the message instead of relying on auto-splitting.

        See also :meth:`kaztron.utils.split_chunks_on` and :meth:`kaztron.utils.natural_split` for
        manual control of splitting behaviour. See also :meth:`kaztron.utils.split_code_chunks_on`
        for splitting code blocks manually.

        See also :cls:`kaztron.utils.embeds.EmbedSplitter` for similar functionality in splitting
        embeds.

        :param contents: The content of the message to send. If this is missing, then the ``embed``
            parameter must be present.
        :param embed: The rich embed for the content. Also accepts EmbedSplitter instances, for
            automatic splitting - in this case, the EmbedSplitter will be finalized by this method.
        :param split_lines: If true, split on lines instead of words. This should only be used when
            the message contents is known to contain many line breaks; otherwise, the splitting may
            fail.
        """
        # prepare text contents
        if not contents:
            content_chunks = (contents,)
        else:
            if not split_lines:  # word splitting
                content_chunks = strutils.natural_split(contents, Limits.MESSAGE)
            else:  # line splitting
                content_chunks = strutils.split_chunks_on(contents, Limits.MESSAGE, split_char='\n')

        # prepare embed
        try:
            embed_list = embed.finalize()
        except AttributeError:
            embed_list = (embed,)

        #
        # prepare the arguments for each message to send
        #
        # strategy: output all text chunks before starting to output embed chunks
        # so the last text chunk will have the first embed chunk attached
        # this is because non-split messages usually have the embed appear after the msg -
        # should be fairly rare for both msg and embed to be split
        msgs_kwargs = []

        for content_chunk in content_chunks:
            msg_kwargs = kwargs.copy()
            msg_kwargs['content'] = content_chunk
            msgs_kwargs.append(msg_kwargs)

            # only on first message
            kwargs['reference'] = None

        msgs_kwargs[-1]['embed'] = embed_list[0]  # last text chunk has first embed

        for embed_chunk in embed_list[1:]:
            msg_kwargs = kwargs.copy()
            msg_kwargs['embed'] = embed_chunk
            msgs_kwargs.append(msg_kwargs)

        # last message only
        msgs_kwargs[-1]['file'] = file
        msgs_kwargs[-1]['files'] = files

        # finally, send all the messages and collect the returned Message objects
        return tuple([await self.send(**msg_kwargs) for msg_kwargs in msgs_kwargs])

    Messageable.send_split = send_split
