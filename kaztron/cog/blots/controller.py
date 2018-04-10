import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Union, AbstractSet, Sequence, Mapping, \
    MutableMapping

import discord
from discord.ext import commands
from sqlalchemy import orm

from kaztron.config import KaztronConfig
# noinspection PyUnresolvedReferences
from kaztron.driver import database as db
from kaztron.cog.blots.model import *
from kaztron.driver.database import make_error_handler_decorator
from kaztron.utils.datetime import get_weekday, parse as dt_parse

logger = logging.getLogger(__name__)

db_file = 'blots.sqlite'

engine = None
Session = db.sessionmaker()


def init_db():
    global engine
    engine = db.make_sqlite_engine(db_file)
    Session.configure(bind=engine)
    Base.metadata.create_all(engine)


on_error_rollback = make_error_handler_decorator(lambda *args, **kwargs: args[0].session, logger)


class MilestoneInfo:
    MULTIPLE_ROLES = discord.Object(id=0)

    def __init__(self,
                 user: discord.Member,
                 check_in: CheckIn,
                 current_role: Optional[Sequence[discord.Role]],
                 target_role: discord.Role):
        self.user = user
        self.check_in = check_in
        self.current_roles = list(current_role) if current_role is not None else None
        self.target_role = target_role

    @property
    def milestone_changed(self):
        return len(self.current_roles) != 1 or self.current_roles[0] != self.target_role


