import pytest
from unittest.mock import Mock

import re
from datetime import datetime, timezone, timedelta

from kaztron.config.fields import *

primitive_data = ("string", 69, 3.1415926535, [1, 2, 3, 4], {'a': 1, 'b': 2})


class MyClass:
    pass


class TestPrimitiveField:
    def test_default_constructor(self):
        PrimitiveField()

    def test_full_constructor(self):
        f = PrimitiveField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert_primitives(self):
        f = PrimitiveField()
        for d in primitive_data:
            assert f.convert(d) == d

    def test_serialise_primitives(self):
        f = PrimitiveField()
        for d in primitive_data:
            assert f.serialize(d) == d

    def test_serialise_non_primitive(self):
        f = PrimitiveField()
        with pytest.raises(TypeError):
            # noinspection PyTypeChecker
            f.serialize(MyClass())


class TestStringField:
    def test_default_constructor(self):
        StringField()

    def test_full_constructor(self):
        f = StringField(name='blah', default='default', required=True, lazy=False,
                        len=24, minlen=4, validation=re.compile(r'asdf[^g]'), validation_help='k')
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = StringField()
        for d in ("", "asdf", "1234", "a" * 16384):
            assert f.convert(d) == d

    def test_convert_non_string(self):
        f = StringField()
        with pytest.raises(TypeError):
            f.convert(1234)

    def test_convert_maxlength_check(self):
        f = StringField(len=5)
        with pytest.raises(ValueError):
            f.convert('012345')
        assert f.convert('01234') == '01234'
        assert f.convert('') == ''

    def test_convert_minlength_check(self):
        f = StringField(minlen=5)
        with pytest.raises(ValueError):
            f.convert('0123')
        assert f.convert('01234') == '01234'
        assert f.convert('012345') == '012345'

    def test_convert_window_length_check(self):
        f = StringField(len=24, minlen=5)
        # too short
        with pytest.raises(ValueError):
            f.convert('')
        with pytest.raises(ValueError):
            f.convert('0123')
        # too long
        with pytest.raises(ValueError):
            f.convert('a' * 25)
        with pytest.raises(ValueError):
            f.convert('a' * 26)
        # just right
        assert f.convert('a' * 24) == 'a' * 24
        assert f.convert('a' * 5) == 'a' * 5
        assert f.convert('a' * 12) == 'a' * 12

    def test_convert_validation_check(self):
        f = StringField(validation=re.compile(r'abcd?1234?'), validation_help="msg")
        with pytest.raises(ValueError):
            f.convert('asdf0987')
        assert f.convert('abc1234') == 'abc1234'

    def test_serialise(self):
        f = StringField()
        for d in ("", "asdf", "1234", "a" * 16384):
            assert f.serialize(d) == d

    def test_serialise_non_string(self):
        f = StringField()
        with pytest.raises(TypeError):
            f.serialize(1234)

    def test_serialise_maxlength_check(self):
        f = StringField(len=5)
        with pytest.raises(ValueError):
            f.serialize('012345')
        assert f.serialize('01234') == '01234'
        assert f.serialize('') == ''

    def test_serialise_minlength_check(self):
        f = StringField(minlen=5)
        with pytest.raises(ValueError):
            f.serialize('0123')
        assert f.serialize('01234') == '01234'
        assert f.serialize('012345') == '012345'

    def test_serialise_window_length_check(self):
        f = StringField(len=24, minlen=5)
        # too short
        with pytest.raises(ValueError):
            f.serialize('')
        with pytest.raises(ValueError):
            f.serialize('0123')
        # too long
        with pytest.raises(ValueError):
            f.serialize('a' * 25)
        with pytest.raises(ValueError):
            f.serialize('a' * 26)
        # just right
        assert f.serialize('a' * 24) == 'a' * 24
        assert f.serialize('a' * 5) == 'a' * 5
        assert f.serialize('a' * 12) == 'a' * 12

    def test_serialise_validation_check(self):
        f = StringField(validation=re.compile(r'abcd?1234?'), validation_help="msg")
        with pytest.raises(ValueError):
            f.serialize('asdf0987')
        assert f.serialize('abc1234') == 'abc1234'


