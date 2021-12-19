#!/usr/bin/env python
# coding=utf8

import sys
import logging

import kaztron
from kaztron.runner import *
from kaztron.config import get_kaztron_config
from kaztron.logging import setup_logging

# In the loving memory of my time as a moderator of r/worldbuilding network
# To the future dev, this whole thing is a mess that somehow works. Sorry for the inconvenience.
# (Assuming this is from Kazandaki -- Laogeodritt)

# load configuration
try:
    config = get_kaztron_config()
except OSError as e:
    print(str(e), file=sys.stderr)
    sys.exit(ErrorCodes.CFG_FILE)


def stop_daemon():
    import os
    import signal
    # noinspection PyPackageRequirements
    from daemon import pidfile
    print("Reading pidfile...")
    pidf = pidfile.TimeoutPIDLockFile(config.get(('core', 'daemon', 'pidfile'), "pid.lock"))
    pid = pidf.read_pid()
    print("Stopping KazTron (PID={:d})...".format(pid))
    os.kill(pid, signal.SIGINT)
    time.sleep(2)  # time for process to finish - TODO: monitor PID directly
    print("Stopped.")


if __name__ == '__main__':
    import asyncio
    import os
    import signal
    import time

    try:
        cmd = sys.argv[1].lower()
    except IndexError:
        cmd = None

    is_daemon = config.get(('core', 'daemon', 'enabled'), False)

    if cmd == 'start' and is_daemon:
        print("Daemonize...")
        with get_daemon_context(config):
            print("Starting KazTron (daemon)...")
            setup_logging(logging.getLogger(), config, console=False)
            run_kaztron(asyncio.get_event_loop())

    elif cmd == 'start':  # non-daemon
        print("Starting KazTron ...")
        setup_logging(logging.getLogger(), config, console=True)
        run_kaztron(asyncio.get_event_loop())

    elif cmd == 'debug':
        print("Starting KazTron (debug mode)...")
        setup_logging(logging.getLogger(), config, debug=True)
        run_kaztron(asyncio.get_event_loop())  # always non-daemon mode

    elif cmd == 'stop':
        if not is_daemon:
            print("[ERROR] Cannot stop: daemon mode not enabled", file=sys.stderr)
            sys.exit(ErrorCodes.DAEMON_NOT_RUNNING)

        try:
            stop_daemon()
        except TypeError:
            print("[ERROR] Cannot stop: daemon not running", file=sys.stderr)
            sys.exit(ErrorCodes.DAEMON_NOT_RUNNING)

    elif cmd == 'restart':
        if not is_daemon:
            print("[ERROR] Cannot restart: daemon mode not enabled", file=sys.stderr)
            sys.exit(ErrorCodes.DAEMON_NOT_RUNNING)

        try:
            stop_daemon()
        except TypeError:
            print("[WARNING] Cannot stop: daemon not running", file=sys.stderr)

        print("Starting KazTron (daemon mode)...")
        with get_daemon_context(config):
            print("Starting KazTron daemon...")
            setup_logging(logging.getLogger(), config, console=False)
            run_kaztron(asyncio.get_event_loop())

    else:
        print("Usage: ./kaztron.py <start|stop|restart|debug|help>\n")
