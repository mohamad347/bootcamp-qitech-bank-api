import json
from pathlib import Path

from utils.document_number import is_valid_cpf


INITIALIZATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "mockserver"
    / "analysis-provider-initialization.json"
)
REJECT_DOCUMENT = "16899535009"


def _response_body(expectation: dict) -> dict:
    return json.loads(expectation["httpResponse"]["body"])


def test_manual_analysis_provider_has_deterministic_approve_and_reject() -> None:
    expectations = json.loads(INITIALIZATION_FILE.read_text(encoding="utf-8"))

    reject = next(item for item in expectations if item["id"] == "manual-reject")
    approve = next(item for item in expectations if item["id"] == "manual-approve")

    assert is_valid_cpf(REJECT_DOCUMENT)
    assert reject["priority"] > approve["priority"]
    assert reject["httpRequest"] == {
        "method": "POST",
        "path": "/v1/client-analysis",
        "body": {
            "type": "JSON",
            "json": {"document": REJECT_DOCUMENT},
            "matchType": "ONLY_MATCHING_FIELDS",
        },
    }
    assert _response_body(reject) == {
        "decision": "REJECT",
        "reason": "Dados cadastrais não atendem aos critérios da análise.",
    }
    assert approve["httpRequest"] == {
        "method": "POST",
        "path": "/v1/client-analysis",
    }
    assert _response_body(approve) == {"decision": "APPROVE", "reason": None}
