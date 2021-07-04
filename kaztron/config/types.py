import typing
from typing import List, Dict, Pattern, Union, Any, Type, TYPE_CHECKING
from abc import ABC, abstractmethod
from collections.abc import Iterable, Container, Sized, MutableSequence, MutableMapping

import dataclasses
from dataclasses import dataclass
import logging

from datetime import datetime, timezone, timedelta

if TYPE_CHECKING:
    from munch import Munch
    from kaztron.config.object import ConfigObject

ConfigDict = Union[dict, Munch]
ConfigPrimitive = Union[str, int, float, list, ConfigDict]

logger = logging.getLogger("kaztron.config")


@dataclass
class Field(ABC):
    """
    Represents a single field in a config file, that is to say, a ``key: value`` pair in a config
    file dict (a.k.a. table in TOML, object in JSON).

    Use Field subclasses in a :cls:`ConfigObject` subclass definition to set up the schema for a
    config object representation.

    Field subclasses have two purposes: 1) provide information about the field, such as its type,
    its key name and whether it is a required field, to be used by :cls:`ConfigObject`;
    2) provide conversion from config-file primitive types to Python objects and back.

    The type represented by a Field subclass should always be one of:

    1. an immutable object;
    2. a primitive (including mutable primitives like ListField, DictField) (see subclasses of
       :cls:`PrimitiveField`); or
    3. a :cls:`ConfigObject` subclass, represented by :cls:`ConfigObjectField`.

    You can subclass Field, or one of the other Field subclasses, to define a custom type. You
    primarily need to implement :meth:`convert` and :meth:`serialize`, along with any parameters
    needed for the type (e.g. limits, parameters used for validation or conversion, etc.).
    For most custom config types, point 1 should apply. Immutability is required to ensure that
    changes to the object must go through the config manager so that the change can be saved to
    file (i.e., editing an immutable object in the config involves assigning a new object to it,
    which cannot happen "sneakily" unlike editing a mutable object). ListField and DictField get
    around this by wrapping the original list or dict and providing its mutation methods.

    :ivar name: Name of the field. If None, use the :cls:`ConfigObject` attribute name. This defines
        the key to look up in the underlying config data: it can be different than the attribute
        name used to access this field in the :cls:`ConfigObject`.
    :ivar required: Whether this field is required.
    :ivar default: Default value. Only meaningful if ``required`` is ``False``. If this field
        is not defined, this value is returned instead. (It will not be written to the source
        data.) Cannot be ``None``.
    :ivar lazy: If true, validate only on access. Otherwise, validate when initialised. Validation
        involves verifying required fields and verifying that they :meth:`~.convert` properly.
    :ivar parent: The parent :cls:`ConfigObject`. This should not be set on construction, but will
        automatically be set by the parent :cls:`ConfigObject`.
    """
    name: str
    default: Any = None
    required: bool = False
    lazy: bool = True

    @abstractmethod
    def convert(self, value: ConfigPrimitive) -> Any:
        """
        Must be overridden. Convert a config field value to a Python object representation
        (depending on the field type). Any validation needed should happen here too.

        :raise ValueError: Invalid value or validation of data failed.
        :raise TypeError: Invalid type in config field
        """

    @abstractmethod
    def serialize(self, value: Any) -> ConfigPrimitive:
        """
        Must be overridden. Encode a Python object corresponding to this field type to its
        serialised representation in one of the config primitive types. Any validation needed
        should happen here too.

        :raise ValueError: Invalid value or validation of data failed.
        :raise TypeError: Invalid type passed.
        """


@dataclass
class PrimitiveField(Field):
    lazy: bool = True

    def convert(self, value: ConfigPrimitive):
        return value

    def serialize(self, value: ConfigPrimitive) -> ConfigPrimitive:
        if not isinstance(value, typing.get_args(ConfigPrimitive)):
            raise TypeError("PrimitiveField value must be a config primitive")
        return value


