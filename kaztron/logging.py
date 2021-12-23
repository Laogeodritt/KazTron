import gzip
import logging
import logging.handlers
import os

from typing import TYPE_CHECKING

from kaztron.config import KaztronConfig
from kaztron.core_config import Logging


class LoggingInfo:
    is_setup = False
    cfg_level = logging.INFO
    cfg_packages = {}
    file_handler = None  # type: logging.FileHandler
    console_handler = None  # type: logging.StreamHandler


_logging_info = LoggingInfo()


def setup_logging(logger, config: KaztronConfig, *, debug=False, console=True):
    global _logging_info

    # set up access to logging configuration and read configuration
    config.root.cfg_register_model('logging', Logging, required=False, lazy=False)
    cfg_logging = config.root.logging  # type: Logging

    if not debug:
        cfg_level = cfg_logging.level
        console_level = max(cfg_level, logging.INFO)  # console never above INFO - avoid clutter
    else:
        cfg_level = console_level = logging.DEBUG

    logger.setLevel(cfg_level)
    _logging_info.cfg_level = cfg_level
    _logging_info.cfg_packages = cfg_logging.tags  # level overrides for specific packages

    for name, s_value in _logging_info.cfg_packages.items():
        logging.getLogger(name).setLevel(max(s_value, cfg_level))

    # remove any existing handlers
    logging.getLogger().handlers.clear()

    # File handler
    fh = logging.handlers.RotatingFileHandler(
        cfg_logging.file,
        maxBytes=cfg_logging.max_size_kb*1024,
        backupCount=cfg_logging.max_backups
    )
    if cfg_logging.gzip_backups:
        fh.namer = gzip_namer
        fh.rotator = gzip_rotator
    fh_formatter = logging.Formatter(
        '[%(asctime)s] (%(levelname)s) %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    _logging_info.file_handler = fh

    # Console handler
    if console or debug:
        import sys
        ch = logging.StreamHandler(stream=sys.stdout)
        ch_formatter = logging.Formatter('[%(asctime)s] (%(levelname)s) %(name)s: %(message)s')
        ch.setLevel(console_level)
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)
        _logging_info.console_handler = ch

    _logging_info.is_setup = True


def get_logging_info() -> LoggingInfo:
    return _logging_info


def gzip_rotator(source, dest):
    with open(source, "rb") as sf:
        with gzip.open(dest, 'wb') as df:
            df.writelines(sf)
    os.remove(source)


def gzip_namer(name):
    return name + '.gz'
