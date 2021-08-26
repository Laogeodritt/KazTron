import typing
from typing import List, Dict, Pattern, Union, Any, Type, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
from munch import Munch

if TYPE_CHECKING:
    from kaztron.config.object import ConfigModel

ConfigDict = Union[dict, Munch]
ConfigPrimitive = Union[str, int, float, list, ConfigDict]

logger = logging.getLogger("kaztron.config")


__all__ = 'Field', 'PrimitiveField', 'StringField', 'BooleanField', \
          'IntegerField', 'ConstrainedIntegerField', 'FloatField', 'ConstrainedFloatField', \
          'TimestampField', 'DatetimeField', \
          'ListField', 'DictField', 'ConfigModelField', \
          'ConfigPrimitive'


# TODO: standardise ValueError raised? e.g. (message, value, field)

@dataclass
class Field(ABC):
    """
    Represents a single field in a config file, that is to say, a ``key: value`` pair in a config
    file dict (a.k.a. table in TOML, object in JSON).

    Use Field subclasses in a :cls:`ConfigModel` subclass definition to set up the schema for a
    config object representation.

    Field subclasses have two purposes: 1) provide information about the field, such as its type,
    its key name and whether it is a required field, to be used by :cls:`ConfigModel`;
    2) provide conversion from config-file primitive types to Python objects and back.

    The type represented by a Field subclass should always be one of:

    1. an immutable object;
    2. a primitive (including mutable primitives like ListField, DictField) (see subclasses of
       :cls:`PrimitiveField`); or
    3. a :cls:`ConfigModel` subclass, represented by :cls:`ConfigModelField`.

    You can subclass Field, or one of the other Field subclasses, to define a custom type. You
    primarily need to implement :meth:`convert` and :meth:`serialize`, along with any parameters
    needed for the type (e.g. limits, parameters used for validation or conversion, etc.).
    For most custom config types, point 1 should apply. Immutability is required to ensure that
    changes to the object must go through the config manager so that the change can be saved to
    file (i.e., editing an immutable object in the config involves assigning a new object to it,
    which cannot happen "sneakily" unlike editing a mutable object). ListField and DictField get
    around this by wrapping the original list or dict and providing its mutation methods.

    :ivar name: Name of the field. If None, use the :cls:`ConfigModel` attribute name. This defines
        the key to look up in the underlying config data: it can be different than the attribute
        name used to access this field in the :cls:`ConfigModel`.
    :ivar required: Whether this field is required.
    :ivar default: Default value. Only meaningful if ``required`` is ``False``. If this field
        is not defined, this value is returned instead. (It will not be written to the source
        data.) Cannot be ``None``.
    :ivar lazy: If true, validate only on access. Otherwise, validate when initialised. Validation
        involves verifying required fields and verifying that they :meth:`~.convert` properly.
    :ivar parent: The parent :cls:`ConfigModel`. This should not be set on construction, but will
        automatically be set by the parent :cls:`ConfigModel`.
    """
    name: Optional[str] = None
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
    len: int = None
    minlen: int = 0
    validation: Pattern = None
    validation_help: str = None

    def convert(self, value: str) -> str:
        """ Validate type and length. This is a *strict* converter: ``value`` must be str."""
        if not isinstance(value, str):
            raise TypeError("StringField value must be string")
        if not self._is_valid_length(value):
            raise ValueError("invalid length")
        if self.validation and self.validation.search(value) is None:
            raise ValueError(self.validation_help or "validation pattern error")
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
        if self.validation and self.validation.search(value) is None:
            raise ValueError(self.validation_help or "validation pattern error")
        return value

    def _is_valid_length(self, str_val: str):
        is_valid_min = self.minlen <= len(str_val)
        is_valid_max = self.len is None or len(str_val) <= self.len
        return is_valid_max and is_valid_min


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
        constr_value = int(value)
        if self.min is not None:
            constr_value = max(self.min, constr_value)
        if self.max is not None:
            constr_value = min(self.max, constr_value)
        if value != constr_value:
            logging.warning(f"{self.name}: Read value {value} constrained to {constr_value}")
        return constr_value

    def serialize(self, value: int) -> int:
        """
        Validate integer's limits. If the value is out-of-range, this function will return the
        min/max value instead.
        """
        constr_value = int(value)
        if self.min is not None:
            constr_value = max(self.min, constr_value)
        if self.max is not None:
            constr_value = min(self.max, constr_value)
        if constr_value != value:
            logging.warning(f"{self.name}: Serialize value {value} constrained to {constr_value}")
        return constr_value


