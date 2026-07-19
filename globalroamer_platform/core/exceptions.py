class GlobalRoamerPlatformError(Exception):
    """Base exception for all expected platform errors."""


class ConfigurationError(GlobalRoamerPlatformError):
    """Raised when platform configuration is invalid."""


class ApplicationError(GlobalRoamerPlatformError):
    """Base exception for application use-case failures."""


class TraceAlreadyExistsError(ApplicationError):
    ...


class TraceNotFoundError(ApplicationError):
    ...


class ProcessingError(GlobalRoamerPlatformError):
    """Base exception for trace-processing failures."""

    def __init__(
        self,
        message: str,
        *,
        trace_id: str | None = None,
        stage: str | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.stage = stage
        super().__init__(message)


class TraceLoaderError(ProcessingError):
    pass


class TraceParserError(ProcessingError):
    pass


class TraceNormalizationError(ProcessingError):
    pass


class TraceChunkingError(ProcessingError):
    pass


class EmbeddingGenerationError(ProcessingError):
    pass


class VectorStoreError(ProcessingError):
    pass


class SimilaritySearchError(ProcessingError):
    pass


class AISummaryError(ProcessingError):
    pass


class RootCauseAnalysisError(ProcessingError):
    pass


class RetryAdvisorError(ProcessingError):
    pass


class CampaignHealthError(ProcessingError):
    pass


class ReportGenerationError(ProcessingError):
    pass
