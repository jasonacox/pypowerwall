class PyPowerwallInvalidConfigurationParameter(Exception):
    pass


class InvalidBatteryReserveLevelException(Exception):
    """Reserved for future use.

    Exported as part of the public API but not currently raised anywhere in
    the library - invalid reserve levels are logged and rejected via return
    values instead. Kept (not removed) because downstream code may already
    import or catch it.
    """
    pass