@dataclass
class StringField(PrimitiveField):
    """
    Represents a string field. This field is a strict converter: type passed must be string. If
    trying to write the ``str()`` or ``repr()`` representation of an object, then these functions
    should be explicitly called when writing to the config file.

    :ivar len: Length of field. If not specified, no limit.
    :ivar minlen: Minimum length of field. Optional, by default allows empty string. Set to
        "1" if field must be non-empty.
    :ivar validation: Optional. Regular expression pattern for validation.
    :ivar validation_help: Optional. Text used for error message if validation fails.
    """
    len: int = -1
    minlen: int = 0
    validation: Pattern = None
    validation_help: str = None

    def convert(self, value: str) -> str:
        """ Validate type and length. This is a *strict* converter: ``value`` must be str."""
        if not isinstance(value, str):
            raise TypeError("StringField value must be string")
        if not self._is_valid_length(value):
            raise ValueError("invalid length")
        if not self.validation.search(value) is None:
            raise ValueError("validation pattern error")
        return value

    def serialize(self, value: str) -> str:
        """
        Validate string. This is a *strict* converter: ``value`` must be str. Use ``str()``
        explicitly to convert an object to string.
        """
        if not isinstance(value, str):
            raise TypeError("StringField value must be string")
        if not self._is_valid_length(value):
            raise ValueError("invalid length")
        return value

    def _is_valid_length(self, str_val: str):
        is_valid_length = self.minlen <= len(str_val) <= self.len
        is_valid_minlength = self.len is None and self.minlen <= len(str_val)
        return is_valid_length or is_valid_minlength


@dataclass
class IntegerField(PrimitiveField):
    """
    Represents an integer field. This field will reject integer values out of range.

    :ivar min: Minimum value. Optional. Note that if not specified, negative values are permitted.
    :ivar max: Maximum value. Optional.
    """
    max: int = None
    min: int = None

    def convert(self, value: int) -> int:
        """ Validate integer's limits. """
        value = int(value)
        if not self._is_valid_range(value):
            raise ValueError("invalid range")
        return value

    def serialize(self, value: int) -> int:
        """ Validate integer's limits. """
        value = int(value)
        if not self._is_valid_range(value):
            raise ValueError("invalid range")
        return value

    def _is_valid_range(self, value: int):
        is_min_ok = self.min is None or self.min <= value
        is_max_ok = self.max is None or value <= self.max
        return is_min_ok and is_max_ok


@dataclass
class ConstrainedIntegerField(IntegerField):
    """
    Represents an integer field. This field will automatically constrain out-of-range values (e.g.
    a too-large value will automatically be converted to the max value).

    Same instance variables as :cls:`IntegerField`.
    """
    def convert(self, value: int) -> int:
        """
        Validate integer's limits. If the value is out-of-range, this function will return the
        min/max value instead.
        """
        value = int(value)
        constr_value = max(self.min, min(self.max, value))
        if value != constr_value:
            logging.warning(f"{self.name}: Read value {value} constrained to {constr_value}")
        return constr_value

    def serialize(self, value: int) -> int:
        """
        Validate integer's limits. If the value is out-of-range, this function will return the
        min/max value instead.
        """
        value = int(value)
        constr_value = max(self.min, min(self.max, value))
        if constr_value != value:
            logging.warning(f"{self.name}: Serialize value {value} constrained to {constr_value}")
            return constr_value