@dataclass
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
        return self.allow_special or \
               not (value == self.INF or value == self.NINF or value == self.NAN)

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
        constr_value = float(value)
        if not self.is_allowed_special(constr_value):
            raise ValueError("Infinities and NaN not allowed")
        if self.min is not None:
            constr_value = max(self.min, constr_value)
        if self.max is not None:
            constr_value = min(self.max, constr_value)
        if value != constr_value:
            logging.warning(f"{self.name}: Read value {value} constrained to {constr_value}")
        return constr_value

    def serialize(self, value: float) -> float:
        """ Validate float's limits. """
        constr_value = float(value)
        if not self.is_allowed_special(constr_value):
            raise ValueError("Infinities and NaN not allowed")
        if self.min is not None:
            constr_value = max(self.min, constr_value)
        if self.max is not None:
            constr_value = min(self.max, constr_value)
        if value != constr_value:
            logging.warning(f"{self.name}: Serialize value {value} constrained to {constr_value}")
        return constr_value


@dataclass
class BooleanField(PrimitiveField):
    def convert(self, value) -> bool:
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            if value.lower() in ('0', 'off', 'no', 'disabled', 'false'):
                return False
            if value.lower() in ('1', 'on', 'yes', 'enabled', 'true'):
                return True
            raise ValueError("string value is not a known boolean word")
        else:
            return bool(value)

    def serialize(self, value) -> bool:
        return self.convert(value)


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
class ContainerField(Field, ABC):
    """
    Represents any kind of config file container. This is an abstract base class.

    Unlike scalar fields, which primarily provide validation and conversion of data, container
    fields replace the container they represent and provide all the normal access methods to the
    data directly. They also provide conversion and validation of the contents.
    """
    type: Field = PrimitiveField(name=None)


@dataclass
class ListField(ContainerField):
    """
    Represents a list. See also :cls:`ContainerField` for more info.

    If the ``type`` attribute is left default, then this is a naïve list: it will not convert or
    validate values and can contain mixed primitive types. If the ``type`` attribute is defined as
    any :cls:`Field`, then the list will be converted and validated using that Field object, and
    can only contain compatible values.
    """
    max_len: int = None
    min_len: int = 0

    def _validate_length(self, d) -> bool:
        return (self.max_len is None and self.min_len <= len(d)) or \
               (self.min_len <= len(d) <= self.max_len)

    def convert(self, raw_list: List[ConfigPrimitive]) -> List:
        if not self._validate_length(raw_list):
            raise ValueError("invalid length", raw_list, self)
        return [self.type.convert(raw_item) for raw_item in raw_list]

    def serialize(self, obj_list: List[Any]) -> List[ConfigPrimitive]:
        if not self._validate_length(obj_list):
            raise ValueError("invalid length", obj_list, self)
        return [self.type.serialize(obj_item) for obj_item in obj_list]


@dataclass
class DictField(ContainerField):
    """
    Represents a dict/table with string keys. See also :cls:`ContainerField` for more info.

    If the ``type`` attribute is left default, then this is a naïve dict: it will not convert or
    validate values and can contain mixed primitive types. If the ``type`` attribute is defined as
    any :cls:`Field`, then the dict will be converted and validated using that Field object, and
    can only contain compatible values.
    """

    def convert(self, raw_dict: Dict[str, ConfigPrimitive]) -> Dict[str, Any]:
        return {key: self.type.convert(raw_item) for key, raw_item in raw_dict.items()}

    def serialize(self, obj_dict: Dict[str, Any]) -> Dict[str, ConfigPrimitive]:
        return {key: self.type.serialize(obj_item) for key, obj_item in obj_dict.items()}


@dataclass
class ConfigModelField(Field):
    """
    Field that contains a ConfigModel. This is an alternative to :cls:`DictField`. It allows
    object-oriented access to this field, along with a number of configuration file convenience
    methods and nesting of further downstream fields; DictField, on the other hand, only allows
    primitive (non-converted) access to its values or assumes that all values are of the same
    converted type.

    This field, in particular, can be used within a :Cls:`ListField`, :cls:`DictField`, or another
    :cls:`ConfigModelField` in order to allow nested object-oriented access to the entire
    config file structure.

    This field represents a ConfigModel subclass instance.

    :ivar type: The ConfigModel class that this field represents.
    :ivar strict_keys: If True, then keys not configured as a field by the ConfigModel are
        rejected. If False, writing or reading a key not configured is permitted, and will be
        treated as a generic PrimitiveField (i.e. will read or write any primitive type).
    """
    type: Type['ConfigModel'] = None
    strict_keys = True

    def __post_init__(self):
        if type is None:
            raise ValueError('type must be specified')

    def convert(self, value: dict) -> 'ConfigModel':
        conv_obj = self.type()
        conv_obj.cfg_set_field(self)
        conv_obj.cfg_set_data(value)
        return conv_obj

    def serialize(self, value: 'ConfigModel') -> dict:
        return {key: value.get(key) for key in value.keys()}
