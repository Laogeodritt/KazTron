import pytest
from unittest.mock import Mock

from kaztron.config.fields import *
from kaztron.config import DiscordDummy


class Dummy:
    def __init__(self, name, id_):
        self.id: int = id_
        self.name: str = name


class MockClient:
    def __init__(self):
        pass

    def get_channel(self, id_):
        return Dummy("channel", id_)

    def get_all_channels(self):
        channels = [Dummy("exists", 123456789012345678), Dummy("other", 876543210987654321)]
        for channel in channels:
            yield channel


class NotFoundClient(MockClient):
    def __init__(self):
        pass

    def get_channel(self, id_):
        return None


class TestGuildChannelField:
    def test_default_constructor(self):
        GuildChannelField()

    def test_full_constructor(self):
        f = GuildChannelField(name='blah', default='default', required=True, lazy=False,
            must_exist=False)
        assert f.name == 'blah'
        assert f.default == 'default'
        assert f.required
        assert not f.lazy
        assert not f.must_exist

    def test_convert_id(self):
        f = GuildChannelField()
        f.client = MockClient()
        ch = f.convert(123456789012345678)
        assert isinstance(ch, Dummy)
        assert ch.id == 123456789012345678

    def test_convert_name(self):
        f = GuildChannelField()
        f.client = MockClient()
        ch = f.convert("exists")
        assert isinstance(ch, Dummy)
        assert ch.name == "exists"

    def test_convert_non_existent(self):
        f = GuildChannelField(must_exist=False)
        f.client = NotFoundClient()
        ch = f.convert(123456789012345678)
        assert ch.id == 123456789012345678

    def test_convert_name_non_existent(self):
        f = GuildChannelField(must_exist=False)
        f.client = NotFoundClient()
        ch = f.convert("not-exists")
        assert ch.name == "not-exists"

    def test_convert_non_existent_must_exist(self):
        f = GuildChannelField(must_exist=True)
        f.client = NotFoundClient()
        with pytest.raises(ValueError):
            f.convert(123456789012345678)
        with pytest.raises(ValueError):
            f.convert("not-exists")

    @pytest.mark.parametrize("must_exist", [True, False])
    def test_serialise(self, must_exist):
        f = GuildChannelField(must_exist=must_exist)  # must_exist shouldn't matter
        f.client = MockClient()
        assert f.serialize(Dummy("exists", 123456789012345678)) == 123456789012345678
