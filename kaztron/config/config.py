import logging
import errno
import copy
from typing import Sequence
from munch import Munch

from kaztron.driver.atomic_write import atomic_write

from .object import ConfigRoot
from .error import ReadOnlyError, ConfigKeyError, ConfigConverterError

logger = logging.getLogger("kaztron.config")


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
            return tomli.load(file)

    def write(self, _):
        raise NotImplementedError


class KaztronConfig:
    """
    Simple interface for KazTron configuration files. Currently supports two file formats using
    the Strategy design pattern: JSON (read/write) and TOML (read-only).

    This class is a configuration management class, allowing reading/writing the file, managing
    when modifications have occurred to the data that needs to be written to file, and allowing
    low-level access to the data.

    Normal access to the data should happen via :cls:`ConfigModel` object-oriented models. You can
    access the :cls:`ConfigRoot` of the data using the :attr:`root` attribute, and register your
    own models via :meth:`kaztron.config.object.ConfigRoot.cfg_register_model`.

    The root of a KazTron configuration must be a dict (JSON object, TOML table). All dicts in
    KazTron configuration files must have string keys. Allowed types within a configuration file are
    integers, floats, strings, lists, and dicts. The object-oriented models can convert the raw
    data into any Python object via the :meth:`kaztron.config.fields.Field.convert` method.

    :ivar filename: Filename or filepath for the config file. Read/write.
    :ivar read_only: Whether the config file is read-only. This reflects the init parameter, and
        not necessarily the filesystem permissions.
    """
    _NO_DEFAULT = object()

    def __init__(self, filename="config.json", file_strategy=JsonFileStrategy,
                 read_only=False):
        """
        :param filename:
        :param file_strategy:
        :param read_only:
        """
        self._data = None
        self._file_strategy = file_strategy(filename)
        self._root = ConfigRoot(self)
        self._read_only = read_only
        self.is_dirty = False
        self.read()

    @property
    def filename(self) -> str:
        return self._file_strategy.filename

    @filename.setter
    def filename(self, value):
        self._file_strategy.filename = value

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def root(self) -> ConfigRoot:
        """
        Access root of the configuration tree. Use this to read configuration data. This property
        returns a :cls:`ConfigModel` object which allows rich ORM-style access to data,
        defining Python data types for the config data values, etc.

        See :cls:`ConfigModel` documentation for more information.
        """
        return self._root

    @property
    def data(self) -> Munch:
        """
        **In most cases, this property should not be used.**

        **Live dict, do not modify.** Changes will not be detected or written to disk!

        Get the raw dict containing parsed configuration data.
        """
        return self._data

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
        self._root.cfg_set_data(self._data)

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

    def get(self, path: Sequence[str], default=_NO_DEFAULT):
        """
        Note: Using the Config Model system starting at :attr:`root` is generally preferred. This
        method is a low-level method retrieving raw data.

        Retrieve a configuration value. The returned value, if it is a
        collection, the returned collection is **not a copy**: modifications to
        the collection may be reflected in the config loaded into memory. If you
        need to modify it without changing the loaded config, make a copy.

        If the value is not found in the config data, then ``default`` is returned if specified,
        otherwise KeyError is raised.

        :param path: Path to retrieve within the config file's structure. This is usually a tuple of
            strings and ints, each representing a key (for dicts) or index (for lists).
        :param default: Value to return if the path is not found. If this
            not specified, a KeyError is raised instead.

        :raises ConfigKeyError: Path not found and ``default`` param is not specified.
        :raises TypeError: Path is invalid for data structure (e.g. string in path to access a
            list).
        """
        logger.debug(f"config:get: file={self.filename!r} path={path!r}")
        current_node = self._data

        for next_node_name in path:
            try:
                current_node = current_node[next_node_name]
            except (KeyError, IndexError):
                if default is not self._NO_DEFAULT:
                    logger.debug("config({}) {!r} not found: using default {!r}"
                        .format(self.filename, path, default))
                    return default

                path_part = path[:path.index(next_node_name)]
                raise ConfigKeyError(self.filename, path_part, next_node_name)

        return current_node

    def set(self, path: Sequence[str], value, make_path=False):
        """
        Write a configuration value. Values should always be acceptable primitive types. A deep copy
        is made of the object for storing in the configuration. No type validation is
        performed: passing invalid types to ``set()`` may cause a later call to :meth:`write` to
        fail.

        If traversing through lists within the ``path``, an integer can be specified. However, this
        will only traverse existing elements; it is not possible to append a value, or to traverse
        through non-existent elements in a list using ``make_path``. (To do so, get() the list,
        insert or append to it, then set() it).

        :param path: Path to retrieve within the config file's structure. This is usually a tuple of
            strings and ints, each representing a key (for dicts) or index (for lists).
        :param value: Value to store at the given section and key. Value (or deep structure, if a
            container) must be a valid type for configuration files.
        :param make_path: If true, and a node on the path doesn't exist, that node will be created
            as a dict. This only works if the parent node is a dict.
        :raise ReadOnlyError: configuration is set as read-only
        :raises ConfigKeyError: Path not found and ``make_path`` is False.
        :raises TypeError: Path is invalid for data structure (e.g. string in path to access a
            list).
        :raises IndexError: Index is invalid for a list access in the path.
        """
        if self._read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.filename))
        logger.debug("config:set: file={!r} path={!r}"
            .format(self.filename, path))
        current_node = self._data

        for next_node_name in path[:-1]:
            try:
                current_node = current_node[next_node_name]
            except KeyError:
                if make_path:
                    logger.debug("Key {!r} not found: creating as dict".format(next_node_name))
                    current_node[next_node_name] = Munch()
                    current_node = current_node[next_node_name]
                else:
                    path_part = path[:path.index(next_node_name)]
                    raise ConfigKeyError(self.filename, path_part, next_node_name)
            except IndexError:
                path_part = path[:path.index(next_node_name)]
                raise ConfigKeyError(self.filename, path_part, next_node_name)

        current_node[path[-1]] = copy.deepcopy(value)
        self.is_dirty = True

    def notify(self):
        """
        Notify that a config value has been changed in the underlying data. This is generally only
        used by :cls:`ConfigModel` when data is being set through it.
        """
        if self._read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.filename))
        self.is_dirty = True

    def __str__(self):
        return '{!s}{}'.format(self.filename, '[ro]' if self.read_only else '')

    def __repr__(self):
        return 'KaztronConfig<{!s}>'.format(self)
