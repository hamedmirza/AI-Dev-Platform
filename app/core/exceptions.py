
class AppError(Exception):
    """Base application error."""


class ConfigurationError(AppError):
    """Raised when required configuration is invalid or unavailable."""


class ProviderError(AppError):
    """Raised when model-provider interaction fails."""


class WorkflowError(AppError):
    """Raised when a run cannot advance safely."""