class TestIntegerField:
    def test_default_constructor(self):
        IntegerField()

    def test_full_constructor(self):
        f = IntegerField(name='blah', default='default', required=True, lazy=False,
            min=-128, max=127)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = IntegerField()
        for d in (-5, 0, 5, 1234567890000):
            assert f.convert(d) == d

    def test_convert_max_check(self):
        f = IntegerField(max=127)
        with pytest.raises(ValueError):
            f.convert(128)
        assert f.convert(5) == 5
        assert f.convert(127) == 127
        assert f.convert(-1000) == -1000

    def test_convert_min_check(self):
        f = IntegerField(min=0)
        with pytest.raises(ValueError):
            f.convert(-1)
        assert f.convert(0) == 0
        assert f.convert(128) == 128

    def test_convert_window_check(self):
        f = IntegerField(min=-128, max=127)
        with pytest.raises(ValueError):
            f.convert(-129)
        with pytest.raises(ValueError):
            f.convert(-10000)
        with pytest.raises(ValueError):
            f.convert(129)
        with pytest.raises(ValueError):
            f.convert(10000)
        assert f.convert(-128) == -128
        assert f.convert(127) == 127
        assert f.convert(0) == 0

    def test_serialise(self):
        f = IntegerField()
        for d in (-5, 0, 5, 1234567890000):
            assert f.serialize(d) == d

    def test_serialise_max_check(self):
        f = IntegerField(max=127)
        with pytest.raises(ValueError):
            f.serialize(128)
        assert f.serialize(5) == 5
        assert f.serialize(127) == 127
        assert f.serialize(-1000) == -1000

    def test_serialise_min_check(self):
        f = IntegerField(min=0)
        with pytest.raises(ValueError):
            f.serialize(-1)
        assert f.serialize(0) == 0
        assert f.serialize(128) == 128

    def test_serialise_window_check(self):
        f = IntegerField(min=-128, max=127)
        with pytest.raises(ValueError):
            f.serialize(-129)
        with pytest.raises(ValueError):
            f.serialize(-10000)
        with pytest.raises(ValueError):
            f.serialize(129)
        with pytest.raises(ValueError):
            f.serialize(10000)
        assert f.serialize(-128) == -128
        assert f.serialize(127) == 127
        assert f.serialize(0) == 0


class TestConstrainedIntegerField:
    def test_default_constructor(self):
        ConstrainedIntegerField()

    def test_full_constructor(self):
        f = ConstrainedIntegerField(name='blah', default='default', required=True, lazy=False,
            min=-128, max=127)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = ConstrainedIntegerField()
        for d in (-5, 0, 5, 1234567890000):
            assert f.convert(d) == d

    def test_convert_max_check(self):
        f = ConstrainedIntegerField(max=127)
        assert f.convert(128) == 127
        assert f.convert(10000) == 127
        assert f.convert(5) == 5
        assert f.convert(127) == 127
        assert f.convert(-1000) == -1000

    def test_convert_min_check(self):
        f = ConstrainedIntegerField(min=0)
        assert f.convert(-1000) == 0
        assert f.convert(-1) == 0
        assert f.convert(0) == 0
        assert f.convert(128) == 128

    def test_convert_window_check(self):
        f = ConstrainedIntegerField(min=-128, max=127)
        assert f.convert(-129) == -128
        assert f.convert(-10000) == -128
        assert f.convert(129) == 127
        assert f.convert(10000) == 127

        assert f.convert(-128) == -128
        assert f.convert(127) == 127
        assert f.convert(0) == 0

    def test_serialise(self):
        f = ConstrainedIntegerField()
        for d in (-5, 0, 5, 1234567890000):
            assert f.serialize(d) == d

    def test_serialise_max_check(self):
        f = ConstrainedIntegerField(max=127)
        assert f.serialize(128) == 127
        assert f.serialize(10000) == 127
        assert f.serialize(5) == 5
        assert f.serialize(127) == 127
        assert f.serialize(-1000) == -1000

    def test_serialise_min_check(self):
        f = ConstrainedIntegerField(min=0)
        assert f.serialize(-1000) == 0
        assert f.serialize(-1) == 0
        assert f.serialize(0) == 0
        assert f.serialize(128) == 128

    def test_serialise_window_check(self):
        f = ConstrainedIntegerField(min=-128, max=127)
        assert f.serialize(-129) == -128
        assert f.serialize(-10000) == -128
        assert f.serialize(129) == 127
        assert f.serialize(10000) == 127

        assert f.serialize(-128) == -128
        assert f.serialize(127) == 127
        assert f.serialize(0) == 0


