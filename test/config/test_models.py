import pytest
from unittest.mock import Mock
from typing import List, Dict, Type

from kaztron.config import KaztronConfig, ConfigModel, ConfigRoot, ConstrainedIntegerField, \
    IntegerField, StringField, FloatField, ListField, DictField, BooleanField, ConfigModelField,\
    Field, ConfigList, ConfigDict, \
    ConfigKeyError, ConfigConverterError, ReadOnlyError


class ConfigModelFixture:
    data: dict = None
    mock_config: Mock = None
    root: ConfigRoot = None
    object: 'DataRoot' = None
    model_data: Type[ConfigRoot] = None
    model_asdf: Type[ConfigModel] = None
    model_jkl: Type[ConfigModel] = None
    model_nest: Type[ConfigModel] = None
    model_meow: Type[ConfigModel] = None


@pytest.fixture
def model_fixture() -> ConfigModelFixture:
    f = ConfigModelFixture()
    f.mock_config = Mock(spec=KaztronConfig)
    f.mock_config.get.return_value = 'value'
    f.mock_config.filename = 'mock_file.cfg'
    f.mock_config.read_only = False
    f.data = {
        'asdf': {
            'four': 4,
            'big': 1028,
            'pi': 3.1415926535,
            'is_potato': True,
            'string': 'spaghetti',
            'not_in_fields': 'meow',
        },
        'jkl': {
            'nest': {
                'bird': 'blue jay',
                'five': 5,
                'one_meow': {'a': 1, 'b': 2},
                'meow': [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}, {'a': 5, 'b': 6}],
                'list': [0, 2, 4, 6, 8, 10],
                'dict': {'a': 32, 'b': 33, 'c': 34, 'd': 35},
                'meowmap': {'x': {'a': 1, 'b': 2}, 'y': {'a': 3, 'b': 4}, 'z': {'a': 5, 'b': 6}}
            },
            'dict_default': {
                'overwrite': 12,
                'new': 15
            },
            'enable_feature': False,
            'enable_horrors': True
        }
    }

    class Meow(ConfigModel):
        a: int = IntegerField()
        b: int = IntegerField()

    class Nest(ConfigModel):
        bird: str = StringField()
        five: int = IntegerField()
        one_meow: Meow = ConfigModelField(type=Meow)
        meow: List[Meow] = ListField(type=ConfigModelField(type=Meow))
        list: list = ListField(type=IntegerField(max=255))
        dict: dict = DictField(type=IntegerField(max=255))
        meowmap: Dict[str, Meow] = DictField(type=ConfigModelField(type=Meow))

    class Jkl(ConfigModel):
        nest: Nest = ConfigModelField(type=Nest)
        enable_feature: bool = BooleanField()
        enable_horrors: bool = BooleanField()
        dict_default: Dict[str, int] = DictField(type=IntegerField(), merge_defaults=True,
            default = {'default': -1, 'overwrite': 0})

    class Asdf(ConfigModel):
        four: int = IntegerField()
        big: int = ConstrainedIntegerField(min=0, max=255)
        pi: float = FloatField()
        is_potato: bool = BooleanField()
        string: str = StringField(default="default")
        not_in_data: str = StringField(default="default")

    class DataRoot(ConfigRoot):
        asdf: Asdf = ConfigModelField(type=Asdf)
        jkl: Jkl = ConfigModelField(type=Jkl)

    f.model_meow = Meow
    f.model_nest = Nest
    f.model_jkl = Jkl
    f.model_asdf = Asdf
    f.model_data = DataRoot

    root = f.model_data(f.mock_config)
    root.cfg_set_data(f.data)
    f.object = root
    return f


class ConfigModelAttrFixture:
    data: dict = None
    mock_config: Mock = None
    root: ConfigRoot = None
    object: 'DataRoot' = None
    model_data: Type[ConfigRoot] = None
    model_a: Type[ConfigModel] = None
    model_b: Type[ConfigModel] = None
    field: Type[Field] = None
    type: Type[object] = None


