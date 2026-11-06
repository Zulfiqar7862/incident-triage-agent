"""Application-level errors mapped to HTTP by the presentation layer."""


class NotFound(Exception):
    pass


class RunStateError(Exception):
    pass


class InvalidInput(Exception):
    pass


class TooBusy(Exception):
    pass