class TestFloatField:
    def test_default_constructor(self):
        FloatField()

    def test_full_constructor(self):
        f = FloatField(name='blah', default='default', required=True, lazy=False,
            min=-120.5, max=127.5)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = FloatField()
        for d in (-5.27, 0.0, 5.27, 1234567890000.):
            assert f.convert(d) == d

    def test_convert_max_check(self):
        f = FloatField(max=127.0)
        with pytest.raises(ValueError):
            f.convert(127.1)
        assert f.convert(5.2) == 5.2
        assert f.convert(127.0) == 127.0
        assert f.convert(-1234.56) == -1234.56

    def test_convert_min_check(self):
        f = FloatField(min=-0.5)
        with pytest.raises(ValueError):
            f.convert(-1.2)
        assert f.convert(0.0) == 0.0
        assert f.convert(128.24) == 128.24

    def test_convert_window_check(self):
        f = FloatField(min=-120.55, max=100.57)
        with pytest.raises(ValueError):
            f.convert(-120.65)
        with pytest.raises(ValueError):
            f.convert(-10000.0)
        with pytest.raises(ValueError):
            f.convert(100.58)
        with pytest.raises(ValueError):
            f.convert(10000.)
        assert f.convert(-120.55) == -120.55
        assert f.convert(100.57) == 100.57
        assert f.convert(0.) == 0.

    def test_convert_specials_not_allowed(self):
        f = FloatField(allow_special=False)
        with pytest.raises(ValueError):
            f.convert(f.INF)

    def test_convert_specials_allowed_with_limit(self):
        f = FloatField(max=100.57, allow_special=True)
        with pytest.raises(ValueError):
            f.convert(f.INF)

    def test_convert_specials_allowed(self):
        f = FloatField(allow_special=True)
        assert f.convert(f.INF) is f.INF

    def test_serialise(self):
        f = FloatField()
        for d in (-5.27, 0.0, 5.27, 1234567890000.):
            assert f.serialize(d) == d

    def test_serialise_max_check(self):
        f = FloatField(max=127.0)
        with pytest.raises(ValueError):
            f.serialize(127.1)
        assert f.serialize(5.2) == 5.2
        assert f.serialize(127.0) == 127.0
        assert f.serialize(-1234.56) == -1234.56

    def test_serialise_min_check(self):
        f = FloatField(min=-0.5)
        with pytest.raises(ValueError):
            f.serialize(-1.2)
        assert f.serialize(0.0) == 0.0
        assert f.serialize(128.24) == 128.24

    def test_serialise_window_check(self):
        f = FloatField(min=-120.55, max=100.57)
        with pytest.raises(ValueError):
            f.serialize(-120.65)
        with pytest.raises(ValueError):
            f.serialize(-10000.0)
        with pytest.raises(ValueError):
            f.serialize(100.58)
        with pytest.raises(ValueError):
            f.serialize(10000.)
        assert f.serialize(-120.55) == -120.55
        assert f.serialize(100.57) == 100.57
        assert f.serialize(0.) == 0.

    def test_serialise_specials_not_allowed(self):
        f = FloatField(allow_special=False)
        with pytest.raises(ValueError):
            f.serialize(f.INF)

    def test_serialise_specials_allowed_with_limit(self):
        f = FloatField(max=100.57, allow_special=True)
        with pytest.raises(ValueError):
            f.serialize(f.INF)

    def test_serialise_specials_allowed(self):
        f = FloatField(allow_special=True)
        assert f.serialize(f.INF) is f.INF


