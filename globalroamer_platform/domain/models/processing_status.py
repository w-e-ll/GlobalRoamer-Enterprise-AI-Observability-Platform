from enum import StrEnum


class ProcessingStatus(StrEnum):
    """Lifecycle status of a trace processed by the platform."""

    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"