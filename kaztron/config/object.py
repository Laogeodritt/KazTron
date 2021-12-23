from copy import copy
from collections.abc import MutableSequence, MutableMapping
from dataclasses import dataclass
import logging
import typing
from typing import Optional, Iterable, List, Dict, Tuple, Type, Any, TYPE_CHECKING

from kaztron.config.error import ConfigKeyError, ConfigNameError, ConfigConverterError, \
    ReadOnlyError
from kaztron.config.fields import Field, PrimitiveField, ConfigModelField, ListField, DictField, \
    ConfigPrimitive

if TYPE_CHECKING:
    from kaztron.config.config import KaztronConfig

logger = logging.getLogger("kaztron.config")


class ConfigNodeMixin:
    def __init__(self):
        super().__init__()
        self.__config_field__: Optional[Field] = None
        self.__config_parent__: Optional['ConfigNodeMixin'] = None
        self.__config_root__: Optional['ConfigRoot'] = None
        self._parent_index: Optional[int] = None
        self._field_runtime_attributes: Dict[Type[Field], Dict[str, Any]] = {}

    def cfg_set_field(self, field: Field):
        self.__config_field__ = field

    def cfg_set_parent(self, parent: 'ConfigNodeMixin'):
        self.__config_parent__ = parent
        self.__config_root__ = parent.__config_root__

    def cfg_set_data(self, raw_data):
        raise NotImplementedError()

    def cfg_notify_update(self, key: str, value):
        try:
            self.__config_parent__.cfg_notify_update(key, value)
        except AttributeError:
            pass  # no parent - non-file-attached object

    def cfg_write(self):
        try:
            self.__config_root__.write()
        except AttributeError:
            pass  # no root - non-file-attached object

    def _convert_child_node(self, field: Field, raw_value: ConfigPrimitive)\
            -> Any:
        """
        Uses the passed field to convert the raw value into its Python object form. F

        This is a wrapper around the field's own convert method in order to also properly set
        config node metadata. In the case of non-node field types, this method simply calls
        :meth:`Field.convert`.

        Note that in nodes that implement object caching, this method should only be called when
        a cache miss happens to avoid redundant conversions (esp. for non-lazy fields).

        :param field: Field definition for the child node
        :param raw_value: Raw (serialised) value of the child node. This should be a reference
        within the KazTronConfig data object, and not a copy of the data, in order for data
        writes to work properly.
        """
        self._update_runtime_attributes(field)
        if isinstance(field, ConfigModelField):
            node = field.convert(raw_value, self)
            return node
        elif isinstance(field, DictField):
            if not isinstance(raw_value, dict):
                raise ValueError(raw_value)
            node = ConfigDict(field=field)
            node.cfg_set_parent(self)
            node.cfg_set_data(raw_value)
            return node
        elif isinstance(field, ListField):
            if not isinstance(raw_value, list):
                raise ValueError(raw_value)
            node = ConfigList(field=field)
            node.cfg_set_parent(self)
            node.cfg_set_data(raw_value)
            return node
        else:
            return field.convert(raw_value)

    def _update_child_node(self, field: Field, node: 'ConfigNodeMixin', raw_value=None):
        """
        Update the metadata of a node so that it becomes this node's child. Optionally also update
        its raw data store (this does not copy data over, only changes the referenced data).
        """
        self._update_runtime_attributes(field)
        if isinstance(node, ConfigNodeMixin):
            node.cfg_set_field(field)
            node.cfg_set_parent(self)
            if raw_value is not None:
                node.cfg_set_data(raw_value)
        return node

    def _update_runtime_attributes(self, field: Field):
        for attr_name, attr_value in self.cfg_get_runtime_attributes(type(field)).items():
            setattr(field, attr_name, attr_value)

    def cfg_set_runtime_attributes(self, FieldType: Type[Field], **kwargs):
        """
        Set runtime attributes for a specific Field. This attribute will recursively be applied
        to all child fields of the specified type (unless overridden in a child node). Calling
        this method will replace any previously set attributes.

        Context: some Field objects require special runtime attributes to convert correctly; for
        example, DiscordModelField subclasses need an instance of the Discord client to be able to
        look up conversions.

        To apply a runtime attribute for a given field anywhere in a config file, apply it to the
        file's :cls:`ConfigRoot` instance.

        :param FieldType: The Field class to set.
        :param kwargs: keyword arguments for the attributes to add.
        :return:
        """
        self._field_runtime_attributes[FieldType] = copy(kwargs)

    def cfg_get_runtime_attributes(self, FieldType: Type[Field]) -> Dict[str, Any]:
        """
        Get all runtime attributes applicable to a specified Field class. This will also search for
        superclasses of the specified Field class, and return a merged dict of all attributes found.
        """
        try:
            # get attributes
            resolved_attributes = self.__config_parent__.cfg_get_runtime_attributes(FieldType)
        except AttributeError:
            resolved_attributes = {}

        for MroFieldType in FieldType.__mro__:
            try:
                resolved_attributes.update(self._field_runtime_attributes[MroFieldType])
            except KeyError:
                pass
        return resolved_attributes

    @property
    def cfg_file(self) -> Optional[str]:
        try:
            return self.__config_root__.cfg_file
        except AttributeError:
            return None  # no root - non-file-attached object

    @property
    def cfg_path(self) -> Tuple:
        if self._parent_index is None:
            node_name = self.__config_field__.name or '<null>'
        else:
            node_name = self._parent_index

        try:
            return self.__config_parent__.cfg_path + (node_name,)
        except AttributeError:
            return node_name,

    @property
    def cfg_read_only(self) -> bool:
        try:
            return self.__config_root__.cfg_read_only
        except AttributeError:
            return False  # no root - non-file-attached object

    def __str__(self):
        """ String representation of this config object: returns file and config path. """
        file = self.cfg_file or '(No file)'
        path_parts = []
        for p in self.cfg_path:
            if isinstance(p, int):
                try:
                    path_parts[-1] += f'[{p:d}]'
                except IndexError:
                    path_parts.append(f'[{p:d}]')
            else:
                path_parts.append(p)

        return file + ':' + '.'.join(path_parts)


