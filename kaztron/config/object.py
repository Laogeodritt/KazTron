import typing
from copy import copy
import logging
from typing import Iterable, Tuple, Type, Any, TYPE_CHECKING

from kaztron.config.error import ConfigKeyError, ConfigConverterError, ReadOnlyError
from kaztron.config.types import Field, PrimitiveField, ContainerField, ConfigObjectField, \
    ConfigPrimitive

if TYPE_CHECKING:
    from kaztron.config.config import KaztronConfig

logger = logging.getLogger("kaztron.config")

# TODO: in key accesses, if Field specifies a different name than attribute, use that


class ConfigObjectMeta(type):
    """
    Metaclass for Config objects. Processes configuration fields and merges them according to
    inheritance structure, if needed.

    This metaclass should not be used directly. You should subclass :cls:`ConfigObject` instead.
    """
    def __new__(mcs, name, bases, attrs):
        cls = super().__new__(mcs, name, bases, attrs)
        cls.__config_fields__ = {}
        for base in reversed(cls.__mro__):
            try:
                if cls is not base:
                    cls.__config_fields__.update(base.__config_fields__)
            except AttributeError:
                pass

        for attr, value in list(cls.__dict__.items()):
            if isinstance(value, Field):
                if value.name is None:
                    value.name = attr
                cls.__config_fields__[attr] = value
                delattr(cls, attr)
        return cls


class ConfigObject(metaclass=ConfigObjectMeta):
    """
    Object-oriented model for a configuration file dict (JSON object, TOML table). This object is
    intended to a) allow easy definition of keys, default values, and conversion to Python objects,
    with minimum boilerplate code; b) allow simple object-oriented access to config file structures,
    including within lists; c) automatically write changes back to file.

    This class should not be instantiated directly, but subclassed. Subclasses are to be used in a
    :cls:`dataclasses.dataclass`-like fashion, where fields are typehinted (for IDE convenience)
    and assigned to a :cls:`~kaztron.config.Field` subclass instance to determine the type and
    parameters of the config value. Refer to examples in the Core cog.

    This object allows two ways of accessing a key. In these examples, we have an instance of a
    ConfigObject ``co`` and want to access the ``name`` key:

    1. Attribute access: ``co.name``
    2. Get method: ``co.get("name")``

    Similarly, for setting:

    1. Attribute access: ``co.name = "Eleanor"``
    2. Set method: ``co.set("name", "Eleanor")``
    """
    DEFAULT_FIELD = PrimitiveField(name=None, default=None, required=True, lazy=True)

    def __init__(self, **kwargs):
        self.__config_field__ = ConfigObjectField(name='Unassigned', type=self.__class__)
        self.__config_parent__: 'ConfigObject' = None
        self.__config_root__: 'ConfigRoot' = None
        self._data = {}
        self._converted = {}

        for key, value in kwargs:
            self.set(key, value)

    def cfg_set_field(self, field: ConfigObjectField):
        self.__config_field__ = field

    def cfg_set_parent(self, parent: 'ConfigObject'):
        self.__config_parent__ = parent
        self.__config_root__ = parent.__config_root__

    def cfg_set_data(self, raw_data: dict):
        self._data = raw_data
        self.clear_cache()

        # pre-convert all keys, if not lazy
        if not self.__config_field__.lazy:
            logging.info(f"{self!s}: Converting all data (non-lazy)...")
            # convert all defined keys in data
            for key in self.keys():
                self.get(key)

            # also convert all field keys, to check for missing required fields
            # don't worry about redundancy here: this will simply return from cache
            for key in self.cfg_field_keys():
                self.get(key)

    def cfg_get_field(self, key: str) -> Field:
        """ Return the Field for a given key, or a PrimitiveField if the key is not known. """
        try:
            field = self.__config_fields__[key]
        except KeyError:
            field = self.DEFAULT_FIELD
        return field

    def cfg_field_keys(self) -> Iterable[str]:
        """
        Get all keys for known fields. This usually means fields defined in the
        ConfigObject subclass definition. See also :meth:`keys()`.
        """
        return self.__config_fields__.keys()

    def keys(self) -> Iterable[str]:
        """
        Get all keys contained in the configuration data. This only returns keys actually defined
        in the configuration file. See also :meth:`cfg_field_keys`.
        """
        return self._data.keys()

    @property
    def cfg_file(self) -> str:
        return self.__config_root__.filename if self.__config_root__ else None

    @property
    def cfg_path(self) -> Tuple:
        try:
            return self.__config_parent__.cfg_path + (self.__config_field__.name,)
        except AttributeError:
            return self.__config_field__.name,

    @property
    def cfg_read_only(self) -> bool:
        return self.__config_root__.read_only

    def clear_cache(self):
        """ Clear cache of converted objects (i.e. read cache). """
        self._converted.clear()
        logging.info(f"{self!s}: Cache cleared.")

    def cfg_notify_update(self, key: str, value):
        self.__config_parent__.cfg_notify_update(key, value)

    def cfg_write(self):
        self.__config_root__.write()

    def get(self, key: str) -> Any:
        """
        Read a configuration value. Usage is similar to :meth:`KaztronConfig.get`.

        If the key doesn't exist, behaviour depends on the key's associated :cls:`Field`: if the
        key is required, then :cls:`ConfigKeyError` is raised. Otherwise, the Field's default value
        is returned.

        :raises ConfigKeyError: Key doesn't exist
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        if key in self._converted:
            logger.debug(f"{self!s}: Read key '{key}' from converter cache.")
            return self._converted[key]

        field = self.cfg_get_field(key)

        try:
            raw_value = self._data[key]
            logger.debug(f"{self!s}: Read key '{key}' from file.")
        except KeyError as e:
            if field.required:
                raise ConfigKeyError(self.cfg_file, self.cfg_path, key) from e
            else:
                logging.warning(f"{self!s}: Key '{key}' not found, using default.")
                raw_value = copy(field.default)
        try:
            conv_value = self._convert_field(field, raw_value)
        except Exception as e:
            raise ConfigConverterError(self.cfg_file, self.cfg_path, key, raw_value, conv_value) \
                from e
        self._converted[key] = conv_value
        return conv_value

    def _convert_field(self, field: Field, raw_value: ConfigPrimitive) -> Any:
        # Note: this method should only be called when a cache miss happens
        # So the initialisation of data in ContainerField and ConfigObjectField
        # should only happen on first access or after cache is cleared
        if isinstance(field, ConfigObjectField):
            obj = field.convert(raw_value)
            obj.cfg_set_parent(self)
            return obj
        elif isinstance(field, ContainerField):
            # TODO: consider separating the Field from the proxy container type
            field.init_data(raw_value)
            return field
        elif isinstance(field, PrimitiveField):
            return field.convert(raw_value)

    def set(self, key: str, value):
        """
        Write a configuration value. Usage is similar to :meth:`KaztronConfig.set`.
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        if self.cfg_read_only:
            raise ReadOnlyError(self.cfg_file)

        logging.info(f"{self!s}: Set key {key}")

        field = self.cfg_get_field(key)
        ser_value = field.serialize(value)
        if not isinstance(ser_value, typing.get_args(ConfigPrimitive)):
            raise ConfigConverterError(self.cfg_file, self.cfg_path, key, value, ser_value)

        # clear old cached value if needed
        try:
            del self._converted[key]
        except KeyError:
            pass

        # update the object's state, in case it continues to be used
        self.cfg_set_parent(self)
        self.cfg_set_data(self._data[key])

        # We DO NOT add the object to cache - prefer to convert it on next access

        # update the data store
        self._data[key] = ser_value
        self.cfg_notify_update(key, ser_value)

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key: str, value):
        if not key.startswith('_') and not key.startswith('cfg_'):
            self.set(key, value)
        else:
            self.__dict__[key] = value

    def __str__(self):
        """ String representation of this config object: returns file and config path. """
        file = self.cfg_file or '(No file)'
        return file + ':' + '.'.join(self.cfg_path)

    def __repr__(self):
        """
        Technical representation of this object, including its data. This method may trigger
        a conversion of all keys, which may be time-consuming.
        """
        repr_data = {key: repr(self.get(key)) for key in self.keys()}
        return f'<{self.__class__.__name__} {str(self)} {repr(repr_data)}>'

    def __eq__(self, other: 'ConfigObject'):
        return self._data == other._data


