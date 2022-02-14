from kaztron import KazCog

import discord
from discord.ext import commands
from discord.ext.commands import Context

import logging


class TestLoadFailCog(KazCog):
    logger = logging.getLogger("TestLoadFailCog")

    def __init__(self, bot):
        super().__init__(bot)

    @KazCog.listener()
    async def on_ready(self):
        self.logger.info("on_ready: raising ValueError")
        raise ValueError("test error")

    @KazCog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState):
        await self.bot.channel_out.send("TestLoadFailCog "
                                        "FAIL READY_ONLY LISTENER: `on_voice_state_update`")

    @KazCog.listener(ready_only=False)
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        await self.bot.channel_out.send("TestLoadFailCog: Reaction added (OK, non-ready_only)")

    @commands.command()
    async def failed(self, ctx: Context):
        await ctx.channel.send("FAIL COG READY CHECK ON COMMAND: `.failed` executed")


def setup(bot):
    bot.add_cog(TestLoadFailCog(bot))
