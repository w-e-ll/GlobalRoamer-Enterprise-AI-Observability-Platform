#!/usr/bin/env python3
# -*- coding: utf-8 -*-


class GlobalRoamerAIException(Exception):
    pass


class ConfigError(GlobalRoamerAIException):
    pass


class TraceLoaderError(GlobalRoamerAIException):
    pass


class TraceParserError(GlobalRoamerAIException):
    pass


class ResultLogParserError(GlobalRoamerAIException):
    pass


class ExcelReportParserError(GlobalRoamerAIException):
    pass


class EvidenceExtractionError(GlobalRoamerAIException):
    pass


class EventClassificationError(GlobalRoamerAIException):
    pass


class IncidentSignatureError(GlobalRoamerAIException):
    pass


class TraceNormalizationError(GlobalRoamerAIException):
    pass


class TraceChunkingError(GlobalRoamerAIException):
    pass


class EmbeddingGenerationError(GlobalRoamerAIException):
    pass


class VectorStoreError(GlobalRoamerAIException):
    pass


class SimilaritySearchError(GlobalRoamerAIException):
    pass


class AISummaryError(GlobalRoamerAIException):
    pass


class RootCauseAnalysisError(GlobalRoamerAIException):
    pass


class RetryAdvisorError(GlobalRoamerAIException):
    pass


class CampaignHealthError(GlobalRoamerAIException):
    pass


class WorkflowGraphError(GlobalRoamerAIException):
    pass


class TelecomTaxonomyError(GlobalRoamerAIException):
    pass


class ReportGenerationError(GlobalRoamerAIException):
    pass