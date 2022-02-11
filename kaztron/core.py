import logging

from typing import List, Sequence
import re

import discord
from discord.ext import commands

import kaztron
from kaztron import config as cfg
from kaztron.client import CoreConfig, InfoLink
from kaztron.error_handler import ErrorHandlerCog
# from kaztron.help_formatter import DiscordHelpFormatter, JekyllHelpFormatter
# from kaztron.rolemanager import RoleManager
from kaztron.utils.cogutils import *
from kaztron.utils.datetime import format_timestamp, format_timedelta
from kaztron.utils.embeds import EmbedSplitter

logger = logging.getLogger(__name__)


class CoreState(cfg.ConfigModel):
    public_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])
    mod_links: List[InfoLink] = \
        cfg.ListField(type=cfg.ConfigModelField(type=InfoLink), default=[])


class CoreCog(kaztron.KazCog):
    """!kazhelp

    brief: Essential internal {{name}} functionality, plus bot information and control commands.
    description: |
        Essential {{name}} functionality: core setup and configuration tasks, general-purpose error
        handling for other cogs and commands, etc. It also includes commands for general bot
        information and control. The Core cog cannot be disabled.
    contents:
        - info
        - request
        - jekyllate
    """
    config: CoreConfig
    state: CoreState

    def __init__(self, bot):
        super().__init__(bot, 'core', state_model=CoreState)

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """!
        description: Check if the bot is responsive. This command is designed to be minimalist and
            provide minimal failure points, to allow verifying if the bot is at all responsive.
        """
        await ctx.send(ctx.author.mention + " Pong.")

    @commands.command()
    @checks.mod_only()
    @checks.mod_channels()
    async def version(self, ctx: commands.Context):
        """!kazhelp

        description: Provides technical bot information and links for operators/admins.
        details: Provides detailed version and runtime information on this {{name}} instance.
        """
        em = discord.Embed(color=0x80AAFF, title=self.config.name)
        em.add_field(name="KazTron Core", value=f"v{kaztron.__version__}", inline=True)
        em.add_field(name="discord.py", value=f"v{discord.__version__}", inline=True)
        em.add_field(name="Uptime", value=format_timedelta(self.bot.uptime), inline=True)

        loaded_list = (
                '\n'.join(name for name in self.bot.cogs_ready) + '\n' +
                '\n'.join(name + " (std cog)" for name in self.bot.cogs_std)
        )
        error_list      = '\n'.join(name for name in self.bot.cogs_error)
        not_loaded_list = '\n'.join(name for name in self.bot.cogs_not_ready)
        em.add_field(name="Loaded Cogs", value=loaded_list or 'None')
        em.add_field(name="Load Error", value=error_list or 'None')
        em.add_field(name="Not Loaded", value=not_loaded_list or 'None')

        for link in self.merge_info_links(kaztron.bot_links, tuple(), with_manual=True):
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        await ctx.send(ctx.author.mention, embed=em)

    @commands.group(invoke_without_command=True)
    async def info(self, ctx: commands.Context):
        """!kazhelp

        description: Provides bot info and useful links.
        details: |
            This command provides the version of the {{name}} instance currently running and links
            to documentation, the GitHub repository, and other resources for bot users.

            TIP: The links can be customised in the configuration or dynamically using the
            {{!info add}} and {{!info rem}} commands.

            NOTE: *For operators and moderators.* Use {{!version}} for technical bot info (like cog
            status) and {{!modinfo}} for mod-specific info links.
        """
        em = EmbedSplitter(color=0x80AAFF, title=self.config.name)
        em.set_footer(text="Moderators, you can customise this list!`.info add` and `.info rem`.")
        links = self.merge_info_links(self.config.public_links, self.state.public_links, True)
        for link in links:
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        for e in em.finalize():
            await ctx.send(ctx.author.mention, embed=e)

    @info.command(name='add')
    @checks.mod_only()
    async def info_add(self, ctx: commands.Context, name: str, url: str):
        """!kazhelp

        description: Add a public link to the {{!info}} command.
        details: If a link of the same name already exists, replaces it.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
            - name: url
              type: str
              description: URL of the linked resource. If it contains spaces, must be surrounded
                by double quotes.
        examples:
            - command: .info add "/r/aww on reddit" https://reddit.com/r/aww
              description: Adds a link to the /r/aww subreddit.
        """
        new_link = InfoLink(name=name, url=url)
        try:  # try to find a link of the same name
            i = next(i for i, v in enumerate(self.state.public_links) if v.name == name)
            self.state.public_links[i] = new_link
        except StopIteration:  # if same name not found
            self.state.public_links.append(new_link)
        await ctx.send(ctx.author.mention + f" Added link '{name}' {url}")

    @info.command(name='rem', aliases=['remove'])
    @checks.mod_only()
    async def info_rem(self, ctx: commands.Context, name: str):
        """!kazhelp

        description: Remove a public link from the {{!info}} command.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
        examples:
            - command: .info rem "/r/aww on reddit"
              description: Remove the link named "/r/aww on reddit".
        """
        try:
            link = next(v for v in self.state.public_links if v.name == name)
            self.state.public_links.remove(link)
        except StopIteration:  # not found
            await ctx.send(ctx.author.mention + f" **ERROR**: No link named '{name}'.")
        else:
            await ctx.send(ctx.author.mention + f" Removed link '{name}' to {link.url}")

    @commands.group(invoke_without_command=True)
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo(self, ctx: commands.Context):
        """!kazhelp
        description: Provides useful links for moderators and bot operators.
        """
        em = EmbedSplitter(color=0x80AAFF, title=self.config.name)
        em.set_footer(text="Moderators, you can customize this list!"
                           "`.modinfo add` and `.modinfo rem`.")
        links = self.merge_info_links(self.config.mod_links, self.state.mod_links, False)
        for link in links:
            em.add_field(name=link.name, value=f'[{link.name}]({link.url})', inline=True)
        for e in em.finalize():
            await ctx.send(ctx.author.mention, embed=e)

    @modinfo.command(name='add')
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo_add(self, ctx: commands.Context, name: str, url: str):
        """!kazhelp

        description: Add a link to the {{!modinfo}} command.
        details: If a link of the same name already exists, replaces it.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
            - name: url
              type: str
              description: URL of the linked resource. If it contains spaces, must be surrounded
                by double quotes.
        examples:
            - command: .modinfo add "/r/aww on reddit" https://reddit.com/r/aww
              description: Adds a link to the /r/aww subreddit.
        """
        new_link = InfoLink(name=name, url=url)
        try:  # try to find a link of the same name
            i = next(i for i, v in enumerate(self.state.mod_links) if v.name == name)
            self.state.mod_links[i] = new_link
        except StopIteration:  # if same name not found
            self.state.mod_links.append(new_link)
        await ctx.send(ctx.author.mention + f" Added mod link '{name}' {url}")

    @modinfo.command(name='rem', aliases=['remove'])
    @checks.mod_only()
    @checks.mod_channels()
    async def modinfo_rem(self, ctx: commands.Context, name: str):
        """!kazhelp

        description: Remove a link from the {{!modinfo}} command.
        parameters:
            - name: name
              type: str
              description: Name or title of the linked resource. If it contains spaces, must be
                surrounded by double quotes.
        examples:
            - command: .modinfo rem "/r/aww on reddit"
              description: Remove the link named "/r/aww on reddit".
        """
        try:
            link = next(v for v in self.state.mod_links if v.name == name)
            self.state.mod_links.remove(link)
        except StopIteration:  # not found
            await ctx.send(ctx.author.mention + f" **ERROR**: No mod link named '{name}'.")
        else:
            await ctx.send(ctx.author.mention + f" Removed mod link '{name}' to {link.url}")

    def merge_info_links(self, a: Sequence[InfoLink], b: Sequence[InfoLink], with_manual=False):
        """
        Merge InfoLink lists. If links have the same name, b will overwrite a. If with_manual is
        True, the manual is also added (but may be overwritten by both a and b).
        """
        if with_manual:
            manual = [InfoLink(name='Manual', url=self.config.manual_url)]
            return self.merge_info_links(self.merge_info_links(manual, a), b)

        links = {link.name: link for link in a}
        links.update({link.name: link for link in b})
        return list(links.values())

    @commands.command(pass_context=True, aliases=['bug'])
    @commands.cooldown(rate=3, per=120)
    async def issue(self, ctx, *, content: str):
        """!kazhelp

        description: Submit a bug report or feature request to the {{name}} bot team.
        details: |
            Everyone can use this command, but please make sure that your submission is **clear**,
            and submitted as **one issue per command** (don't split up one issue into several
            commands or submit several issues in one command).

            If you're reporting a bug, include the answers to the questions:

            * What were you trying to do? Include the *exact* command you tried to use, if any.
            * What error messages were given by the bot? *Exact* message.
            * Where and when did this happen? Ideally, link the message itself (message menu >
              Copy Link).

            If you're requesting a feature, make sure to answer these questions:

            * What do you want the feature to do?
            * Why is this useful? Who do you expect will use it? How and where will they use it?

            IMPORTANT: Any submissions made via this system may be tracked publicly. By submitting
            a request via this system, you give us permission to post your username and message,
            verbatim or altered, to a public database for the purpose of project management.

            IMPORTANT: Abuse of this command may be treated like spam, and enforced accordingly.
        examples:
            - command: |
                .request When trying to use the `.roll 3d20` command, I get the message:
                "An error occurred! Details have been logged. Let a mod know so we can investigate."

                This only happens with d20, I've tried d12 and d6 with no problems.
                The last time this happened was here: <direct link to message>
        """
        em = EmbedSplitter(color=0x80AAFF, auto_truncate=True)
        em.set_author(name="User Issue Submission")
        em.add_field(name="User", value=ctx.message.author.mention, inline=True)
        try:
            em.add_field(name="Channel", value=ctx.message.channel.mention, inline=True)
        except AttributeError:  # probably a private channel
            em.add_field(name="Channel", value=ctx.message.channel, inline=True)
        em.add_field(name="Timestamp", value=format_timestamp(ctx.message), inline=True)
        em.add_field(name="Content", value=content, inline=False)
        for e in em.finalize():
            await self.config.discord.channel_issues.send(embed=em)
        await ctx.send(ctx.author.mention + " Your issue was submitted to the bot DevOps team. "
                       "If you have any questions or if there's an urgent problem, "
                       "please feel free to contact the moderators directly.")

    @commands.command(pass_context=True)
    @checks.mod_only()
    @checks.mod_channels()
    async def jekyllate(self, ctx: commands.Context):
        """!kazhelp

        description: Generate Jekyll-compatible markdown documentation for all loaded cogs.
        """
        import os
        import io
        import zipfile

        jekyll = JekyllHelpFormatter(self.bot.kaz_help_parser, self.bot)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
            for cog_name, cog in self.bot.cogs.items():
                logger.info("jekyllate: Generating docs for {}".format(cog_name))
                with z.open(cog_name.lower() + '.md', mode='w') as f:
                    docs = jekyll.format(cog, ctx)
                    docs_b = docs.encode('utf8')
                    f.write(docs_b)

        logger.info("jekyllate: Sending file...")
        buf.seek(0)
        filename = re.sub(r'[^A-Za-z0-9_\- ]', self.config.name) + '-jekyll.zip'
        filename = filename.replace(' ', '-')
        file = discord.File(buf, filename=filename)
        await ctx.send(file=file)


def setup(bot):
    bot.add_cog(CoreCog(bot))
    bot.add_cog(ErrorHandlerCog(bot))
#    bot.add_cog(RoleManager(bot))
