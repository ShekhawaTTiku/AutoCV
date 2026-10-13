"""Domain exception hierarchy for AutoCV."""
from src.constants import MAX_LOG


class ProjectError(ValueError):
    """Raised for invalid file uploads, project structures, or path traversal."""
    pass


class EditError(ValueError):
    """Raised when a section edit or repair patch violates safety or schema constraints."""
    pass


class CompileError(RuntimeError):
    """Raised when LaTeX compilation times out or fails."""
    def __init__(self, message: str, log: str = "", repairable: bool = True):
        super().__init__(message)
        self.log = log[:MAX_LOG]
        self.repairable = repairable


class OperationCancelled(Exception):
    """Raised when a running AI or compilation job is cancelled by the user."""
    pass


class UsageError(ValueError):
    """Raised when token limits or session request quotas are exceeded."""
    pass


class ProviderError(RuntimeError):
    """Recoverable provider, network, or structured response failure."""
    pass


def check_cancel(cancel_event=None):
    """Raise OperationCancelled if the cancel event is set."""
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("Request cancelled. Your approved source is unchanged.")
