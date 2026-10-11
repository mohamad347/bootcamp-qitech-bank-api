from dataclasses import dataclass


@dataclass(frozen=True)
class AccountPatchDTO:
    status: str
    reason: str

    @classmethod
    def from_payload(cls, payload: dict) -> "AccountPatchDTO":
        reason = payload["reason"].strip()
        if not reason:
            raise ValueError("reason must not be empty after trimming")
        if len(reason) > 500:
            raise ValueError("reason must have at most 500 characters after trimming")
        return cls(status=payload["status"], reason=reason)

    @staticmethod
    def to_response(account_key, status: str) -> dict:
        return {"account_key": str(account_key), "status": status}
