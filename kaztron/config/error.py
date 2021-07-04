class ConfigError(Exception):
    def __init__(self, file, section, key, *args):
        super().__init__(file, section, key, *args)
        self.file = file
        self.section = section
        self.key = key

    def __str__(self):
        return "Error in configuration {}".format(self._get_config_info())

    def _get_config_info(self):
        s = [self.file]
        if self.section:
            s.append(self.section)
        if self.key:
            s.append(self.key)
        return ':'.join(s)


class ReadOnlyError(ConfigError):
    def __init__(self, file, *args):
        super().__init__(file, None, None, *args)

    def __str__(self):
        return "Configuration file {} is open read-only".format(self.file)


class ConfigNameError(ConfigError):
    def __str__(self):
        return "Config sections cannot start with '_' in {}".format(self._get_config_info())


class ConfigKeyError(ConfigError, AttributeError, KeyError):
    def __str__(self):
        return "Configuration key not found: {}".format(self._get_config_info())


class ConfigConverterError(ConfigError):
    """
    :deprecated: 3.0.0
    """
    def __str__(self):
        return "Error in converter for configuration: {}".format(self._get_config_info())


class ConfigValueError(ConfigError, ValueError):
    def __str__(self):
        return "Invalid configuration value: {}".format(self._get_config_info())


class ConfigTypeError(ConfigError, TypeError):
    def __str__(self):
        return "Invalid type of configuration value: {}".format(self._get_config_info())
