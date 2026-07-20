from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from globalroamer_platform.domain.models.operational_signal import (
    OperationalSignal,
    OperationalSignalType,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)


@dataclass(frozen=True, slots=True)
class SignalRule:
    """
    Define one lightweight operational-signal detection rule.

    Unlike evidence rules, signal rules are not exclusive. A single trace
    row may match multiple operational concepts.
    """

    signal_type: OperationalSignalType
    keywords: tuple[str, ...]
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(
            self.signal_type,
            OperationalSignalType,
        ):
            raise TypeError(
                "signal_type must be an OperationalSignalType"
            )

        normalized_keywords = tuple(
            keyword.strip().casefold()
            for keyword in self.keywords
            if keyword and keyword.strip()
        )

        if not normalized_keywords:
            raise ValueError(
                "Signal rule must contain at least one keyword"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Signal rule confidence must be between 0.0 and 1.0"
            )

        object.__setattr__(
            self,
            "keywords",
            normalized_keywords,
        )

    def find_keyword(
        self,
        normalized_content: str,
    ) -> str | None:
        """Return the first configured keyword found in the content."""

        for keyword in self.keywords:
            if keyword in normalized_content:
                return keyword

        return None


DEFAULT_SIGNAL_RULES: Final[tuple[SignalRule, ...]] = (
    SignalRule(
        signal_type=OperationalSignalType.FAILURE,
        keywords=(
            "failed",
            "failure",
            "fail",
        ),
        confidence=0.85,
    ),
    SignalRule(
        signal_type=OperationalSignalType.ERROR,
        keywords=(
            "exception",
            "error",
        ),
        confidence=0.90,
    ),
    SignalRule(
        signal_type=OperationalSignalType.TIMEOUT,
        keywords=(
            "timed out",
            "timeout",
        ),
        confidence=0.90,
    ),
    SignalRule(
        signal_type=OperationalSignalType.RETRY,
        keywords=(
            "retransmission",
            "retransmit",
            "retried",
            "retry",
        ),
        confidence=0.85,
    ),
    SignalRule(
        signal_type=OperationalSignalType.DETACH,
        keywords=(
            "psattachstate detached",
            "ps detached",
            "psdetached",
            "detached",
            "detach",
        ),
        confidence=0.80,
    ),
    SignalRule(
        signal_type=OperationalSignalType.ATTACH,
        keywords=(
            "psattachstate attached",
            "ps attached",
            "psattached",
            "attached",
            "attach",
        ),
        confidence=0.80,
    ),
    SignalRule(
        signal_type=OperationalSignalType.REGISTRATION,
        keywords=(
            "registrationstate",
            "registration",
            "registered",
            "register",
        ),
        confidence=0.80,
    ),
    SignalRule(
        signal_type=OperationalSignalType.AUTHENTICATION,
        keywords=(
            "authentication",
            "authenticate",
            "authorization",
            "authorisation",
            "auth",
        ),
        confidence=0.75,
    ),
    SignalRule(
        signal_type=OperationalSignalType.PAGING,
        keywords=(
            "paging",
            "page request",
        ),
        confidence=0.85,
    ),
    SignalRule(
        signal_type=OperationalSignalType.REJECT,
        keywords=(
            "rejected",
            "reject",
            "denied",
        ),
        confidence=0.85,
    ),
    SignalRule(
        signal_type=OperationalSignalType.DISCONNECT,
        keywords=(
            "disconnected",
            "disconnect",
        ),
        confidence=0.85,
    ),
    SignalRule(
        signal_type=OperationalSignalType.RELEASE,
        keywords=(
            "released",
            "release",
        ),
        confidence=0.80,
    ),
    SignalRule(
        signal_type=OperationalSignalType.SMS,
        keywords=(
            "short message service",
            "sms",
        ),
        confidence=0.90,
    ),
    SignalRule(
        signal_type=OperationalSignalType.CALL,
        keywords=(
            "voice call",
            "call",
            "voice",
        ),
        confidence=0.75,
    ),
    SignalRule(
        signal_type=OperationalSignalType.VOLTE,
        keywords=(
            "voice over lte",
            "volte",
            "ims",
        ),
        confidence=0.85,
    ),
)


class SignalExtractor:
    """
    Extract lightweight operational signals from raw trace rows.

    Signal extraction is intentionally broad and non-exclusive. It
    identifies terminology that may be relevant to later correlation,
    retrieval, analytics, or normalization.

    It does not classify root causes or assign operational severity.
    """

    def __init__(
        self,
        *,
        rules: tuple[SignalRule, ...] | None = None,
    ) -> None:
        configured_rules = (
            rules
            if rules is not None
            else DEFAULT_SIGNAL_RULES
        )

        if not configured_rules:
            raise ValueError(
                "SignalExtractor requires at least one signal rule"
            )

        signal_types = [
            rule.signal_type
            for rule in configured_rules
        ]

        if len(signal_types) != len(set(signal_types)):
            raise ValueError(
                "SignalExtractor rules must contain no duplicate "
                "signal types"
            )

        self._rules = tuple(configured_rules)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def supported_signal_types(
        self,
    ) -> tuple[OperationalSignalType, ...]:
        return tuple(
            rule.signal_type
            for rule in self._rules
        )

    def extract(
        self,
        trace: RawTrace,
    ) -> tuple[OperationalSignal, ...]:
        """Extract all operational signals from all trace rows."""

        signals: list[OperationalSignal] = []

        for row in trace.rows:
            signals.extend(
                self.extract_from_row(row)
            )

        return tuple(signals)

    def extract_from_row(
        self,
        row: RawTraceRow,
    ) -> tuple[OperationalSignal, ...]:
        """
        Extract every distinct configured signal type from one row.

        A rule produces at most one signal for a row, even when several
        keywords belonging to the same rule occur.
        """

        searchable_content = self._build_searchable_content(
            row
        )

        if not searchable_content:
            return ()

        normalized_content = self._normalize_for_matching(
            searchable_content
        )

        signals: list[OperationalSignal] = []

        for rule in self._rules:
            matched_keyword = rule.find_keyword(
                normalized_content
            )

            if matched_keyword is None:
                continue

            signals.append(
                OperationalSignal.create(
                    signal_type=rule.signal_type,
                    source_line_number=row.line_number,
                    source_line=row.source_line,
                    matched_keyword=matched_keyword,
                    confidence=rule.confidence,
                    timestamp=row.timestamp,
                    metadata={
                        "event": row.event,
                        "event_type": row.event_type,
                        "call_id": row.call_id,
                        "ptc": row.ptc,
                    },
                )
            )

        return tuple(signals)

    @staticmethod
    def _build_searchable_content(
        row: RawTraceRow,
    ) -> str:
        """
        Build the text inspected by signal rules.

        Information is the primary source, while Event and Type are
        included because some traces place useful operational terms in
        those columns rather than Information.
        """

        values = (
            row.information,
            row.event,
            row.event_type,
        )

        return " ".join(
            value
            for value in values
            if value and value.strip()
        )

    @staticmethod
    def _normalize_for_matching(
        content: str,
    ) -> str:
        """Case-fold content and collapse repeated whitespace."""

        return " ".join(
            content.casefold().split()
        )
