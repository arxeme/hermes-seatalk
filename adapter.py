"""Hermes plugin entry shim for the SeaTalk platform."""

from hermes_seatalk.adapter import (  # noqa: F401
    REQUIRED_ENV,
    SEATALK_PLATFORM,
    SEATALK_PLUGIN_NAME,
    SeaTalkAdapter,
    _is_seatalk_connected,
    _validate_seatalk_config,
    check_seatalk_requirements,
    register,
)

