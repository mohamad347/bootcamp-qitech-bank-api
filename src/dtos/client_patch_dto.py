from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ClientPatchDTO:
    status: str
    reason: str

    @classmethod
    def from_payload(cls, payload: dict) -> "ClientPatchDTO":
        reason = payload["reason"].strip()
        if not reason:
            raise ValueError("reason must not be empty after trimming")
        if len(reason) > 500:
            raise ValueError("reason must have at most 500 characters after trimming")
        return cls(status=payload["status"], reason=reason)

    @staticmethod
    def to_response(client_key: UUID, status: str) -> dict:
        return {"client_key": str(client_key), "status": status}
