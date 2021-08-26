import functools
from unittest.mock import Mock, create_autospec

import pytest

from kaztron.config import KaztronConfig, ReadOnlyError, ConfigKeyError, JsonFileStrategy

config_data = {
    'core': {
        'name': 'ConfigTest',
        'extensions': ['a', 'b', 'c', 'd', 'e'],
        'channel_request': '123456789012345678'
    },
    'discord': {
        'playing': 'status',
        'limit': 5,
        'structure': {'a': 1, 'b': 2, 'c': 3}
    }
}


class ConfigFixture:
    mock_strategy: Mock = None
    mock_read: Mock = None
    mock_write: Mock = None
    config: KaztronConfig = None


def write_test(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        for cc in list(args) + list(kwargs.values()):
            if isinstance(cc, ConfigFixture):
                break
        else:
            raise Exception("Can't find ConfigFixture for write_test decorator")

        if cc.config.read_only:
            with pytest.raises(ReadOnlyError):
                return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return decorator


@pytest.fixture(params=[True, False])
def config(request, mocker) -> ConfigFixture:
    f = ConfigFixture()
    f.mock_strategy = create_autospec(JsonFileStrategy)
    f.mock_strategy.return_value.filename = 'test.json'

    f.mock_read = f.mock_strategy.return_value.read
    f.mock_read.return_value = config_data

    f.mock_write = f.mock_strategy.return_value.write
    f.config = KaztronConfig(
        filename='test.json',
        file_strategy=f.mock_strategy,
        read_only=request.param)
    return f


@pytest.fixture
def config_file_not_found(mocker) -> ConfigFixture:
    import errno
    f = ConfigFixture()
    f.mock_strategy = create_autospec(JsonFileStrategy)
    f.mock_strategy.return_value.filename = 'nope.json'

    def read_side_effect():
        raise OSError(errno.ENOENT, 'errmsg', 'nope.json')

    f.mock_read = f.mock_strategy.return_value.read
    f.mock_read.return_value = config_data
    f.mock_read.side_effect = read_side_effect

    f.mock_write = f.mock_strategy.return_value.write
    return f


# noinspection PyShadowingNames
class TestConfig:
    # Untested:
    # - File write (checks function call only)

    def test_init(self, config: ConfigFixture):
        config.mock_strategy.assert_called_once_with('test.json')
        config.mock_read.assert_called_once()

    def test_read_non_existent_file(self, config_file_not_found: ConfigFixture):
        config = config_file_not_found
        config.config = KaztronConfig(
            filename='nope.json',
            file_strategy=config.mock_strategy,
            read_only=False)
        config.mock_strategy.assert_called_once_with('nope.json')
        config.mock_read.assert_called_once()
        config.mock_write.assert_called_once()

    def test_read_non_existent_file_read_only(self, config_file_not_found: ConfigFixture):
        config = config_file_not_found
        with pytest.raises(OSError):
            config.config = KaztronConfig(
                filename='nope.json',
                file_strategy=config.mock_strategy,
                read_only=True)
        config.mock_strategy.assert_called_once_with('nope.json')
        config.mock_read.assert_called_once()
        config.mock_write.assert_not_called()

    def test_prop_data(self, config: ConfigFixture):
        assert config.config.data == config_data

    def test_get_real_values(self, config: ConfigFixture):
        assert config.config.get(('core', 'name')) == 'ConfigTest'
        assert config.config.get(('discord', 'limit')) == 5
        assert config.config.get(('discord', 'structure')) == {'a': 1, 'b': 2, 'c': 3}
        assert config.config.get(('discord', 'structure', 'c')) == 3

    def test_get_default_values(self, config: ConfigFixture):
        assert config.config.get(('core', 'asdfjkl;'), False) is False
        assert config.config.get(('core', 'qwerty'), 'hippo') == 'hippo'

    def test_get_default_none(self, config: ConfigFixture):
        assert config.config.get(('core', 'nonexistent'), None) is None

    def test_get_nonexistent(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            assert config.config.get(('asdf', 'jklx'))
        with pytest.raises(ConfigKeyError):
            assert config.config.get(('core', 'jklx'))
        with pytest.raises(ConfigKeyError):
            assert config.config.get(('discord', 'structure', 'd'))

    @write_test
    def test_set_existing_key(self, config: ConfigFixture):
        assert config.config.get(('core', 'name')) == 'ConfigTest'
        config.config.set(('core', 'name'), 'Chloe')
        assert config.config.get(('core', 'name')) == 'Chloe'

    @write_test
    def test_set_and_write(self, config: ConfigFixture):
        config.mock_write.reset_mock()
        config.config.set(('core', 'name'), 'Chloe')
        assert config.config.get(('core', 'name')) == 'Chloe'
        config.config.write()
        config.mock_write.assert_called_once()

    @write_test
    def test_set_new_key(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            config.config.get(('core', 'flamingo'))
        config.config.set(('core', 'flamingo'), 'pink')
        assert config.config.get(('core', 'flamingo')) == 'pink'

    @write_test
    def test_set_new_section(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            config.config.get(('asdf',))
        config.config.set(('asdf',), {'pink': True, 'blue': False})
        assert config.config.get(('asdf', 'pink')) is True

    @write_test
    def test_set_make_path(self, config: ConfigFixture):
        with pytest.raises(ConfigKeyError):
            config.config.get(('asdf', 'jkl;', 'qwer', 'uiop'))
        config.config.set(('asdf', 'jkl;', 'qwer', 'uiop'), 100, make_path=True)
        assert config.config.get(('asdf', 'jkl;', 'qwer', 'uiop')) == 100

    @write_test
    def test_notify(self, config: ConfigFixture):
        config.mock_write.reset_mock()
        config.config.write()
        config.mock_write.assert_not_called()

        config.config.notify()
        config.config.write()
        config.mock_write.assert_called_once()

    def test_strings(self, config: ConfigFixture):
        # just to make sure these don't raise errors - no string checking, can be checked manually
        print(str(config.config))
        print(repr(config.config))