class ConfigModelMeta(type):
    """
    Metaclass for Config objects. Processes configuration fields and merges them according to
    inheritance structure, if needed.

    This metaclass should not be used directly. You should subclass :cls:`ConfigModel` instead.
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
                name_invalid = (value.name and mcs._is_reserved_name(value.name))
                attr_name_invalid = (not value.name and mcs._is_reserved_name(attr))
                if name_invalid or attr_name_invalid:
                    continue
                if value.name is None:
                    value.name = attr
                cls.__config_fields__[attr] = value
                delattr(cls, attr)

        return cls

    @staticmethod
    def _is_reserved_name(key):
        return key.startswith('_') or key.startswith('cfg_')


class ConfigModel(ConfigNodeMixin, metaclass=ConfigModelMeta):
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
    ConfigModel ``co`` and want to access the ``name`` key:

    1. Attribute access: ``co.name``
    2. Get method: ``co.get("name")``

    Similarly, for setting:

    1. Attribute access: ``co.name = "Eleanor"``
    2. Set method: ``co.set("name", "Eleanor")``

    This class implements a naïve ``__eq__()`` which compares the underlying raw data. This may
    mean that equivalent data, e.g. string "no" and boolean False on a BooleanField, will not
    compare equal.
    """
    __config_field__: ConfigModelField

    def __init__(self, **kwargs):
        super().__init__()
        self.__config_field__ = ConfigModelField(name='Unassigned', type=self.__class__)  # default
        self._data = {}
        self._converted = {}

        for key, value in kwargs.items():  # for creating new objects programmatically
            self.set(key, value)

    def cfg_set_data(self, raw_data: dict):
        self._data = raw_data
        self.clear_cache()

    @classmethod
    def cfg_get_field(cls, key: str) -> Field:
        """ Return the Field for a given key, or a PrimitiveField if the key is not known. """
        try:
            field = cls.__config_fields__[key]
        except KeyError:
            field = cls._get_default_field()
            field.name = key
        return field

    @staticmethod
    def _get_default_field() -> Field:
        return PrimitiveField(name=None, default=None, required=True, lazy=True)

    @classmethod
    def cfg_field_keys(cls) -> Iterable[str]:
        """
        Get all keys for known fields. This usually means fields defined in the
        ConfigModel subclass definition. See also :meth:`keys()`.
        """
        return cls.__config_fields__.keys()

    def keys(self) -> Iterable[str]:
        """
        Get all keys contained in the configuration data. This only returns keys actually defined
        in the configuration file. See also :meth:`cfg_field_keys`.
        """
        return self._data.keys()

    def clear_cache(self):
        """ Clear cache of read objects. If non-lazy, also re-convert all fields."""
        self._converted.clear()
        logger.info(f"{self!s}: Cache cleared.")

        # pre-convert all keys, if not lazy
        if not self.__config_field__.lazy:
            logger.info(f"{self!s}: Converting all data (non-lazy)...")
            # convert all defined keys in data
            for key in self.keys():
                self.get(key)

            # also convert all field keys, to check for missing required fields
            # don't worry about redundancy here: this will simply return from cache
            for key in self.cfg_field_keys():
                self.get(key)

    def get(self, key: str) -> Any:
        """
        Read a configuration value..

        If the key doesn't exist, behaviour depends on the key's associated :cls:`Field`: if the
        key is required, then :cls:`ConfigKeyError` is raised. Otherwise, the Field's default value
        is returned.

        :raises ConfigKeyError: Key doesn't exist
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """

        field = self.cfg_get_field(key)

        if key in self._converted:
            logger.debug(f"{self!s}: Read key '{key}' from converter cache.")
            node = self._converted[key]
            # make sure root/parent/field properly set
            # (non-lazy conversion can happen before root/parent are set)
            self._update_child_node(field, node)
            return node
        if key.startswith('_') or key.startswith('cfg_'):
            raise ConfigNameError(self.cfg_file, self.cfg_path, key)

        # retrieve raw data
        try:
            raw_value = self._data[field.name]
            logger.debug(f"{self!s}: Read key '{field.name}' from file.")
        except KeyError as e:
            if field.required:
                raise ConfigKeyError(self.cfg_file, self.cfg_path, field.name) from e
            else:
                logger.warning(f"{self!s}: Key '{key}' not found, using default.")
                raw_value = copy(field.default)
        else:
            if self.__config_field__.strict_keys and key not in self.cfg_field_keys():
                raise ConfigKeyError(self.cfg_file, self.cfg_path, key, 'key not allowed')

        # convert
        try:
            conv_value = self._convert_child_node(field, raw_value)
        except Exception as e:
            raise ConfigConverterError(self.cfg_file, self.cfg_path, key, raw_value) from e
        self._converted[key] = conv_value  # caching

        return conv_value

    def set(self, key: str, value):
        """
        Write a configuration value. Usage is similar to :meth:`KaztronConfig.set`.
        :raises ConfigConverterError: A converter error happened (that error will be passed as the
        cause of this one)
        """
        if self.cfg_read_only:
            raise ReadOnlyError(self.cfg_file)

        logger.info(f"{self!s}: Set key {key}")

        field = self.cfg_get_field(key)
        # strict_keys
        if self.__config_field__.strict_keys and key not in self.cfg_field_keys():
            raise ConfigKeyError(self.cfg_file, self.cfg_path, key, 'key not allowed')

        # serialise and (shallow) type-checking before setting
        ser_value = field.serialize(value)
        if not isinstance(ser_value, typing.get_args(ConfigPrimitive)):
            raise ConfigConverterError(self.cfg_file, self.cfg_path, key, value, ser_value)

        # save new value
        self._data[key] = ser_value

        # clear old cached value if needed
        # (DO NOT add the new object to cache - prefer to newly convert on next access)
        try:
            del self._converted[key]
        except KeyError:
            pass

        # if value is a config node, update its properties (in case obj continues to be used)
        self._update_child_node(field, value, self._data[key])

        # notify changes - for lazy writing
        self.cfg_notify_update(key, ser_value)

    def traverse(self, *args):
        """
        Traverse through a recursive ConfigModel tree and return the value. This method is basically
        a recursive :meth:`get()` convenience function. Will raise a ConfigKeyError if it is not
        possible to traverse through the given path. Cannot traverse through lists or dicts, only
        ConfigModels.
        """
        current = self
        for arg in args:
            current = current.get(arg)
        return current

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key: str, value):
        if not key.startswith('_') and not key.startswith('cfg_'):
            self.set(key, value)
        else:
            self.__dict__[key] = value

    def __repr__(self):
        """
        Technical representation of this object, including its data. This method may trigger
        a conversion of all keys, which may be time-consuming.
        """
        if not self.__config_field__.strict_keys:
            repr_dict = {key: repr(self.get(key)) for key in self.keys()}
        else:
            keys = set(self.keys()).intersection(set(self.cfg_field_keys()))
            repr_dict = {key: repr(self.get(key)) for key in keys}
        repr_data = ', '.join(f"{key}: {value}" for key, value in repr_dict.items())
        return f'<{self.__class__.__name__}({str(self)}) {{{repr_data}}}>'

    def __eq__(self, other: 'ConfigModel'):
        keys = self.cfg_field_keys() if self.__config_field__.strict_keys else self.keys()
        for key in keys:
            try:
                if self.get(key) != other.get(key):
                    return False
            except ConfigKeyError:
                return False
        return True

    def __contains__(self, key):
        return key in self.keys()


