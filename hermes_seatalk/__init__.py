"""SeaTalk platform plugin package for Hermes Agent."""

from .adapter import register
from .probe import SeaTalkProbeResult, probe_seatalk

__all__ = ["register", "probe_seatalk", "SeaTalkProbeResult"]

