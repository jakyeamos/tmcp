"""Receipt recording orchestration over explicit adapter capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ReceiptPath = Path
ReceiptBuilder = Callable[[Mapping[str, Any], str], dict[str, Any]]
ReceiptRedactor = Callable[
    [Mapping[str, Any]], tuple[dict[str, Any], Mapping[str, int]]
]
StorageKeyBuilder = Callable[[str, str], str]
ReceiptPathBuilder = Callable[[str, str, Mapping[str, Any]], ReceiptPath]
ReceiptWriter = Callable[[ReceiptPath, Mapping[str, Any]], ReceiptPath]
PathPresenter = Callable[[ReceiptPath], str]
RecordedResultBuilder = Callable[
    [Mapping[str, Any], str, Mapping[str, int]], dict[str, Any]
]
ResultRedactor = Callable[[dict[str, Any]], dict[str, Any]]
NowIso = Callable[[], str]


@dataclass(frozen=True)
class ReceiptServiceContext:
    """Adapter-owned capabilities needed to record one receipt."""

    build_receipt: ReceiptBuilder
    redact_receipt: ReceiptRedactor
    storage_key: StorageKeyBuilder
    build_path: ReceiptPathBuilder
    write_receipt: ReceiptWriter
    present_path: PathPresenter
    build_result: RecordedResultBuilder
    redact_result: ResultRedactor
    now_iso: NowIso


class ReceiptService:
    """Coordinate receipt creation without owning redaction or persistence policy."""

    def __init__(self, context: ReceiptServiceContext) -> None:
        self._context = context

    def record(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Build, redact, persist, and present one receipt."""

        created_at = self._context.now_iso()
        receipt = self._context.build_receipt(arguments, created_at)
        safe_receipt, redactions = self._context.redact_receipt(receipt)
        packet_id = str(receipt["packet_id"])
        safe_packet_id = str(safe_receipt["packet_id"])
        storage_key = self._context.storage_key(packet_id, safe_packet_id)
        path = self._context.build_path(created_at, storage_key, safe_receipt)
        receipt_path = self._context.write_receipt(path, safe_receipt)
        result = self._context.build_result(
            safe_receipt,
            self._context.present_path(receipt_path),
            redactions,
        )
        return self._context.redact_result(result)