class FloatField(PrimitiveField):
    """
    Represents a floating-point field. This field will reject values out of range.

    :ivar min: Minimum value. Optional. Note that if not specified, negative values are permitted.
    :ivar max: Maximum value. Optional.
    :ivar allow_special: Allow infinities and NaN.
    """
    max: float = None
    min: float = None
    allow_special: bool = None

    INF = float('inf')
    NINF = float('-inf')
    NAN = float('nan')

    def convert(self, value: float) -> float:
        """ Validate float's limits. """
        value = float(value)
        if not self.is_allowed_special(value):
            raise ValueError("Infinities and NaN not allowed")
        if not self._is_valid_range(value):
            raise ValueError("invalid range")
        return value

    def serialize(self, value: float) -> float:
        """ Validate float's limits. """
        value = float(value)
        if not self.is_allowed_special(value):
            raise ValueError("Infinities and NaN not allowed")
        if not self._is_valid_range(value):
            raise ValueError("invalid range")
        return value

    def is_allowed_special(self, value: float):
        return self.allow_special and (value == self.INF or value == self.NINF or value == self.NAN)

    def _is_valid_range(self, value: float):
        is_min_ok = self.min is None or self.min <= value
        is_max_ok = self.max is None or value <= self.max
        return is_min_ok and is_max_ok


@dataclass
class ConstrainedFloatField(FloatField):
    """
    Represents a floating point field. This field will automatically constrain out-of-range values
    (e.g. a too-large value will automatically be converted to the max value).

    Same instance variables as :cls:`IntegerField`.
    """

    def convert(self, value: float) -> float:
        """ Validate float's limits. """
        value = float(value)
        constr_value = max(self.min, min(self.max, value))
        if not self.is_allowed_special(value):
            raise ValueError("Infinities and NaN not allowed")
        if value != constr_value:
            logging.warning(f"{self.name}: Read value {value} constrained to {constr_value}")
        return constr_value

    def serialize(self, value: float) -> float:
        """ Validate float's limits. """
        value = float(value)
        constr_value = max(self.min, min(self.max, value))
        if not self.is_allowed_special(value):
            raise ValueError("Infinities and NaN not allowed")
        if value != constr_value:
            logging.warning(f"{self.name}: Serialize value {value} constrained to {constr_value}")
        return value


@dataclass
class GenericDatetimeField(Field, ABC):
    """
    Represents a datetime object. This is an abstract base class for concrete datetime datatypes
    like :cls:`TimestampField` and :cls:`DatetimeField`.
    """


@dataclass
class TimestampField(GenericDatetimeField):
    """
    Represents a datetime stored as a UNIX timestamp. This field assumes that this value is always
    stored as a UNIX timestamp (integer datatype), and provides a Python datetime object in the UTC
    timezone (timezone-aware, as per `datetime.utcfromtimestamp()`_ recommendation).

    .. _`datetime.utcfromtimestamp()`: https://docs.python.org/3/library/datetime.html#datetime.datetime.utcfromtimestamp
    """
    def convert(self, value: Union[int, float]) -> datetime:
        """ Convert UNIX timestamp to datetime. Returned object is UTC (timezone-aware). """
        # equivalent to fromtimestamp(), but with potentially wider range
        # note that datetime doesn't support leap seconds so this method doesn't differ in that way
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=value)

    def serialize(self, value: datetime) -> float:
        """ Convert a datetime to a timestamp. """
        return value.timestamp()


