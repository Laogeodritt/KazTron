import pytest

import logging
from kaztron.config.fields import *

pairs = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}


class TestLogLevelField:
    def test_default_constructor(self):
        LogLevelField()

    def test_full_constructor(self):
        f = LogLevelField(name='blah', default='default', required=True, lazy=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy

    def test_convert(self):
        f = LogLevelField()
        for s, l in pairs.items():
            assert logging.getLevelName(f.convert(s)) == s

    def test_convert_invalid(self):
        f = LogLevelField()
        with pytest.raises(KeyError):
            f.convert('THISLEVELDOESNOTEXIST')

    def test_serialise(self):
        f = LogLevelField()
        for s, l in pairs.items():
            assert f.serialize(l) == logging.getLevelName(l)

    def test_serialise_invalid(self):
        # This is a bit of a weird case - not sure if we should constrain this to a strict map
        f = LogLevelField()
        assert f.serialize(21475) == 'Level 21475'
