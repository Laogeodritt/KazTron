from kaztron.config import KaztronConfig, TomlReadOnlyStrategy, JsonFileStrategy

_kaztron_config = None
_runtime_config = None


def get_kaztron_config(defaults=None) -> KaztronConfig:
    """
    Get the static configuration object for the bot. Constructs the object if needed.
    """
    global _kaztron_config
    if not _kaztron_config:
        try:
            _kaztron_config = KaztronConfig("config.toml", file_strategy=TomlReadOnlyStrategy,
                                            defaults=defaults, read_only=True)
        except FileNotFoundError as e:
            # legacy config.json file
            _kaztron_config = KaztronConfig("config.json", file_strategy=JsonFileStrategy,
                                            defaults=defaults, read_only=True)
    return _kaztron_config


def get_runtime_config() -> KaztronConfig:
    """
    Get the dynamic (state-persisting) configuration object for the bot. Constructs the object if
    needed.
    """
    global _runtime_config
    if not _runtime_config:
        _runtime_config = KaztronConfig("state.json", file_strategy=JsonFileStrategy)
    return _runtime_config
