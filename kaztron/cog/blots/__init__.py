from kaztron.cog.blots.checkin import CheckInManager
from kaztron.cog.blots.controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(CheckInManager(bot))