class ConfigRoot(ConfigObject):
    """
    ConfigObject model which represents the root of a configuration file. Instances are provided
    by the framework; this class should typically not be instantiated directly.
    """

    def __init__(self, config: KaztronConfig):
        super().__init__()
        self._config = config
        self.cfg_set_field(ConfigObjectField(name='root', type=self.__class__))
        self.__config_parent__ = None
        self.__config_root__ = self

    def cfg_set_parent(self, parent: 'ConfigObject'):
        raise NotImplementedError("ConfigRoot cannot have parent")

    # TODO: add register model method/capability to KazCog
    def cfg_register_model(self, key: str, model: Type[ConfigObject], **kwargs):
        """
        Register the ConfigObject model to use for a given key. kwargs are passed to the
        underlying ConfigObjectField describing that key (except ``type``).
        """
        if 'name' not in kwargs:
            kwargs['name'] = key
        kwargs['type'] = model
        self.__config_fields__[key] = field = ConfigObjectField(**kwargs)
        logging.info(f"ConfigRoot({self.cfg_file}): registered key '{key}' to field {field}")

        if not field.lazy:
            self.get(key)

    @property
    def cfg_file(self) -> str:
        return self._config.filename

    @property
    def cfg_path(self) -> Tuple:
        return tuple()

    @property
    def cfg_read_only(self) -> bool:
        return self._config.read_only

    def cfg_notify_update(self, _, __):
        self._config.notify()

    def cfg_write(self):
        self._config.write()