class ConfigRoot(ConfigModel):
    """
    ConfigModel which represents the root of a configuration file. Instances are provided
    by the framework; this class should typically not be instantiated directly.
    """

    def __init__(self, config: 'KaztronConfig'):
        super().__init__()
        self._config = config
        self.cfg_set_field(ConfigModelField(name='root', type=self.__class__))
        self.__config_parent__ = None
        self.__config_root__ = self

    def cfg_set_parent(self, parent: ConfigModel):
        raise NotImplementedError("ConfigRoot cannot have parent")

    def cfg_register_model(self, key: str, model: Type[ConfigModel], **kwargs):
        """
        Register the ConfigModel to use for a given key. kwargs are passed to the
        underlying ConfigModelField describing that key (except ``type``).
        """
        if 'name' not in kwargs:
            kwargs['name'] = key
        kwargs['type'] = model
        self.__config_fields__[key] = field = ConfigModelField(**kwargs)
        logger.info(f"ConfigRoot({self.cfg_file}): registered key '{key}' to field {field}")

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

    def cfg_notify_update(self, _=None, __=None):
        self._config.notify()

    def cfg_write(self):
        self._config.write()


class ConfigList(ConfigNodeMixin, MutableSequence):
    """
    Model for a configuration file list, acting like a normal Python list. This class is intended
    to work well with :cls:`ConfigModel`, allowing for access and conversion of a configuration
    model list and to be contained within the hierarchy of a larger Config Model, while acting
    like a normal Python list to the user.

    This class is generally designed to contain lists of a single type, defined by
    :attr:`ListField.type`. If this attribute is not specified or is set to :cls:`PrimitiveField`,
    mixed list contents will be accepted.
    """
    def __init__(self, iterable=None, *, field: ListField=None):
        """
        :param field: Set the :cls:`ListField` containing config system metadata about this object.
            Defaults to a ListField with type PrimitiveField. Required if ``iterable`` is passed.
        :param iterable: Initial data. This is assumed to be Python objects and is converted to
            primitive representation (i.e. this is equivalent to calling ``config_list.append(x)``
            for each object in this iterable). It is not appropriate for setting raw config file
            data.
        """
        super().__init__()
        self.__config_field__ = field or ListField(name='Unassigned', type=PrimitiveField())

        self._converted: List[Any] = []
        self._convert_map: List[bool] = []  # for lazy conversion
        self._serialized_data: List[ConfigPrimitive] = []

        if iterable:
            for value in iterable:
                self.append(value)

    def cfg_set_data(self, data: list):
        """
        Pass the raw primitive data that this ConfigList represents, and set up caching (and non-
        lazy conversion if applicable).

        :param data: The raw list from the config file.
        :raise IndexError: invalid length
        """
        max_ok = not self.__config_field__.max_len or len(data) <= self.__config_field__.max_len
        min_ok = len(data) >= self.__config_field__.min_len
        if not max_ok or not min_ok:
            raise IndexError("invalid length")

        self._serialized_data = data
        self.clear_cache()

    def clear_cache(self):
        """ Clear cache of read objects. If non-lazy, also re-convert all fields."""
        if self._serialized_data is not None:  # allows for clearing data
            if self.__config_field__.lazy:
                self._converted = [None] * len(self._serialized_data)
                self._convert_map = [False] * len(self._serialized_data)
            else:
                self._converted = self.__config_field__.convert(self._serialized_data)
                self._convert_map = [True] * len(self._serialized_data)
        else:
            self._converted = None
            self._convert_map = None
        logger.info(f"{self!s}: Cache cleared.")

    def __len__(self):
        return len(self._serialized_data)

    def _update_child_node(self, field, node, raw_value=None, index: int=None):
        node = super()._update_child_node(field, node, raw_value)
        if index is not None and isinstance(node, ConfigNodeMixin):
            node._parent_index = index
        return node

    def _convert_child_node(self, field: Field, raw_value: ConfigPrimitive, index: int=None) -> Any:
        node = super()._convert_child_node(field, raw_value)
        if index is not None and isinstance(node, ConfigNodeMixin):
            node._parent_index = index
        return node

    def __getitem__(self, index: int):
        field = self.__config_field__.type
        if self._convert_map[index]:
            obj_item = self._converted[index]
            # make sure root/parent/field properly set
            # (non-lazy conversion can happen before root/parent are set)
            self._update_child_node(field, obj_item, index=index)
        else:
            # convert item
            obj_item = self._convert_child_node(field, self._serialized_data[index], index=index)
            # set caching
            self._converted[index] = obj_item
            self._convert_map[index] = True

        return obj_item

    def __setitem__(self, index: int, obj_value):
        field = self.__config_field__.type
        self._serialized_data[index] = field.serialize(obj_value)

        # update the old object, in case it continues to be used
        self._update_child_node(field, obj_value, self._serialized_data[index], index=index)

        # don't store this value in _converted cache - avoids problems with references/mutable types
        # we will convert this from the raw data on the next access to this index instead
        self._convert_map[index] = False
        self.cfg_notify_update(self.__config_field__.name, self._serialized_data)

    def __delitem__(self, index: int):
        if self.__config_field__.min_len and len(self) <= self.__config_field__.min_len:
            # this would bring us below minimum length
            raise IndexError(index, self.__config_field__.min_len)

        del self._serialized_data[index]
        del self._converted[index]
        del self._convert_map[index]
        self.cfg_notify_update(self.__config_field__.name, self._serialized_data)

    def insert(self, index: int, obj_value):
        self._serialized_data.insert(index, None)
        self._converted.insert(index, None)
        self._convert_map.insert(index, False)
        self[index] = obj_value  # calls __setitem__ which handles all needed conversions
        self.cfg_notify_update(self.__config_field__.name, self._serialized_data)

    def __repr__(self):
        """
        Technical representation of this object, including its data. This method may trigger
        a conversion of all keys, which may be time-consuming.
        """
        repr_data = ', '.join(repr(item) for item in self)
        return f'<{self.__class__.__name__}({str(self)}) [{repr_data}]>'

    def __eq__(self, other: Iterable):
        if other is None or len(self) != len(other):
            return False
        return all(val1 == val2 for val1, val2 in zip(self, other))


