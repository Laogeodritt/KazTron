from kaztron import KazCog
from kaztron.utils.discord import metagroup

import discord
from discord.ext import commands
from discord.ext.commands import Context

import logging


class TestCoreCog(KazCog):
    logger = logging.getLogger("TestFailureCog")

    def __init__(self, bot):
        super().__init__(bot)

    @metagroup()
    async def say(self, ctx: Context):
        pass

    @say.command(name='log')
    async def say_log(self, ctx: Context, *, msg: str):
        await self.bot.channel_out.send(msg)

    @say.command(name='public')
    async def say_public(self, ctx: Context, *, msg: str):
        await self.bot.channel_public.send(msg)

    @say.command(name='long')
    async def say_long(self, ctx: Context):
        await ctx.channel.send_split('This is a long message. '*90)

    @KazCog.listener(ready_only=True)
    async def on_voice_state_update(self, ctx: Context,
                                    before: discord.VoiceState, after: discord.VoiceState):
        await self.bot.channel_out.send("Received voice state event update (test event pass)")


class TestStandardCog(commands.Cog):
    @commands.command()
    async def standard(self, ctx: Context):
        await ctx.channel.send('Hello, standard world!')
