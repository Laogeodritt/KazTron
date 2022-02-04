from .core import TestCoreCog, TestStandardCog


def setup(bot):
    bot.add_cog(TestCoreCog(bot))
    bot.add_cog(TestStandardCog(bot))
