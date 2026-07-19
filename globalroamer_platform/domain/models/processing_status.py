# domain/models/processing_status.py

from enum import StrEnum


class ProcessingStatus(StrEnum):
    RECEIVED = "received"
    STORED = "stored"
    PARSING = "parsing"
    PARSED = "parsed"
    NORMALIZING = "normalizing"
    NORMALIZED = "normalized"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    ANALYZING = "analyzing"
    COMPLETED = "completed"

    RETRY_PENDING = "retry_pending"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
