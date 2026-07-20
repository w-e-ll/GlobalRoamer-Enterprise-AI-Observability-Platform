from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class OperationalSignalType(StrEnum):
    """Supported operational signals detected in trace content."""

    FAILURE = "failure"
    ERROR = "error"
    TIMEOUT = "timeout"
    RETRY = "retry"

    DETACH = "detach"
    ATTACH = "attach"
    REGISTRATION = "registration"
    AUTHENTICATION = "authentication"

    PAGING = "paging"
    REJECT = "reject"
    DISCONNECT = "disconnect"
    RELEASE = "release"

    SMS = "sms"
    CALL = "call"
    VOLTE = "volte"


@dataclass(frozen=True, slots=True)
class OperationalSignal:
    """
    Represent a lightweight operational keyword signal.

    A signal indicates that a raw trace row contains terminology related
    to an operational concept. It is not equivalent to classified
    evidence and does not imply that an actual failure occurred.

    For example, a line containing ``authentication successful`` may
    produce an AUTHENTICATION signal, but it should not automatically
    produce failure evidence.
    """

    signal_type: OperationalSignalType

    source_line_number: int
    source_line: str

    matched_keyword: str
    confidence: float

    timestamp: datetime | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(
            self.signal_type,
            OperationalSignalType,
        ):
            raise TypeError(
                "signal_type must be an OperationalSignalType"
            )

        if self.source_line_number <= 0:
            raise ValueError(
                "Signal source_line_number must be greater than zero"
            )

        normalized_source_line = self.source_line.strip()

        if not normalized_source_line:
            raise ValueError(
                "Signal source_line must not be empty"
            )

        normalized_keyword = self.matched_keyword.strip().casefold()

        if not normalized_keyword:
            raise ValueError(
                "Signal matched_keyword must not be empty"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Signal confidence must be between 0.0 and 1.0"
            )

        object.__setattr__(
            self,
            "source_line",
            normalized_source_line,
        )
        object.__setattr__(
            self,
            "matched_keyword",
            normalized_keyword,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        signal_type: OperationalSignalType,
        source_line_number: int,
        source_line: str,
        matched_keyword: str,
        confidence: float = 1.0,
        timestamp: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OperationalSignal:
        """Create an immutable operational signal."""

        return cls(
            signal_type=signal_type,
            source_line_number=source_line_number,
            source_line=source_line,
            matched_keyword=matched_keyword,
            confidence=confidence,
            timestamp=timestamp,
            metadata=metadata or {},
        )

    @property
    def is_problem_signal(self) -> bool:
        """
        Return whether the signal commonly represents an operational issue.

        This is only a coarse grouping. Final interpretation belongs to
        evidence classification and trace normalization.
        """

        return self.signal_type in {
            OperationalSignalType.FAILURE,
            OperationalSignalType.ERROR,
            OperationalSignalType.TIMEOUT,
            OperationalSignalType.RETRY,
            OperationalSignalType.REJECT,
            OperationalSignalType.DISCONNECT,
            OperationalSignalType.DETACH,
        }

    @property
    def is_network_lifecycle_signal(self) -> bool:
        """Return whether the signal describes network lifecycle activity."""

        return self.signal_type in {
            OperationalSignalType.ATTACH,
            OperationalSignalType.DETACH,
            OperationalSignalType.REGISTRATION,
            OperationalSignalType.AUTHENTICATION,
            OperationalSignalType.PAGING,
            OperationalSignalType.DISCONNECT,
            OperationalSignalType.RELEASE,
        }

    @property
    def is_service_signal(self) -> bool:
        """Return whether the signal identifies a telecom service."""

        return self.signal_type in {
            OperationalSignalType.SMS,
            OperationalSignalType.CALL,
            OperationalSignalType.VOLTE,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the signal."""

        return {
            "signal_type": self.signal_type.value,
            "source_line_number": self.source_line_number,
            "source_line": self.source_line,
            "matched_keyword": self.matched_keyword,
            "confidence": self.confidence,
            "timestamp": (
                self.timestamp.isoformat()
                if self.timestamp is not None
                else None
            ),
            "metadata": dict(self.metadata),
        }
