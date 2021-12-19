import pytest
from unittest.mock import Mock, patch

from discord.ext import commands

from kaztron.errors import UnauthorizedChannelError
from kaztron.utils.checks import *


def _x(decorator):
    """ Extract the check predicate from a decorator wrapper. """
    return decorator(Mock()).__commands_checks__[0]


def get_channel_patch(ctx, ch_id):
    ch = Mock()
    if isinstance(ch_id, int):
        ch.id = ch_id
        ch.name = f'channel-{ch_id:18d}'
    else:
        ch.id = 123456789012345678
        ch.name = ch_id
    return ch


class TestCheckBase:
    def test_doc_params(self):
        class TestCheck(Check):
            def __call__(self, ctx) -> bool:
                return True
        data = (1, 2, 3)
        a = TestCheck(CheckType.OTHER, data)
        assert a.type == CheckType.OTHER
        assert a.data == data


class TestCheckAny:
    class FailCheck(Check):
        def __init__(self):
            super().__init__(check_type=CheckType.OTHER, check_data=False)

        def __call__(self, _):
            raise commands.CheckFailure()

    class SuccessCheck(Check):
        def __init__(self):
            super().__init__(check_type=CheckType.OTHER, check_data=True)

        def __call__(self, _):
            return True

    def _fail_check_func(self, _):
        raise commands.CheckFailure

    async def _fail_check_async(self, _):
        raise commands.CheckFailure

    def fail_check(self):
        return commands.check(self.FailCheck())

    def success_check(self):
        return commands.check(self.SuccessCheck())

    def fail_check_f(self):
        return commands.check(self._fail_check_func)

    def fail_check_a(self):
        return commands.check(self._fail_check_async)

    def test_doc_params(self):
        data = (1, 2, 3)
        checks = (self.fail_check(), self.success_check(), self.fail_check())
        a = _x(check_any(*checks))
        assert isinstance(a, Check)
        assert a.type == CheckType.ANY
        assert len(a.checks) == 3
        for check in a.checks:
            assert check.type == CheckType.OTHER
        assert a.data == a.checks

    @pytest.mark.asyncio
    async def test_all_checks_fail(self):
        a = _x(check_any(self.fail_check(), self.fail_check_f(), self.fail_check_a()))
        with pytest.raises(commands.CheckAnyFailure):
            s = Mock()
            await a(s)

    @pytest.mark.asyncio
    async def test_second_check_success(self):
        s = Mock()
        a = _x(check_any(self.fail_check(), self.success_check(), self.fail_check()))
        assert await a(s) is True
        a = _x(check_any(self.fail_check_f(), self.success_check(), self.fail_check()))
        assert await a(s) is True
        a = _x(check_any(self.fail_check_a(), self.success_check(), self.fail_check()))
        assert await a(s) is True


class TestChannelCheck:
    @staticmethod
    def _test_channels(ctx, check):
        with patch('kaztron.utils.checks.get_channel', get_channel_patch):
            ctx.channel.id = 123456789012345678
            ctx.channel.name = 'channel-123456789012345678'
            assert check(ctx) is True

            ctx.channel.id = 123456780123456789
            ctx.channel.name = 'allowed-channel'
            assert check(ctx) is True

            ctx.channel.id = 987654321087654321
            ctx.channel.name = 'not-allowed'
            with pytest.raises(UnauthorizedChannelError):
                check(ctx)

    @staticmethod
    def _setup_config_return(config_model):
        ctx = Mock()  # doesn't matter for get_channel_patch
        config_model.traverse.return_value = [
            get_channel_patch(ctx, 123456789012345678),
            get_channel_patch(ctx, 'allowed-channel')
        ]

    def test_channel_list(self):
        ctx = Mock()
        check = _x(in_channels(channels=[123456789012345678, 'allowed-channel']))
        self._test_channels(ctx, check)

    def test_channel_config(self):
        ctx = Mock()
        self._setup_config_return(ctx.cog.config)
        check = _x(in_channels(config='some.config.path'))
        self._test_channels(ctx, check)
        ctx.cog.config.traverse.assert_called_with('some', 'config', 'path')

    def test_channel_state(self):
        ctx = Mock()
        self._setup_config_return(ctx.cog.state)
        check = _x(in_channels(state='some.config.path'))
        self._test_channels(ctx, check)
        ctx.cog.state.traverse.assert_called_with('some', 'config', 'path')

    def test_channel_cog_state(self):
        ctx = Mock()
        self._setup_config_return(ctx.cog.cog_state)
        check = _x(in_channels(cog_state='some.config.path'))
        self._test_channels(ctx, check)
        ctx.cog.cog_state.traverse.assert_called_with('some', 'config', 'path')

    def test_mod_channels(self):
        ctx = Mock()
        self._setup_config_return(ctx.cog.config)
        check = _x(mod_channels())
        self._test_channels(ctx, check)
        ctx.cog.config.traverse.assert_called_with('core', 'discord', 'mod_channels')

    def test_admin_channels(self):
        ctx = Mock()
        self._setup_config_return(ctx.cog.config)
        check = _x(admin_channels())
        self._test_channels(ctx, check)
        ctx.cog.config.traverse.assert_called_with('core', 'discord', 'admin_channels')
