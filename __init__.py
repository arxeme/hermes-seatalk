try:
    from .hermes_seatalk.adapter import register
except ImportError:  # pragma: no cover - direct local import fallback.
    from hermes_seatalk.adapter import register

__all__ = ["register"]
