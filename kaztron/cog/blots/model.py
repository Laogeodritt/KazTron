from enum import Enum

from kaztron.driver import database as db
from kaztron.utils.discord import user_mention

Base = db.declarative_base()


class ProjectType(Enum):
    words = 0
    script = 1
    visual = 2


class User(Base):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, db.Sequence('user_id_seq'), primary_key=True, nullable=False)
    discord_id = db.Column(db.String(24), unique=True, nullable=False, index=True)
    project_type = db.Column(db.Enum(ProjectType), default=ProjectType.words)
    check_ins = db.relationship('CheckIn', foreign_keys='CheckIn.user_id', back_populates='user')
    is_exempt = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return "<User(user_id={:d}, discord_id={!r}, project_type={}, is_exempt={!s}>" \
            .format(self.user_id, self.discord_id, self.project_type.name, self.is_exempt)

    def __str__(self):
        return repr(self)

    @property
    def mention(self):
        return user_mention(self.discord_id)


class CheckIn(Base):
    __tablename__ = 'check_ins'

    MAX_MESSAGE_LEN = 1000

    id = db.Column(db.Integer, db.Sequence('checkin_id_seq'), primary_key=True)
    timestamp = db.Column(db.TIMESTAMP, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    user = db.relationship('User', lazy='joined', foreign_keys=[user_id])
    word_count = db.Column(db.Integer, nullable=False)
    project_type = db.Column(db.Enum(ProjectType), nullable=False)
    message = db.Column(db.String(MAX_MESSAGE_LEN), nullable=False)

    def __repr__(self):
        return "<CheckIn(id={:d}, timestamp={}, user_id={}, word_count={}, message={})>" \
            .format(self.id if self.id is not None else -1,
                    self.timestamp.isoformat(' '), self.user_id, self.word_count,
                    (self.message[:97] + '...') if len(self.message) > 100 else self.message)

    def __str__(self):
        raise NotImplementedError()
