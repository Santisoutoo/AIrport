"""Typed errors raised by the taxi router.

Kept separate so the plugin side can import them without pulling in the
rest of the router (which depends on redis/networkx/etc.).
"""


class TaxiRouterError(Exception):
    """Base class for router-level failures."""


class UnknownTaxiwayError(TaxiRouterError):
    """A token from the pilot readback could not be resolved to a graph node."""

    def __init__(self, token: str):
        super().__init__(f"Unknown taxiway/point: {token!r}")
        self.token = token


class RouteNotFoundError(TaxiRouterError):
    """Graph search could not connect the requested via-point sequence."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class InvalidPushbackError(TaxiRouterError):
    """The clearance's pushback direction could not be parsed."""