class TestConstrainedFloatField:
    def test_default_constructor(self):
        ConstrainedFloatField()

    def test_full_constructor(self):
        f = ConstrainedFloatField(name='blah', default='default', required=True, lazy=False,
            min=-128.5, max=127.5)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = ConstrainedFloatField()
        for d in (-5.27, 0.0, 5.27, 1234567890000.):
            assert f.convert(d) == d

    def test_convert_max_check(self):
        f = ConstrainedFloatField(max=120.55)
        assert f.convert(128.97) == 120.55
        assert f.convert(10000) == 120.55
        assert f.convert(5.2) == 5.2
        assert f.convert(120.55) == 120.55
        assert f.convert(-1000.) == -1000.

    def test_convert_min_check(self):
        f = ConstrainedFloatField(min=-1.2)
        assert f.convert(-1000.0) == -1.2
        assert f.convert(-1.5) == -1.2
        assert f.convert(0.5) == 0.5
        assert f.convert(128.77) == 128.77

    def test_convert_window_check(self):
        f = ConstrainedFloatField(min=-121.5, max=125.5)
        assert f.convert(-129.7) == -121.5
        assert f.convert(-10000.) == -121.5
        assert f.convert(126.5) == 125.5
        assert f.convert(10000.) == 125.5

        assert f.convert(-121.5) == -121.5
        assert f.convert(125.5) == 125.5
        assert f.convert(5.2) == 5.2

    def test_convert_specials_not_allowed(self):
        f = ConstrainedFloatField(allow_special=False)
        with pytest.raises(ValueError):
            f.convert(f.INF)

    def test_convert_specials_allowed_with_limit(self):
        f = ConstrainedFloatField(max=100.57, allow_special=True)
        assert f.convert(f.INF) == 100.57

    def test_convert_specials_allowed(self):
        f = ConstrainedFloatField(allow_special=True)
        assert f.convert(f.INF) is f.INF

    def test_serialise(self):
        f = ConstrainedFloatField()
        for d in (-5.27, 0.0, 5.27, 1234567890000.):
            assert f.serialize(d) == d

    def test_serialise_max_check(self):
        f = ConstrainedFloatField(max=120.55)
        assert f.serialize(128.97) == 120.55
        assert f.serialize(10000) == 120.55
        assert f.serialize(5.2) == 5.2
        assert f.serialize(120.55) == 120.55
        assert f.serialize(-1000.) == -1000.

    def test_serialise_min_check(self):
        f = ConstrainedFloatField(min=-1.2)
        assert f.serialize(-1000.0) == -1.2
        assert f.serialize(-1.5) == -1.2
        assert f.serialize(0.5) == 0.5
        assert f.serialize(128.77) == 128.77

    def test_serialise_window_check(self):
        f = ConstrainedFloatField(min=-121.5, max=125.5)
        assert f.serialize(-129.7) == -121.5
        assert f.serialize(-10000.) == -121.5
        assert f.serialize(126.5) == 125.5
        assert f.serialize(10000.) == 125.5

        assert f.serialize(-121.5) == -121.5
        assert f.serialize(125.5) == 125.5
        assert f.serialize(5.2) == 5.2

    def test_serialise_specials_not_allowed(self):
        f = ConstrainedFloatField(allow_special=False)
        with pytest.raises(ValueError):
            f.serialize(f.INF)

    def test_serialise_specials_allowed_with_limit(self):
        f = ConstrainedFloatField(max=100.57, allow_special=True)
        assert f.convert(f.INF) == 100.57

    def test_serialise_specials_allowed(self):
        f = ConstrainedFloatField(allow_special=True)
        assert f.serialize(f.INF) is f.INF