@dataclass
class DatetimeField(GenericDatetimeField):
    """
    Represents a datetime stored in an RFC-3339 string format.

    While other formats may be accepted by this Field type, only RFC-3339 compliant formats are
    officially supported. Parsing of other formats should be considered undefined (as an
    implementation detail).

    Exceptionally, the full-date format (as defined in RFC-339 section 5.6) is also supported.
    In this case, the time is assumed to be T00:00Z (midnight UTC).

    The returned datetime is timezone-aware. If none is specified, it is set to UTC.

    The parser used for this type of field may be quite slow. :cls:`TimestampField` is preferable
    if performance is a concern, for reading large numbers of datetimes from config/state files.
    """
    def convert(self, value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def serialize(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


@dataclass
class ContainerField(Field, Container, Iterable, Sized, ABC):
    """
    Represents any kind of config file container. This is an abstract base class.

    Unlike scalar fields, which primarily provide validation and conversion of data, container
    fields replace the container they represent and provide all the normal access methods to the
    data directly. They also provide conversion and validation of the contents.
    """
    # TODO: separate the Fields from the implementor classes
    # TODO: make sure implementor has root/parent; remove parent from the container field classes
    type: Field = PrimitiveField(name=None)

    @abstractmethod
    def init_data(self, data):
        """
        Pass the raw primitive container that this field represents, and set up caching (and
        non-lazy conversion if applicable).

        :param data: The raw list from the config file. Can be None to clear the data.
        :raise IndexError: invalid length, if validated
        """
        pass

    @property
    @abstractmethod
    def is_ready(self):
        """ Return True if data has been initialized via :meth:`init_data`. """


@dataclass
class ListField(ContainerField, MutableSequence):
    """
    Represents a list. See also :cls:`ContainerField` for more info.

    If the ``type`` attribute is left default, then this is a naïve list: it will not convert or
    validate values and can contain mixed primitive types. If the ``type`` attribute is defined as
    any :cls:`Field`, then the list will be converted and validated using that Field object, and
    can only contain compatible values.
    """
    # TODO: more logging
    max_len: int = None
    min_len: int = 0
    _converted: list = dataclasses.field(init=False)
    _convert_map: List[bool] = dataclasses.field(init=False)  # for lazy conversion
    _serialized_data: list = dataclasses.field(init=False)

    def __post_init__(self):
        self._converted = None
        self._convert_map = None
        self._serialized_data = None

    def init_data(self, data: list):
        """
        Pass the raw primitive data that this ListField represents, and set up caching (and non-lazy
        conversion if applicable).

        :param data: The raw list from the config file.
        :raise IndexError: invalid length
        """
        if len(data) > self.max_len or len(data) < self.min_len:
            raise IndexError("invalid length")

        self._serialized_data = data
        if self._serialized_data is not None:  # allows for clearing data
            if self.lazy:
                self._converted = [None] * len(self._serialized_data)
                self._convert_map = [False] * len(self._serialized_data)
            else:
                self._converted = self.convert(self._serialized_data)
                self._convert_map = [True] * len(self._serialized_data)
        else:
            self._converted = None
            self._convert_map = None

    @property
    def is_ready(self):
        return self._serialized_data is not None

    def _validate_length(self) -> bool:
        return (self.max_len is None and self.min_len <= len(self)) or \
               (self.min_len <= len(self) <= self.max_len)

    def __len__(self):
        return len(self._serialized_data)

    def __getitem__(self, index: int):
        if self._convert_map[index]:
            obj_item = self._converted[index]
        else:
            obj_item = self.type.convert(self._serialized_data[index])
            self._converted[index] = obj_item
            self._convert_map[index] = True
        return obj_item

    def __setitem__(self, index: int, obj_value):
        self._serialized_data[index] = self.type.serialize(obj_value)
        # don't store this value in _converted cache - avoids problems with references/mutable types
        # we will convert this from the raw data on the next access to this index instead
        self._convert_map[index] = False
        self.parent.notify_update(self.name, self._serialized_data)

    def __delitem__(self, index: int):
        if len(self) <= self.min_len:  # this would bring us below minimum length
            raise IndexError(index, self.min_len)

        del self._serialized_data[index]
        del self._converted[index]
        del self._convert_map[index]
        self.parent.notify_update(self.name, self._serialized_data)

    def insert(self, index: int, obj_value):
        if len(self) >= self.max_len:  # this would bring us above maximum length
            raise IndexError(index, self.max_len)

        self._serialized_data.insert(index, self.type.serialize(obj_value))

        # same comment here as in __setitem__
        self._converted.insert(index, None)
        self._convert_map.insert(index, False)

        self.parent.notify_update(self.name, self._serialized_data)

    def convert(self, raw_list: List[ConfigPrimitive]) -> List:
        return [self.type.convert(raw_item) for raw_item in raw_list]

    def serialize(self, obj_list: List[Any]) -> List[ConfigPrimitive]:
        return [self.type.serialize(obj_item) for obj_item in obj_list]


@dataclass
class DictField(ContainerField, MutableMapping):
    """
    Represents a dict/table with string keys. See also :cls:`ContainerField` for more info.

    If the ``type`` attribute is left default, then this is a naïve dict: it will not convert or
    validate values and can contain mixed primitive types. If the ``type`` attribute is defined as
    any :cls:`Field`, then the list will be converted and validated using that Field object, and
    can only contain compatible values.
    """
    # TODO: more logging
    _converted: Dict[str, Any] = dataclasses.field(init=False)
    _serialized_data: Dict[str, ConfigPrimitive] = dataclasses.field(init=False)

    def __post_init__(self):
        self._converted = None
        self._serialized_data = None

    def init_data(self, data: Dict[str, Any]):
        """
        Pass the raw primitive data that this ListField represents, and set up caching (and non-lazy
        conversion if applicable).

        :param data: The raw list from the config file. Can be None to clear data.
        """
        self._serialized_data = data
        if self.lazy:
            self._converted = {}
        elif self._serialized_data is not None:  # allows for clearing data by setting data to None
            self._converted = self.convert(self._serialized_data)

    @property
    def is_ready(self):
        return self._serialized_data is not None

    def __iter__(self):
        return iter(self._serialized_data)  # iterates over keys

    def __len__(self):
        return len(self._serialized_data)

    def __getitem__(self, key: str):
        try:
            return self._converted[key]
        except KeyError:
            obj_item = self.type.convert(self._serialized_data[key])
            self._converted[key] = obj_item
            return obj_item

    def __setitem__(self, key: str, obj_value):
        self._serialized_data[key] = self.type.serialize(obj_value)
        # don't store this value in _converted cache - avoids problems with references/mutable types
        # we will convert this from the raw data on the next access to this index instead
        del self._converted[key]
        self.parent.cfg_notify_update(self.name, self._serialized_data)

    def __delitem__(self, key: str):
        del self._serialized_data[key]
        del self._converted[key]
        self.parent.cfg_notify_update(self.name, self._serialized_data)

    def convert(self, raw_dict: Dict[str, ConfigPrimitive]) -> Dict[str, Any]:
        return {key: self.type.convert(raw_item) for key, raw_item in raw_dict.items()}

    def serialize(self, obj_dict: Dict[str, Any]) -> Dict[str, ConfigPrimitive]:
        return {key: self.type.serialize(obj_item) for key, obj_item in obj_dict.items()}


@dataclass
class ConfigObjectField(Field):
    """
    Field that contains a ConfigObject. This is an alternative to :cls:`DictField`. It allows
    object-oriented access to this field, along with a number of configuration file convenience
    methods and nesting of further downstream fields; DictField, on the other hand, only allows
    primitive (non-converted) access to its values or assumes that all values are of the same
    converted type.

    This field, in particular, can be used within a :Cls:`ListField`, :cls:`DictField`, or another
    :cls:`ConfigObjectField` in order to allow nested object-oriented access to the entire
    config file structure.

    This field represents a ConfigObject subclass instance.

    :ivar type: The ConfigObject class that this field represents.
    :ivar strict_keys: If True, then keys not configured as a field by the ConfigObject are
        rejected. If False, writing or reading a key not configured is permitted, and will be
        treated as a generic PrimitiveField (i.e. will read or write any primitive type).
    """
    type: Type[ConfigObject]
    strict_keys = True

    def convert(self, value: dict) -> ConfigObject:
        conv_obj = self.type()
        conv_obj.cfg_set_field(self)
        conv_obj.cfg_set_data(value)
        return conv_obj

    def serialize(self, value: ConfigObject) -> dict:
        return {key: value.get(key) for key in value.keys()}
