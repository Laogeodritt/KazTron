from kaztron.utils import datetime as dt

from datetime import timedelta, datetime


class TestParseTimeDelta:
    def test_single_long_unit(self):
        assert dt.parse_timedelta("0 seconds") == timedelta(seconds=0)
        assert dt.parse_timedelta("1 second") == timedelta(seconds=1)
        assert dt.parse_timedelta("75 seconds") == timedelta(seconds=75)
        assert dt.parse_timedelta("15 minutes") == timedelta(minutes=15)
        assert dt.parse_timedelta("15 hours") == timedelta(hours=15)
        assert dt.parse_timedelta("1 day") == timedelta(days=1)

    def test_single_short_unit(self):
        assert dt.parse_timedelta("0s") == timedelta(seconds=0)
        assert dt.parse_timedelta("1s") == timedelta(seconds=1)
        assert dt.parse_timedelta("75 s") == timedelta(seconds=75)
        assert dt.parse_timedelta("15m") == timedelta(minutes=15)
        assert dt.parse_timedelta("15 h") == timedelta(hours=15)
        assert dt.parse_timedelta("1 d") == timedelta(days=1)

    def test_multiple_long_unit(self):
        assert dt.parse_timedelta("1 day 12 hours 34 minutes") == \
               timedelta(days=1, hours=12, minutes=34)
        assert dt.parse_timedelta("4 hours 34 seconds") == timedelta(hours=4, seconds=34)
        assert dt.parse_timedelta("1 hour 65 seconds") == timedelta(hours=1, minutes=1, seconds=5)

    def test_multiple_short_unit(self):
        # dateparser seems not to be able to handle "d" well
        assert dt.parse_timedelta("1day 12h 34m") == timedelta(days=1, hours=12, minutes=34)
        assert dt.parse_timedelta("4h34s") == timedelta(hours=4, seconds=34)
        assert dt.parse_timedelta("1h 65m") == timedelta(hours=2, minutes=5)


class TestFormatTimeDelta:
    def test_single_value(self):
        assert dt.format_timedelta(timedelta(seconds=34), 'seconds') == '34 seconds'
        assert dt.format_timedelta(timedelta(days=1), 'seconds') == '1 day'

    def test_multiple_values(self):
        assert dt.format_timedelta(timedelta(seconds=65), 'seconds') == '1 minute 5 seconds'
        assert dt.format_timedelta(timedelta(hours=1, seconds=34), 'seconds') == '1 hour 34 seconds'
        assert dt.format_timedelta(timedelta(days=1, minutes=65), 'seconds') == \
               '1 day 1 hour 5 minutes'

    def test_resolution(self):
        assert dt.format_timedelta(timedelta(hours=1, seconds=22), 'seconds') == '1 hour 22 seconds'
        assert dt.format_timedelta(timedelta(hours=1, seconds=22), 'hours') == '1 hour'
