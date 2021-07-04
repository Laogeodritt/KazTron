import logging
import errno
import copy
from typing import Type, Union, TYPE_CHECKING
from munch import Munch

from .error import ReadOnlyError, ConfigNameError, ConfigKeyError, ConfigConverterError
from kaztron.driver.atomic_write import atomic_write

if TYPE_CHECKING:
    from .sectionview import SectionView

logger = logging.getLogger("kaztron.config")


ChannelConfig = Union[str, int]
RoleConfig = Union[str, int]


class JsonFileStrategy:
    def __init__(self, filename):
        self.filename = filename

    def read(self):
        import json
        with open(self.filename) as file:
            return json.load(file)

    def write(self, data):
        import json
        with atomic_write(self.filename) as file:
            return json.dump(data, file)


class TomlReadOnlyStrategy:
    def __init__(self, filename):
        self.filename = filename

    def read(self):
        import tomli
        with open(self.filename) as file:
            tomli.load(file)

    def write(self, _):
        raise NotImplementedError


class KaztronConfig:
    """
    Simple interface for KazTron configuration files. Currently supports two file formats using
    the Strategy design pattern: JSON (read/write) and TOML (read-only).

    Sections can be accessed as attributes (as long as the name is a valid attribute name). If a
    section doesn't exist,

    Expected structure is similar to:

    .. code-block:: json
        {
            "section1": {
                "key1": "any data type",
                "key2": ["a", "list", "is", "fine"]
            },
            "section2": {
                "key1": "flamingo",
                "key2": 3
            }
        }

    :param filename: Filename or filepath of the config file.
    :param defaults: A dict of the same structure as the JSON file above,
        containing default values to set to the config file. Optional.

    .. attribute:: filename

        ``str`` - Filename or filepath for the config file. Read/write.

    .. attribute:: read_only

        ``bool`` - Whether the config file is read-only. If true, disables :meth:`~.write()` and
        :meth:`~.set`. Read-only property.
    """
    def __init__(self, filename="config.json", file_strategy=JsonFileStrategy,
                 defaults=None, read_only=False):
        self._file_strategy = file_strategy(filename)
        self._data = Munch()
        self._defaults = {}
        self._read_only = read_only
        self._section_view_map = {}
        self.is_dirty = False
        self.read()
        for section, s_data in defaults.items() if defaults else {}:
            self.set_defaults(section, **s_data)

    @property
    def filename(self):
        return self._file_strategy.filename

    @filename.setter
    def filename(self, value):
        self._file_strategy.filename = value

    @property
    def read_only(self):
        return self._read_only

    def read(self):
        """
        Read the config file and update all values stored in the object.
        :raises OSError: Error opening file.
        :raises JSONDecodeError:
        :raises ConfigNameError: Invalid key name in file
        """
        logger.info("config({}) Reading file...".format(self.filename))
        self._data = Munch()
        try:
            read_data = self._file_strategy.read()
        except OSError as e:
            if e.errno == errno.ENOENT:  # file not found, just create it
                if not self._read_only:
                    self.is_dirty = True  # force the write
                    self.write()
                else:
                    raise
            else:  # other failures should bubble up
                raise
        else:
            self._data.update(Munch.fromDict(read_data))
            self.is_dirty = False

        for section, sdata in self._data.items():
            if section.startswith('_'):
                raise ConfigNameError(self.filename, section, None)
            for key in sdata.keys():
                if key.startswith('_'):
                    raise ConfigNameError(self.filename, section, key)

    def write(self, log=True):
        """
        Write the current config data to the configured file.
        :raises OSError: Error opening or writing file.
        :raise ReadOnlyError: configuration is set as read-only
        """
        if self._read_only:
            raise ReadOnlyError(self.filename)

        if self.is_dirty:
            if log:
                logger.info("config({}) Writing file...".format(self.filename))
            self._file_strategy.write(self._data)
            self.is_dirty = False

    def set_section_view(self, section: str, cls: Type['SectionView']):
        """
        Set the SectionView sub-class to use for a particular section.

        This option is made available to allow for sub-classes of SectionView, which can contain
        attribute type annotations for IDE autocompletion as well as specify conversion functions.
        """
        self._section_view_map[section] = cls

    def __getattr__(self, item):
        return self.get_section(item)

    def get_section(self, section: str) -> 'SectionView':
        """
        Retrieve a configuration section view. Modifications to this view
        will be reflected in this object's loaded config.

        If section doesn't exist, a SectionView will be returned that can be used to write to a new
        section (unless the configuration is read-only).

        :param section: Section name to retrieve
        :raises ConfigKeyError: section doesn't exist in a read-only config
        """
        from .sectionview import SectionView  # lazy import avoids circular reference
        logger.debug("config:get_section: file={!r} section={!r} ".format(self.filename, section))

        if self.read_only and section not in self._data:
            raise ConfigKeyError(self.filename, section, None)

        cls = self._section_view_map.get(section, SectionView)
        return cls(self, section)

    def get_section_data(self, section: str) -> dict:
        """
        Retrieve the raw section data. THIS IS A LIVE DICT - you should not
        make direct changes to this dict.

        This is a low-level method and should generally not be called by cogs.
        :param section: Section name to retrieve
        :raises ConfigKeyError: section doesn't exist
        """
        # TODO: update for new config types/objects system
        try:
            return self._data[section]
        except KeyError as e:
            raise ConfigKeyError(self.filename, section, None) from e

    def get(self, section: str, key: str, default=None, converter=None):
        """
        Retrieve a configuration value. The returned value, if it is a
        collection, the returned collection is **not a copy**: modifications to
        the collection may be reflected in the config loaded into memory. If you
        need to modify it without changing the loaded config, make a copy.

        If the value is not found in the config data, then ``default`` is
        returned if it is not None.

        Note that if ``defaults`` were provided at construction time or via :meth:`~.set_defaults`,
        they take precedence over the ``default`` parameter.

        .. deprecated:: v2.2a1
            Use attribute access (e.g. `config.section_name.key_name`) instead.

        :param section: Section of the config file to retrieve from.
        :param key: Key to obtain.
        :param default: Value to return if the section/key is not found. If this
            is None or not specified, a KeyError is raised instead.
        :param converter: Type or converter function for the value. Called with
            the retrieved value as its single argument. Must not modify the
            original value (e.g. if that value is a collection).

        :raises ConfigKeyError: Section/key not found and ``default`` param is ``None``
        :raises TypeError: Section is not a dict
        """
        # TODO: update for new config types/objects system (remove converter, predefined defaults, ...)
        logger.debug("config:get: file={!r} section={!r} key={!r}"
            .format(self.filename, section, key))

        try:
            value = self._data[section][key]
        except KeyError as e:
            default = self._get_default(section, key, default)
            if default is not None:
                logger.debug("config({}) {!r} -> {!r} not found: using default {!r}"
                    .format(self.filename, section, key, default))
                value = default
            else:
                raise ConfigKeyError(self.filename, section, key) from e
        except TypeError:
            raise TypeError("config({}) Unexpected configuration file structure"
                .format(self.filename))

        if converter is not None and callable(converter):
            try:
                value = converter(value)
            except Exception as e:
                raise ConfigConverterError(self.filename, section, key) from e
        return value

    def _get_default(self, section: str, key: str, default):
        try:
            return self._defaults[section][key]
        except KeyError:
            return default

    def set(self, section: str, key: str, value):
        """
        Write a configuration value. Values should always be primitive types
        (int, str, etc.) or JSON-serialisable objects. A deep copy is made of
        the object for storing in the configuration.

        .. deprecated:: v2.2a1
            Use attribute access (e.g. ``config.section_name.key_name``) instead.

        :param section: Section of the config file
        :param key: Key name to store
        :param value: Value to store at the given section and key
        :raise ReadOnlyError: configuration is set as read-only
        """
        if self._read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.filename))
        logger.debug("config:set: file={!r} section={!r} key={!r}"
            .format(self.filename, section, key,))

        try:
            section_data = self._data[section]
        except KeyError:
            logger.debug("Section {!r} not found: creating new section".format(section))
            section_data = self._data[section] = Munch()

        section_data[key] = copy.deepcopy(value)
        self.is_dirty = True

    def set_defaults(self, section: str, **kwargs):
        """
        Set configuration values for any keys that are not already defined in the config file.
        If the configuration file is not read-only, this will set the configuration and write the
        file; if it is read-only, this will only retain these defaults in-memory.

        .. deprecated:: v2.2a1
            Use attribute access for the section and :meth:`SectionView.set_defaults`, e.g.,
            ``config.section_name.set_defaults(...)``.

        :param section: The section to set. This method can only set one section at a time.
        :param kwargs: key=value pairs to set, if the key is not already in the config.
        :raises OSError: Error opening or writing file.
        :raise ReadOnlyError: configuration is set as read-only
        """
        if not self.read_only:
            for key, value in kwargs.items():
                try:
                    self.get(section, key)
                except KeyError:
                    self.set(section, key, value)
            self.write()
        else:
            if section not in self._defaults:
                self._defaults[section] = {}
            self._defaults[section].update(kwargs)

    def notify(self):
        """
        Notify that a config value has been changed in the underlying data. This is generally only
        used by :cls:`ConfigObject` when data is being set through it.
        """

    def __str__(self):
        return '{!s}{}'.format(self.filename, '[ro]' if self.read_only else '')

    def __repr__(self):
        return 'KaztronConfig<{!s}>'.format(self)


def log_level(value: str):
    """
    Converter for KaztronConfig.get() for the core.log_level config
    """
    log_level_map = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
    }
    return log_level_map[value.upper()]
