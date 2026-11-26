"""Data contracts and configuration schemas for TASK 09C monitoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

OBS_EVENT_SCHEMA_VERSION = "obs-event-v1"
SCAN_CANDIDATE_SCHEMA_VERSION = "scan-candidate-v1"
TARGET_REF_VERSION = "target-ref-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class ObservationEvent:
    """Raw normalized observation from file watcher or process monitor."""

    event_id: str
    source: str  # "file_watcher" | "process_monitor"
    event_type: str  # "FILE_CREATED" | "FILE_MODIFIED" | "FILE_RENAMED" | "PROCESS_CREATED"
    timestamp_utc: str
    target_kind: str  # "FILE" | "PROCESS"
    target_path: Optional[str] = None
    pid: Optional[int] = None
    process_start_time_epoch: Optional[float] = None
    path_status: str = "KNOWN"  # "KNOWN" | "UNKNOWN" | "OUT_OF_SCOPE"
    reason_code: str = "OBSERVED"
    uncertainty_notes: List[str] = field(default_factory=list)
    monotonic_ns: int = 0
    schema_version: str = OBS_EVENT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "source": self.source,
            "event_type": self.event_type,
            "timestamp_utc": self.timestamp_utc,
            "target_kind": self.target_kind,
            "target_path": self.target_path,
            "pid": self.pid,
            "process_start_time_epoch": self.process_start_time_epoch,
            "path_status": self.path_status,
            "reason_code": self.reason_code,
            "uncertainty": {
                "is_uncertain": self.path_status != "KNOWN" or bool(self.uncertainty_notes),
                "notes": list(self.uncertainty_notes),
            },
        }


@dataclass(frozen=True)
class ScanCandidate:
    """Candidate proposed to Node B (mock boundary). Always requires revalidation."""

    candidate_id: str
    source_event_id: str
    source: str
    created_at_utc: str
    target_kind: str
    target_ref: Dict[str, Any]
    pe_probe: Dict[str, Any]
    reason: str
    observation_sha256: Optional[str] = None  # Dedup only; NOT a trusted identity
    path_status: str = "KNOWN"
    uncertainty_notes: List[str] = field(default_factory=list)
    latency_ms: Optional[float] = None
    schema_version: str = SCAN_CANDIDATE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "source_event_id": self.source_event_id,
            "source": self.source,
            "created_at_utc": self.created_at_utc,
            "target_kind": self.target_kind,
            "target_ref": self.target_ref,
            "pe_probe": self.pe_probe,
            "observation_sha256": self.observation_sha256,
            "reason": self.reason,
            "uncertainty": {
                "path_status": self.path_status,
                "identity_trusted": False,
                "notes": list(self.uncertainty_notes) + [
                    "observation_only_revalidation_required"
                ],
            },
            "latency_ms": self.latency_ms,
        }


def build_target_ref(
    target_kind: str,
    target_path: Optional[str] = None,
    pid: Optional[int] = None,
    start_time_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a target-ref-v1 compatible observation reference.

    Follows bc_contracts.py rules: never invent unavailable identity fields,
    and always mark revalidation_required=True.
    """
    if target_kind == "PROCESS":
        has_pid = isinstance(pid, int)
        has_start = isinstance(start_time_epoch, (int, float))
        return {
            "schema_version": TARGET_REF_VERSION,
            "kind": "PROCESS",
            "observed": {
                "pid": pid,
                "start_time_epoch": start_time_epoch,
                "path": target_path,
            },
            "identity_strength": "PARTIAL" if (has_pid and has_start) else "UNAVAILABLE",
            "verified_digest": None,
            "snapshot": {},
            "revalidation_required": True,
        }

    return {
        "schema_version": TARGET_REF_VERSION,
        "kind": "FILE",
        "observed": {"path": target_path or ""},
        "identity_strength": "UNAVAILABLE",
        "verified_digest": None,
        "snapshot": {},
        "revalidation_required": True,
    }


@dataclass
class MonitorConfig:
    """Configuration for the monitoring pipeline."""

    watch_dirs: List[str] = field(default_factory=list)
    exclude_dirs: List[str] = field(default_factory=list)
    enable_file_watcher: bool = True
    enable_process_monitor: bool = False
    process_poll_interval_ms: int = 100
    debounce_ms: int = 50
    max_retries: int = 3
    retry_delay_ms: int = 40
    queue_maxsize: int = 256
    dedup_ttl_seconds: float = 2.0
    dedup_max_entries: int = 2048
    emit_unknown_process_paths: bool = True
    allow_drive_root: bool = False
    compute_observation_hash_for_dedup: bool = True


@dataclass
class MonitorMetrics:
    """Counters and performance stats for observability (no zero-loss claims)."""

    events_emitted: int = 0
    events_coalesced: int = 0
    events_deduped: int = 0
    filtered_non_pe: int = 0
    filtered_out_of_scope: int = 0
    candidates_enqueued: int = 0
    candidates_delivered: int = 0
    dropped_queue_full: int = 0
    watcher_overflows: int = 0
    retry_attempts: int = 0
    retry_exhausted: int = 0
    errors: int = 0
    queue_peak: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