@pytest.fixture
def model_attr_fixture() -> ConfigModelAttrFixture:
    f = ConfigModelAttrFixture()
    f.mock_config = Mock(spec=KaztronConfig)
    f.mock_config.get.return_value = 'value'
    f.mock_config.filename = 'mock_file.cfg'
    f.mock_config.read_only = False
    f.data = {
        'a': {
            'b': {
                'c': 1,
                'l': [2, 3, 4],
                'd': {'a': 5, 'b': 6, 'c': 7},
            }
        }
    }

    class Potato:
        def __init__(self, x: int, t):
            self.x = x
            self.testattr_from_field = t

    class PotatoField(Field):
        def convert(self, value) -> Potato:
            return Potato(value, self.testattr)

        def serialize(self, value: Potato) -> int:
            return value.x

    class B(ConfigModel):
        c: Potato = PotatoField()
        l: List[Potato] = ListField(type=PotatoField())
        d: Dict[str, Potato] = DictField(type=PotatoField())

    class A(ConfigModel):
        b: B = ConfigModelField(type=B)

    class DataRoot(ConfigRoot):
        a: A = ConfigModelField(type=A)

    f.model_data = DataRoot
    f.model_a = A
    f.model_b = B
    f.field = PotatoField
    f.type = Potato

    root = f.model_data(f.mock_config)
    root.cfg_set_data(f.data)
    f.object = root
    return f