class ConfigDict(ConfigNodeMixin, MutableMapping):
    """
    Model for a configuration file list, acting like a normal Python dict. This class is intended
    to work well with :cls:`ConfigModel`, allowing for access and conversion of a configuration
    model list and to be contained within the hierarchy of a larger Config Model, while acting
    like a normal Python dict to the user.

    This class is generally designed to contain mappings of a single type, defined by
    :attr:`DictField.type`. If this attribute is not specified or is set to :cls:`PrimitiveField`,
    mixed list contents will be accepted.

    For dicts being used as key-value configurations containing mixed value types, a
    :cls:`ConfigModel` is preferred to a ConfigDict.
    """
    def __init__(self, mapping=None, *, field: DictField=None):
        super().__init__()
        self.__config_field__ = field or DictField(name='Unassigned', type=PrimitiveField())
        self._converted: Dict[str, Any] = {}
        self._serialized_data: Dict[str, ConfigPrimitive] = {}

        if mapping:
            for key, value in mapping.items():
                self[key] = value

    def cfg_set_data(self, data: Dict[str, Any]):
        """
        Pass the raw primitive data that this ListField represents, and set up caching (and non-lazy
        conversion if applicable).

        :param data: The raw list from the config file. Can be None to clear data.
        """
        self._serialized_data = data
        if self.__config_field__.lazy:
            self._converted = {}
        elif self._serialized_data is not None:  # allows for clearing data by setting data to None
            self._converted = self.__config_field__.convert(self._serialized_data)

    def clear_cache(self):
        """ Clear cache of read objects. If non-lazy, also re-convert all fields."""
        if self.__config_field__.lazy:
            self._converted = {}
        elif self._serialized_data is not None:  # allows for clearing data by setting data to None
            self._converted = self.__config_field__.convert(self._serialized_data)
        logger.info(f"{self!s}: Cache cleared.")

    def __iter__(self):
        return iter(self._serialized_data)  # iterates over keys

    def __len__(self):
        return len(self._serialized_data)

    def _convert_child_node(self, field: Field, raw_value: ConfigPrimitive, key: str=None) -> Any:
        node_field = copy(field)
        if key is not None:
            node_field.name = key
        return super()._convert_child_node(node_field, raw_value)

    def __getitem__(self, key: str):
        field = self.__config_field__.type
        try:
            obj_item = self._converted[key]
            # make sure root/parent/field properly set
            # (non-lazy conversion can happen before root/parent are set)
            self._update_child_node(field, obj_item)
        except KeyError:
            obj_item = self._convert_child_node(field, self._serialized_data[key], key)
            self._converted[key] = obj_item
        return obj_item

    def __setitem__(self, key: str, obj_value):
        if not isinstance(key, str):
            raise ValueError("key must be string")
        field = self.__config_field__.type
        self._serialized_data[key] = field.serialize(obj_value)

        # update the object in case it continues to be used
        self._update_child_node(field, obj_value, self._serialized_data[key])

        # don't store this value in _converted cache - avoids problems with references/mutable types
        # we will convert this from the raw data on the next access to this index instead
        try:
            del self._converted[key]
        except KeyError:
            pass  # wasn't in conversion cache
        self.cfg_notify_update(self.__config_field__.name, self._serialized_data)

    def __delitem__(self, key: str):
        del self._serialized_data[key]
        try:
            del self._converted[key]
        except KeyError:
            pass  # not in cache
        self.cfg_notify_update(self.__config_field__.name, self._serialized_data)

    def __repr__(self):
        """
        Technical representation of this object, including its data. This method may trigger
        a conversion of all keys, which may be time-consuming.
        """
        repr_data = ', '.join(key + ': ' + repr(item) for key, item in self.items())
        return f'<{self.__class__.__name__}({str(self)}) {{{repr_data}}}>'


@dataclass
class DiscordDummy:
    """ A class that represents a dummy Discord model (by ID or by name). """
    id: int = None
    name: str = None