class BlotsController:
    """
    :param server: Discord server that the bot/BLOTS module is to manage.
    :param config: System-wide KazTron config (not the state.json)
    :param milestone_map: Role mappings for each project type. The role mappings map the
        {MINIMUM wordcount value: corresponding role}.
    """
    def __init__(self,
                 server: discord.Server,
                 config: KaztronConfig,
                 milestone_map: Dict[ProjectType, Dict[discord.Role, int]]):
        self.server = server
        self.config = config
        self.session = Session()
        self.checkin_weekday = self.config.get('blots', 'check_in_weekday')
        self.checkin_time = dt_parse(self.config.get('blots', 'check_in_time')).time()
        # this is ordered in decreasing order of minimum
        self.milestone_map = {}  # type: Dict[ProjectType, Dict[discord.Role, int]]
        for p, inner_map in milestone_map.items():
            # noinspection PyTypeChecker
            self.milestone_map[p] = OrderedDict(
                sorted(inner_map.items(), key=lambda i: i[1], reverse=True))
            logger.info("Milestone map for {}: {{{}}}".format(
                p.name,
                ', '.join(['{0.name}: {1:d}'
                           .format(r, v) for r, v in self.milestone_map[p].items()])
            ))

    @on_error_rollback
    def get_user(self, member: discord.Member):
        """
        Get the database user for a given member.
        :param member:
        :return:
        :raise db.orm_exc.MultipleResultsFound: database is buggered
        """
        try:
            return self.session.query(User).filter(User.discord_id == member.id).one()
        except db.orm_exc.NoResultFound:
            user = User(discord_id=member.id)
            self.session.add(user)
            self.session.commit()
            return user

    def get_exempt_users(self):
        return self.session.query(User).filter_by(is_exempt=True).all()

    def get_check_in_week(self, included_date: datetime=None) -> Tuple[datetime, datetime]:
        """
        Get the start and end times for a check-in week that includes the passed date.
        """
        end = get_weekday(included_date, self.checkin_weekday, future=True).date()
        start = end - timedelta(days=7)
        return datetime.combine(start, self.checkin_time), datetime.combine(end, self.checkin_time)

    def query_check_ins(self, *,
                        member: discord.Member=None,
                        included_date: datetime=None) -> List[CheckIn]:
        """
        Query all check-ins.

        :param member: If given, filter by this user.
        :param included_date: If given, query only for the check-in week that includes this date.
        :return: List of check-ins in chronological order.
        :raise orm.exc.NoResultFound: no results found
        """
        log_conds = []
        query = self.session.query(CheckIn)
        if member:
            query = query.join(User).filter(User.discord_id == member.id)
            log_conds.append("member {}".format(member))

        if included_date:
            start, end = self.get_check_in_week(included_date)
            query = query.filter(db.and_(start <= CheckIn.timestamp, CheckIn.timestamp <= end))
            log_conds.append("period {} to {}".format(start.isoformat(' '), end.isoformat(' ')))

        results = query.order_by(CheckIn.timestamp).all()

        try:
            results[0]
        except IndexError:
            raise orm.exc.NoResultFound

        logger.info("query_check_ins: Found {:d} records for {}"
            .format(len(results), ' and '.join(log_conds)))
        return results

    def query_latest_check_ins(self) -> Dict[User, CheckIn]:
        results = self.session \
            .query(CheckIn, db.func.max(CheckIn.timestamp).label('timestamp_max')) \
            .group_by(CheckIn.user_id) \
            .all()
        logger.info("query_latest_check_ins: Found {:d} records".format(len(results)))
        return {self.server.get_member(check_in.user.discord_id): check_in
                for check_in, _ in results}

    def get_check_in_report(self, included_date: datetime=None) \
            -> Dict[discord.Member, Optional[CheckIn]]:
        """
        Get a report of all server users and their check-ins in a given report week.

        Note that the user list is the CURRENT list. This report does not account for users who
        were not members at the time of the check-in.

        :param included_date: The check-in week to report for must include this date.
        :return: Tuple. First element is a map of users and their latest check-in. Second element
            is a list of users who did not check in.
        """
        logger.info("get_check_in_report: Generating report (included_date={})"
            .format(included_date.isoformat(' ')))

        check_ins = self.query_check_ins(included_date=included_date)

        member_check_in_map = {m: None for m in self.server.members}
        for c in check_ins:
            member_check_in_map[self.server.get_member(c.user.discord_id)] = c

        try:
            del member_check_in_map[None]  # for any users who are no longer on the server
        except KeyError:
            pass

        for user in self.session.query(User).filter_by(is_exempt=True).all():
            try:
                del member_check_in_map[self.server.get_member(user.discord_id)]
            except KeyError:
                pass
        return member_check_in_map

    def get_milestone_report(self) -> Mapping[Union[discord.Role, None], Sequence[MilestoneInfo]]:
        """
        Get a report of all users who have checked in and what their milestone role should be.

        :return: Ordered map of TARGET role to full milestone information. This map will
        always include a None key for any users who have not submitted valid check-ins.
        """
        logger.info("get_milestone_report: Generating report")

        # set up output structure with the full list of milestone roles
        milestones = OrderedDict() \
            # type: MutableMapping[Union[discord.Role, None], List[MilestoneInfo]]
        for role in self.get_milestone_roles():
            milestones[role] = []
        milestones[None] = []
        logger.debug("get_milestone_report: Detected milestone roles: {!r}"
            .format([r.name for r in milestones.keys() if r is not None]))

        check_in_map = self.query_latest_check_ins()
        for member in self.server.members:
            check_in = check_in_map.get(member, None)
            user = check_in.user if check_in else self.get_user(member)
            if user.is_exempt:
                continue
            project_type = check_in.project_type if check_in else user.project_type
            ms_info = MilestoneInfo(
                user=member,
                check_in=check_in,
                current_role=self.get_milestone_role(member, project_type),
                target_role=self.find_target_milestone(check_in) if check_in else None
            )
            milestones[ms_info.target_role].append(ms_info)
        return milestones

    def get_milestone_role(self, member: discord.Member, p_type: ProjectType)\
            -> List[discord.Role]:
        """ Return member's Milestone roles. """
        role_intersect = set(self.milestone_map[p_type].keys()) & set(member.roles)
        return list(role_intersect)

    def get_milestone_roles(self) -> List[discord.Role]:
        """ Get a set of all milestone roles. """
        ms_roles = []
        for p_type in ProjectType:
            for role in self.milestone_map[p_type].keys():
                if role not in ms_roles:
                    ms_roles.append(role)
        return ms_roles

    def find_target_milestone(self, check_in: CheckIn) -> discord.Role:
        """
        Get the milestone the user should be at for a given check-in.
        :raise KeyError: can't find matching milestone role for check-in's wordcount value
        """
        ms_map = self.milestone_map[check_in.project_type]
        for role, v in ms_map.items():
            if check_in.word_count >= v:
                return role
        raise KeyError("No milestone role for check_in: {!r} user: {!r}"
            .format(check_in, check_in.user))

    @on_error_rollback
    def save_check_in(self, *,
            member: discord.Member,
            word_count: int,
            message: str,
            timestamp: datetime=None) -> CheckIn:
        """ Store a new check-in. """
        if timestamp is None:
            timestamp = datetime.utcnow()

        if len(message) > CheckIn.MAX_MESSAGE_LEN:
            raise commands.BadArgument(
                "Message too long (max {:d} chars)".format(CheckIn.MAX_MESSAGE_LEN))

        logger.info("Inserting check-in by {}...".format(member.nick or member.name))
        user = self.get_user(member)
        check_in = CheckIn(timestamp=timestamp, user_id=user.user_id, word_count=word_count,
            project_type=user.project_type, message=message[:CheckIn.MAX_MESSAGE_LEN])
        logger.debug("save_checkin: {!r}".format(CheckIn))
        self.session.add(check_in)
        self.session.commit()
        return check_in

    @on_error_rollback
    def set_user_type(self, member: discord.Member, p_type: ProjectType):
        logger.info("Setting user's project type to {}".format(p_type.name))
        self.get_user(member).project_type = p_type
        self.session.commit()

    @on_error_rollback
    def set_user_exempt(self, member: discord.Member, is_exempt=False):
        logger.info("Setting user {} {} from checkin"
            .format(member.name, "exempt" if is_exempt else "not exempt"))
        self.get_user(member).is_exempt = is_exempt
        self.session.commit()