class TestConfigModel:
    def test_fields_processed(self):
        class Flamingo(ConfigModel):
            four: int = IntegerField()
            pi: float = FloatField()
            list: list = ListField(type=IntegerField())
        assert isinstance(Flamingo.__config_fields__['four'], IntegerField)
        assert isinstance(Flamingo.__config_fields__['pi'], FloatField)
        assert isinstance(Flamingo.__config_fields__['list'], ListField)
        assert len(Flamingo.__config_fields__) == 3

    def test_invalid_fields_not_processed(self):
        class Flamingo(ConfigModel):
            four: int = IntegerField()
            _DEFAULT_FIELD: int = IntegerField()
        assert isinstance(Flamingo._DEFAULT_FIELD, Field)  # attribute exists
        assert '_DEFAULT_FIELD' not in Flamingo.__config_fields__  # and was not processed

    def test_child_model_correct_type(self, model_fixture: ConfigModelFixture):
        # This is positioned here because some of the later tests rely on access to o.asdf
        # I know, I know, poor test design... the perils of free-time volunteer work!
        o = model_fixture.object
        child = o.asdf
        assert isinstance(child, model_fixture.model_asdf)
        assert child.__config_field__ is o.__config_fields__['asdf']

    def test_child_model_hierarchy_properties(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        child = o.asdf
        assert child.__config_parent__ is o
        assert child.__config_root__ is o

        child2 = o.jkl.nest
        assert child2.__config_parent__ is o.jkl
        assert child2.__config_root__ is o

    def test_file_property(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        for oo in (o, o.asdf, o.jkl, o.jkl.nest):
            assert oo.cfg_file == 'mock_file.cfg'

    def test_path_property(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.asdf.cfg_path == ('asdf',)
        assert o.jkl.cfg_path == ('jkl',)
        assert o.jkl.nest.cfg_path == ('jkl', 'nest')

    def test_get_field(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.cfg_get_field('asdf') is model_fixture.model_data.__config_fields__['asdf']
        assert o.asdf.cfg_get_field('is_potato') is \
               model_fixture.model_asdf.__config_fields__['is_potato']

    def test_reading_keys(self, model_fixture: ConfigModelFixture):
        defined_keys = {'four', 'big', 'pi', 'is_potato', 'string', 'not_in_data'}
        real_keys = {'four', 'big', 'pi', 'is_potato', 'string', 'not_in_fields'}
        o = model_fixture.object
        assert set(o.asdf.cfg_field_keys()) == defined_keys
        assert set(o.asdf.keys()) == real_keys

    def test_read_primitives(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.asdf.four == 4
        assert o.asdf.pi == 3.1415926535
        assert o.asdf.is_potato
        assert o.asdf.string == "spaghetti"

        # two-level nested
        assert o.jkl.nest.five == 5
        assert list(o.jkl.nest.list) == [0, 2, 4, 6, 8, 10]

    def test_traverse(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.traverse('jkl', 'nest', 'five') == 5
        assert o.traverse('jkl', 'nest') is o.jkl.nest
        with pytest.raises(ConfigKeyError):
            o.traverse('jkl', 'nest', 'doesnotexist')

    def test_read_converts_field(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.asdf.big == 255  # if properly converted, ConstrainedIntegerField limits to 255

    def test_read_key_in_data_without_field_strict(self, model_fixture: ConfigModelFixture):
        with pytest.raises(ConfigKeyError):
            model_fixture.object.asdf.not_in_fields

    def test_read_key_in_data_without_field_non_strict(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.asdf.__config_field__.strict_keys = False
        assert o.asdf.not_in_fields == 'meow'

    def test_read_key_not_in_data_returns_default(self, model_fixture: ConfigModelFixture):
        assert model_fixture.object.asdf.not_in_data == 'default'

    def test_multiple_read_uses_cached_value(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        first_list = o.jkl.nest.get('list')
        second_list = o.jkl.nest.get('list')
        assert first_list is second_list

    def test_clear_cache(self, model_fixture: ConfigModelFixture):
        # list
        o = model_fixture.object
        first_list = o.jkl.nest.get('list')
        second_list = o.jkl.nest.list
        assert first_list is second_list
        o.jkl.nest.clear_cache()
        assert first_list is not o.jkl.nest.get('list')

        # configmodel object
        asdf = o.asdf
        asdf2 = o.asdf
        assert asdf is asdf2
        o.clear_cache()
        assert asdf is not o.asdf

    def test_cfg_set_data_resets_cache(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        first_list = o.jkl.nest.get('list')
        o.jkl.nest.cfg_set_data(model_fixture.data['jkl']['nest'])
        assert first_list is not o.jkl.nest.get('list')

    def test_set_existing_key(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.asdf.four == 4
        o.asdf.four = 5
        assert o.asdf.four == 5

    def test_set_new_key_with_field(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.asdf.not_in_data == 'default'
        o.asdf.not_in_data = 'not_default'
        assert o.asdf.not_in_data == 'not_default'

    def test_set_new_key_without_field_non_strict(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.asdf.__config_field__.strict_keys = False
        o.asdf.new_key = 'hello'
        assert o.asdf.new_key == 'hello'

    def test_set_new_key_without_field_strict(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.asdf.__config_field__.strict_keys = True
        with pytest.raises(ConfigKeyError):
            o.asdf.new_key = 'hello'

    def test_set_key_read_only(self, model_fixture: ConfigModelFixture):
        model_fixture.mock_config.read_only = True
        o = model_fixture.object
        with pytest.raises(ReadOnlyError):
            o.asdf.four = 5

    def test_set_key_notifies_upward(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.asdf.four = 5
        model_fixture.mock_config.notify.assert_called_once()

    def test_string_conversions(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        # no checking of value, just that these values return correctly
        x = o.jkl.nest.meow[0]
        y = o.jkl.nest.meow
        repr(x)
        yy = o.jkl.nest.meow
        print(repr(o.jkl.nest.meow[0]))
        print(repr(o.jkl.nest.meow))
        print(repr(o.jkl.nest))
        print(repr(o.jkl))
        for p in (o, o.asdf, o.jkl, o.jkl.nest):
            print(str(p))
            print(repr(p))
            print()

    def test_equals_strict(self, model_fixture: ConfigModelFixture):
        # == with strict_keys will only check for defined keys - not_in_fields is ignored
        asdf = model_fixture.object.asdf
        asdf.__config_field__.strict_keys = True

        new_asdf = model_fixture.model_asdf(four=4, pi=3.1415926535, big=1026, is_potato=True,
            string='spaghetti')
        new_asdf.__config_field__.strict_keys = True

        assert asdf == new_asdf

    def test_equals_non_strict(self, model_fixture: ConfigModelFixture):
        asdf = model_fixture.object.asdf
        asdf.__config_field__.strict_keys = False

        new_asdf = model_fixture.model_asdf(four=4, pi=3.1415926535, big=1026, is_potato=True,
            string='spaghetti')
        new_asdf.__config_field__.strict_keys = False
        new_asdf.not_in_fields = 'meow'

        assert asdf == new_asdf

    def test_contains(self, model_fixture: ConfigModelFixture):
        assert 'four' in model_fixture.object.asdf  # defined as field AND in data
        assert 'not_in_fields' in model_fixture.object.asdf  # not defined but is in data
        assert 'asdf' not in model_fixture.object.asdf  # not in data, not defined

    def test_non_lazy_cfg_set_data_deep_converts(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.__config_field__.lazy = False
        # let's spot test a couple different keys within the hierarchy
        model_fixture.model_data.cfg_get_field('asdf').lazy = False
        model_fixture.model_data.cfg_get_field('asdf').strict_keys = False
        model_fixture.model_data.cfg_get_field('jkl').lazy = False
        model_fixture.model_jkl.cfg_get_field('nest').lazy = False
        model_fixture.model_nest.cfg_get_field('meow').lazy = False
        model_fixture.model_nest.cfg_get_field('meow').type.lazy = False

        model_fixture.model_nest.cfg_get_field('bird').convert = mock_a = Mock(return_value='blue jay')
        model_fixture.model_asdf.cfg_get_field('pi').convert = mock_b = Mock(return_value=3.1415926535)
        model_fixture.model_meow.cfg_get_field('b').convert = mock_c = Mock(return_value=4)
        o.cfg_set_data(model_fixture.data)
        mock_a.assert_called_once()
        mock_b.assert_called_once()
        assert mock_c.call_count == 3

    def test_list_child_has_field(self, model_fixture: ConfigModelFixture):  # regression test
        o = model_fixture.object
        assert o.jkl.nest.meow[1].__config_field__.type is model_fixture.model_meow

    def test_dict_child_has_field(self, model_fixture: ConfigModelFixture):  # regression test
        o = model_fixture.object
        assert o.jkl.nest.meowmap['y'].__config_field__.type is model_fixture.model_meow

    def test_runtime_attribute_propagation(self, model_attr_fixture: ConfigModelAttrFixture):
        testattr = object()
        o = model_attr_fixture.object
        o.cfg_set_runtime_attributes(model_attr_fixture.field, testattr=testattr)
        o.clear_cache()
        for oo in o, o.a, o.a.b:
            assert oo.cfg_get_runtime_attributes(model_attr_fixture.field)['testattr'] is testattr
        _ = o.a.b.c
        assert o.a.b.cfg_get_field('c').testattr is testattr

    # TODO: check parent/root with non-lazy eval


class TestConfigRoot:
    def test_properties_hierarchy(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.__config_parent__ is None
        assert o is o.__config_root__

    def test_set_parent_raises(self, model_fixture: ConfigModelFixture):
        with pytest.raises(Exception):
            model_fixture.object.cfg_set_parent(None)

    def test_add_new_model_to_tree(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object

        class Wan(ConfigModel):
            x: int = IntegerField()
            x_name: str = StringField()

        # register the model
        o.cfg_register_model('wan', Wan)
        assert isinstance(o.cfg_get_field('wan'), ConfigModelField)
        assert o.cfg_get_field('wan').type is Wan

        # and attempt to add a new object
        wan = Wan(x=4, x_name='blue')
        o.wan = wan
        model_fixture.mock_config.notify.assert_called_once()
        assert o.wan.x == 4
        assert o.wan.x_name == 'blue'

    def test_properties(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        assert o.cfg_file == 'mock_file.cfg'
        assert o.cfg_path == tuple()

        assert o.cfg_read_only is False
        model_fixture.mock_config.read_only = True
        assert o.cfg_read_only is True

    def test_notify(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.cfg_notify_update()
        model_fixture.mock_config.notify.assert_called_once()

    def test_write(self, model_fixture: ConfigModelFixture):
        o = model_fixture.object
        o.cfg_write()
        model_fixture.mock_config.write.assert_called_once()


class TestConfigList:
    def test_hierarchy_properties(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        assert isinstance(l.__config_field__.type, IntegerField)
        assert l.__config_root__ is model_fixture.object
        assert l.__config_parent__ is model_fixture.object.jkl.nest
        assert l.cfg_path == ('jkl', 'nest', 'list')
        assert l.cfg_file == 'mock_file.cfg'
        assert l.cfg_read_only is False

    def test_read(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        assert len(l) == 6
        assert l[0] == 0
        assert l[1] == 2
        assert l[-1] == l[5] == 10
        assert l[0:2] == [0, 2]

    def test_read_applies_type_convert(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        l.__config_field__.type.convert = Mock(return_value=255)
        l[0]
        l[1]
        assert l.__config_field__.type.convert.call_count == 2

    def test_caching_returns_same_objects(self):
        class F(ConfigModel):
            a: int = IntegerField()
        l = ConfigList(field=ListField(type=ConfigModelField(type=F)))
        l.cfg_set_data([{'a': 1}, {'a': 2}])
        a0 = l[0]
        assert a0 is l[0]
        l.clear_cache()
        assert a0 is not l[0]
        assert l[0].a == 1

    def test_write(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        l[0] = -2
        l.append(12)
        l.insert(1, 0)
        del l[6]
        assert l[0] == -2
        assert l[1] == 0
        assert l[5] == 8
        assert l[-1] == l[6] == 12
        assert model_fixture.mock_config.notify.called

    def test_write_applies_type_serialize(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        l.__config_field__.type.serialize = Mock(return_value=255)
        l[0] = 125
        l.append(128)
        l.insert(1, 255)
        assert l.__config_field__.type.serialize.call_count == 3

    def test_equals_to_list(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        assert l == [0, 2, 4, 6, 8, 10]

    def test_constructor_initialisation(self):
        l1 = ConfigList([0, 2, 4, 8, 16], field=ListField(type=IntegerField(max=255)))
        assert l1 == [0, 2, 4, 8, 16]

    def test_constructor_initialisation_non_lazy(self):
        with pytest.raises(ValueError):  # tests that conversion is happening in non-lazy
            ConfigList([0, 128, 256], field=ListField(type=IntegerField(max=255), lazy=False))

    def test_equals_to_config_list(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.list
        assert l == ConfigList([0, 2, 4, 6, 8, 10],
                               field=ListField(name='Unassigned', type=IntegerField()))

    def test_config_model_child_properties(self, model_fixture: ConfigModelFixture):
        l: ConfigList = model_fixture.object.jkl.nest.meow
        assert l.__config_field__.type.type is model_fixture.model_meow
        el = l[1]
        assert isinstance(el, model_fixture.model_meow)
        assert el.__config_root__ is model_fixture.object
        assert el.__config_parent__ is l
        assert el.cfg_path == ('jkl', 'nest', 'meow', 1)
        assert el.cfg_file == 'mock_file.cfg'

    def test_runtime_attribute_propagation(self, model_attr_fixture: ConfigModelAttrFixture):
        testattr = object()
        o = model_attr_fixture.object
        o.cfg_set_runtime_attributes(model_attr_fixture.field, testattr=testattr)
        o.clear_cache()
        assert o.a.b.l.cfg_get_runtime_attributes(model_attr_fixture.field)['testattr'] is testattr
        assert o.a.b.l[1].testattr_from_field is testattr


class TestConfigDict:
    def test_hierarchy_properties(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        assert isinstance(d.__config_field__.type, IntegerField)
        assert d.__config_root__ is model_fixture.object
        assert d.__config_parent__ is model_fixture.object.jkl.nest
        assert d.cfg_path == ('jkl', 'nest', 'dict')
        assert d.cfg_file == 'mock_file.cfg'
        assert d.cfg_read_only is False

    def test_read(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        assert len(d) == 4
        assert d['a'] == 32
        assert d.get('b') == 33
        assert d['c'] == 34
        assert d['d'] == 35

    def test_read_applies_type_convert(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        d.__config_field__.type.convert = Mock(return_value=255)
        d['a']
        d['b']
        assert d.__config_field__.type.convert.call_count == 2

    def test_iteration(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        i = 32
        for key in d.keys():
            assert d[key] == i
            i += 1

        # extract the ConfigDict into a primitive dict - test items()
        dd = {}
        for key, value in d.items():
            dd[key] = value
        assert dd == {'a': 32, 'b': 33, 'c': 34, 'd': 35}

    def test_caching_returns_same_objects(self):
        class F(ConfigModel):
            a: int = IntegerField()
        d = ConfigDict(field=DictField(type=ConfigModelField(type=F)))
        d.cfg_set_data({'x': {'a': 1}, 'y': {'a': 2}})
        a0 = d['x']
        assert a0 is d['x']
        d.clear_cache()
        assert a0 is not d['x']
        assert d['x'].a == 1

    def test_write(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        d['a'] = 16
        d.pop('d')
        assert len(d) == 3
        assert d['a'] == 16
        assert model_fixture.mock_config.notify.called

    def test_write_applies_type_serialize(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        d.__config_field__.type.serialize = Mock(return_value=255)
        d['a'] = 125
        d['e'] = 127
        assert d.__config_field__.type.serialize.call_count == 2

    def test_equals_to_list(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        assert d == {'a': 32, 'b': 33, 'c': 34, 'd': 35}

    def test_constructor_initialisation(self):
        d1 = ConfigDict({'a': 64, 'b': 128, 'c': 192}, field=DictField(type=IntegerField(max=255)))
        assert d1 == {'a': 64, 'b': 128, 'c': 192}

    def test_constructor_initialisation_non_lazy(self):
        with pytest.raises(ValueError):  # tests that conversion is happening in non-lazy
            ConfigList({'x': 128, 'y': 256}, field=DictField(type=IntegerField(max=255), lazy=False))

    def test_equals_to_config_dict(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.dict
        assert d == ConfigDict({'a': 32, 'b': 33, 'c': 34, 'd': 35},
            field=DictField(name='Unassigned', type=IntegerField()))

    def test_config_model_child_properties(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.nest.meowmap
        assert d.__config_field__.type.type is model_fixture.model_meow
        el: Meow = d['x']
        assert isinstance(el, model_fixture.model_meow)
        assert el.__config_root__ is model_fixture.object
        assert el.__config_parent__ is d
        assert el.cfg_path == ('jkl', 'nest', 'meowmap', 'x')
        assert el.cfg_file == 'mock_file.cfg'

    def test_merged_defaults(self, model_fixture: ConfigModelFixture):
        d: ConfigDict = model_fixture.object.jkl.dict_default
        assert d['default'] == -1
        assert d['new'] == 15
        assert d['overwrite'] == 12
        assert len(d) == 3
        assert set(iter(d)) == {'default', 'new', 'overwrite'}

    def test_runtime_attribute_propagation(self, model_attr_fixture: ConfigModelAttrFixture):
        testattr = object()
        o = model_attr_fixture.object
        o.cfg_set_runtime_attributes(model_attr_fixture.field, testattr=testattr)
        o.clear_cache()
        assert o.a.b.d.cfg_get_runtime_attributes(model_attr_fixture.field)['testattr'] is testattr
        assert o.a.b.d['b'].testattr_from_field is testattr
