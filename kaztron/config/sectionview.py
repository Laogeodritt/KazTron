from typing import Generator, Dict, Tuple, Callable, Any
import logging

from kaztron.config import KaztronConfig, ReadOnlyError, ConfigConverterError

logger = logging.getLogger("kaztron.config")


class SectionView:
    """
    Dynamic view for a configuration section. Configuration keys can be retrieved as attributes
    (``view.config_key``) or via the :meth:`get` method; similarly, they can be written by setting
    attributes or via the :meth:`set` method.

    :meth:`set_defaults` allows default values to be set for specific keys. Note that these defaults
    may end up being written to file.

    :meth:`set_converters` allows setting converter functions for getting and setting values. This
    happens implicitly on any converter access, allowing transparent conversion between the JSON
    file data and Python objects.

    Any changes to configuration values in the view will be reflected in the KaztronConfig parent
    object (and thus can be written to file, etc.).

    Changes to configuration can be written in a few ways:

    * Attribute assignment. Note that you have to access the attribute DIRECTLY: if you make deeper
      modifications to the attribute's value (e.g. if it's a dict or list you modify), then it will
      not be detected and the 'dirty' flag will not be set. This will cause the change not to be
      written to file on the next :meth:`write()` call (or automatic write in a KazTron command).
    * Calling :meth:`set`.
    * Using `with section_view_instance:`. A write will be forced at the end of the `with` block,
      allowing you to get around the attribute assignment problem mentioned above. This may be
      less efficient if you are heavily using converters, as it will re-convert every key in the
      configuration.

    Get/set provide additional functionality like defining a default value, if the config key is
    not present, and specifying a converting function/callable.

    Attempting to get a non-existent value, if no default is set, will raise a ConfigKeyError. If
    a converter raises an error (either get or set), a ConfigConverterError is raised.

    ..deprecated : 3.0
        Use :cls:`kaztron.config.ConfigObject` models instead.
    """
    def __init__(self, config: KaztronConfig, section: str):
        self.__config = config
        self.__section = section
        self.__converters = {}  # type: Dict[str, Tuple[Callable[[Any], Any], Callable[[Any], Any]]]
        self.__cache = {}  # type: Dict[str, Any]

    def __enter__(self):
        if self.__config.read_only:
            raise ReadOnlyError("Configuration {} is read-only".format(self.__config.filename))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:  # exception happened - revert any changes
            self.__config.read()
            self.clear_cache()
            return

        # force detecting and converting data, in case changes were to converted data or structures
        for key in self.keys():
            self.set(key, self.get(key))  # forces dirty flag + conversion to happen
        self.write()

    def set_converters(self, key: str, get_converter, set_converter):
        """
        Set a converter to use with specific configuration values. This converter will only be
        applied to this SectionView.

        This method should generally be called in SectionView subclasses' __init__ method, or in
        the __init__ of a cog.

        Converters must have the signatures:

        * ``def get_converter(json_value) -> output_value``
        * ``def set_converter(any_value) -> json_serializable_value``

        :param key: The key to apply the converter to
        :param get_converter: The converter to be used when retrieving data. None to disable.
        :param set_converter: The converter to be used when setting data. None to disable.
        """
        if get_converter is not None and not callable(get_converter):
            raise ValueError("Get converter must be callable")
        if set_converter is not None and not callable(set_converter):
            raise ValueError("Set converter must be callable")
        if key in self.__cache:  # clear converted cache
            del self.__cache[key]
        self.__converters[key] = (get_converter, set_converter)

    def converter_keys(self) -> Generator[str]:
        """ Returns config keys with configured converters (either or both get or set). """
        for key, converters in self.__converters.items():
            if converters != (None, None):
                yield key

    def set_defaults(self, **kwargs):
        """
        Set configuration values for any keys that are not already defined in the config file.
        This method will write to file, if the config is not read-only.

        This method should generally be called in SectionView subclasses' __init__ method, or in
        the __init__ of a cog.

        Similar in usage to :meth:`KaztronConfig.set_defaults`.
        """
        return self.__config.set_defaults(self.__section, **kwargs)

    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key: str, value):
        if not key.startswith('_'):  # for private and protected values
            self.set(key, value)
        else:
            self.__dict__[key] = value

    def get(self, key: str, default=None):
        """
        Read a configuration value. Usage is similar to :meth:`KaztronConfig.get`.
        :raises ConfigKeyError: Key doesn't exist
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        converter = self.__converters.get(key, (None, None))[0]
        if key in self.__cache:
            logger.debug("{!s}: Read key '{}' from converter cache.".format(self, key))
            return self.__cache[key]
        else:
            value = self.__config.get(self.__section, key, default=default, converter=converter)
            if converter is not None:  # cache converted value
                self.__cache[key] = value
            return value

    def set(self, key: str, value):
        """
        Write a configuration value. Usage is similar to :meth:`KaztronConfig.set`.
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        converter = self.__converters.get(key, (None, lambda x: x))[1]
        if key in self.__cache:  # clear cached converted value
            del self.__cache[key]
        try:
            value = converter(value)
        except Exception as e:
            raise ConfigConverterError(self.__config.filename, self.__section, key) from e
        self.__config.set(self.__section, key, value)

    def keys(self):
        return self.__config.get_section_data(self.__section).keys()

    def clear_cache(self):
        """ Clear the converted value cache. This is recursive on any contained SectionViews. """
        logger.debug("{!s}: Clearing converted value cache.".format(self))
        self.__cache.clear()

    def write(self, log=True):
        """ If the in-memory cache of the config file is dirty, write to file. """
        self.__config.write(log)

    def __str__(self):
        return "{!s}:{}".format(self.__config, self.__section)

    def __repr__(self):
        return "Config<{!s}, data={!r}>"\
            .format(self, self.__config.get_section_data(self.__section))

    def __eq__(self, other):
        return self.__section == other.__section and self.__config is other.__config
