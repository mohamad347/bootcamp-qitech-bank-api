from fastapi import Request, status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import TransactionController
from utils.schema_handler import SchemaHandler


class TransactionResource:
    @SchemaHandler.validate("post_transaction.json")
    def on_post(
        self,
        account_key: str,
        request: Request,
        payload: dict,
    ) -> JSONResponse:
        controller = TransactionController()
        transaction_response = controller.create(
            account_key=account_key,
            idempotency_key=request.headers.get("Idempotency-Key"),
            transaction_data=payload,
        )

        return JSONResponse(
            content=jsonable_encoder(transaction_response),
            status_code=http_status.HTTP_201_CREATED,
        )