class TestSecondsDeltaField:
    def test_default_constructor(self):
        SecondsDeltaField()

    def test_full_constructor(self):
        f = SecondsDeltaField(name='blah', default=timedelta(seconds=2), required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == timedelta(seconds=2)
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = SecondsDeltaField()
        assert f.convert(123.3125) == timedelta(seconds=123.3125)

    def test_serialize(self):
        f = SecondsDeltaField()
        assert f.serialize(timedelta(days=1, seconds=34, microseconds=312500)) == 86434.3125


class TestBooleanField:
    def test_default_constructor(self):
        BooleanField()

    def test_full_constructor(self):
        f = BooleanField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_booleans(self):
        f = BooleanField()
        assert f.convert(True) is True
        assert f.convert(False) is False
        assert f.serialize(True) is True
        assert f.serialize(False) is False

    def test_strings(self):
        f = BooleanField()
        for s in ('0', 'off', 'no', 'disabled', 'false'):
            assert f.convert(s) is False
            assert f.serialize(s) is False
        for s in ('1', 'on', 'yes', 'enabled', 'true'):
            assert f.convert(s) is True
            assert f.serialize(s) is True
        with pytest.raises(ValueError):
            f.convert('asdf')
        with pytest.raises(ValueError):
            f.serialize('asdf')

    def test_other(self):
        f = BooleanField()
        assert f.convert([]) is False
        assert f.convert(['a', 'b']) is True
        assert f.serialize([]) is False
        assert f.serialize(['a', 'b']) is True

        class A:
            pass

        assert f.convert(A()) is True
        assert f.serialize(A()) is True


class TestTimestampField:
    TIMESTAMP = 1628154000
    DATETIME = datetime(2021, 8, 5, 9, 0, 0, tzinfo=timezone.utc)

    def test_default_constructor(self):
        TimestampField()

    def test_full_constructor(self):
        f = TimestampField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = TimestampField()
        assert f.convert(self.TIMESTAMP) == self.DATETIME
        assert f.convert(self.TIMESTAMP).tzinfo == timezone.utc  # must be timezone aware

    def test_serialise(self):
        f = TimestampField()
        assert f.serialize(self.DATETIME) == self.TIMESTAMP


class TestDatetimeField:
    DATETIME = datetime(2021, 8, 5, 9, 0, 0, tzinfo=timezone.utc)
    DATETIME_NAIVE = datetime(2021, 8, 5, 9, 0, 0)
    SERIALIZED = '2021-08-05T09:00:00+00:00'
    SERIALIZED_NAIVE = '2021-08-05T09:00:00'

    DATETIME_EDT = datetime(2021, 8, 5, 9, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
    SERIALIZED_EDT = '2021-08-05T09:00:00-04:00'

    def test_default_constructor(self):
        DatetimeField()

    def test_full_constructor(self):
        f = DatetimeField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = DatetimeField()
        assert f.convert(self.SERIALIZED) == self.DATETIME
        assert f.convert(self.SERIALIZED).tzinfo == timezone.utc  # must be timezone aware

    def test_convert_naive(self):
        f = DatetimeField()
        assert f.convert(self.SERIALIZED_NAIVE) == self.DATETIME
        assert f.convert(self.SERIALIZED_NAIVE).tzinfo == timezone.utc  # must be timezone aware

    def test_convert_with_timezone(self):
        f = DatetimeField()
        assert f.convert(self.SERIALIZED_EDT) == self.DATETIME_EDT
        assert f.convert(self.SERIALIZED_EDT).tzinfo == timezone(timedelta(hours=-4))

    def test_serialise(self):
        f = DatetimeField()
        assert f.serialize(self.DATETIME) == self.SERIALIZED

    def test_serialise_naive(self):
        f = DatetimeField()
        assert f.serialize(self.DATETIME_NAIVE) == self.SERIALIZED  # with UTC timezone

    def test_serialise_with_timezone(self):
        f = DatetimeField()
        assert f.serialize(self.DATETIME_EDT) == self.SERIALIZED_EDT


class TestTimeDeltaField:
    def test_default_constructor(self):
        TimeDeltaField()

    def test_full_constructor(self):
        f = TimeDeltaField(name='blah', default=timedelta(seconds=24), required=True, lazy=False,
            min_seconds=0, max_seconds=2424)
        assert f.name == 'blah'
        assert f.default == timedelta(seconds=24)
        assert f.required
        assert not f.lazy

    def test_convert_string(self):
        f = TimeDeltaField()
        assert f.convert("1 day 12 hours 34 minutes") == timedelta(days=1, hours=12, minutes=34)
        assert f.convert("15m") == timedelta(minutes=15)
        assert f.convert("75 seconds") == timedelta(seconds=75)
        # dateparser has a hard time handling "1d 12h 34m"
        assert f.convert("1 day 12h 34m") == timedelta(days=1, hours=12, minutes=34)
        assert f.convert("4h34s") == timedelta(hours=4, seconds=34)

    def test_convert_int_as_seconds(self):
        f = TimeDeltaField()
        assert f.convert(123) == timedelta(seconds=123)
        assert f.convert(0) == timedelta(seconds=0)

    def test_convert_float_as_seconds(self):
        f = TimeDeltaField()
        assert f.convert(0.0) == timedelta(seconds=0.0)
        assert f.convert(12.5) == timedelta(seconds=12.5)

    def test_serialize(self):
        f = TimeDeltaField()
        assert f.serialize(timedelta(seconds=65)) == '1 minute 5 seconds'
        assert f.serialize(timedelta(hours=1, seconds=22)) == '1 hour 22 seconds'

    def test_limits_minimum_only(self):
        f = TimeDeltaField(min_seconds=10)
        with pytest.raises(ValueError):
            f.convert("5s")
        f.convert("10s")
        f.convert("20s")
        with pytest.raises(ValueError):
            f.serialize(timedelta(seconds=5))
        f.serialize(timedelta(seconds=10))
        f.serialize(timedelta(seconds=20))

    def test_limits_both(self):
        f = TimeDeltaField(min_seconds=10, max_seconds=20)
        with pytest.raises(ValueError):
            f.convert("5s")
        f.convert("10s")
        f.convert("20s")
        with pytest.raises(ValueError):
            f.convert("21s")

        with pytest.raises(ValueError):
            f.serialize(timedelta(seconds=5))
        f.serialize(timedelta(seconds=10))
        f.serialize(timedelta(seconds=20))
        with pytest.raises(ValueError):
            f.serialize(timedelta(seconds=20, microseconds=999999))


@pytest.fixture
def list_fixture() -> ListField:
    f = ListField()
    f.type.convert = Mock(return_value=0)
    f.type.serialize = Mock(return_value=1)
    return f


class TestListField:
    def test_default_constructor(self):
        ListField()

    def test_full_constructor(self):
        f = ListField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self, list_fixture: ListField):
        f = list_fixture
        assert f.convert([1, 2, 3, 4]) == [0, 0, 0, 0]
        assert f.type.convert.call_count == 4

    def test_convert_min_len(self, list_fixture: ListField):
        f = list_fixture
        f.min_len = 2
        assert len(f.convert([4] * 2)) == 2
        with pytest.raises(ValueError):
            f.convert([4])

    def test_convert_max_len(self, list_fixture: ListField):
        f = list_fixture
        f.max_len = 4
        assert len(f.convert([4] * 4)) == 4
        with pytest.raises(ValueError):
            f.convert([4] * 5)

    def test_convert_window_len(self, list_fixture: ListField):
        f = list_fixture
        f.min_len = 2
        f.max_len = 4
        assert len(f.convert([4] * 2)) == 2
        assert len(f.convert([4] * 3)) == 3
        assert len(f.convert([4] * 4)) == 4
        with pytest.raises(ValueError):
            f.convert([4])
        with pytest.raises(ValueError):
            f.convert([4] * 5)

    def test_serialize(self, list_fixture: ListField):
        f = list_fixture
        assert f.serialize([1, 2, 3, 4]) == [1, 1, 1, 1]
        assert f.type.serialize.call_count == 4

    def test_serialise_min_len(self, list_fixture: ListField):
        f = list_fixture
        f.min_len = 2
        assert len(f.serialize([4] * 2)) == 2
        with pytest.raises(ValueError):
            f.serialize([4])

    def test_serialise_max_len(self, list_fixture: ListField):
        f = list_fixture
        f.max_len = 4
        assert len(f.serialize([4] * 4)) == 4
        with pytest.raises(ValueError):
            f.serialize([4] * 5)

    def test_serialise_window_len(self, list_fixture: ListField):
        f = list_fixture
        f.min_len = 2
        f.max_len = 4
        assert len(f.serialize([4] * 2)) == 2
        assert len(f.serialize([4] * 3)) == 3
        assert len(f.serialize([4] * 4)) == 4
        with pytest.raises(ValueError):
            f.serialize([4])
        with pytest.raises(ValueError):
            f.serialize([4] * 5)


@pytest.fixture
def dict_fixture() -> DictField:
    f = DictField()
    f.type.convert = Mock(return_value=0)
    f.type.serialize = Mock(return_value=1)
    return f


class TestDictField:
    def test_default_constructor(self):
        DictField()

    def test_full_constructor(self):
        f = DictField(name='blah', default='default',merge_defaults=False, required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self, dict_fixture: DictField):
        f = dict_fixture
        assert f.convert({'a': 1, 'b': 2}) == {'a': 0, 'b': 0}
        assert f.type.convert.call_count == 2

    def test_serialize(self, dict_fixture: DictField):
        f = dict_fixture
        assert f.serialize({'a': 4, 'b': 3, 'c': 2, 'd': 1}) == {'a': 1, 'b': 1, 'c': 1, 'd': 1}
        assert f.type.serialize.call_count == 4
