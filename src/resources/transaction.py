from fastapi import Request, status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import TransactionController
from errors import InvalidSchema
from utils.schema_handler import SchemaHandler


DEFAULT_STATEMENT_PAGE = 1
DEFAULT_STATEMENT_LIMIT = 20
DEFAULT_STATEMENT_ORDER = "desc"
STATEMENT_QUERY_PARAMS = (
    "page",
    "limit",
    "order_by",
    "date_from",
    "date_to",
)


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

    @SchemaHandler.validate_query_params("get_account_transactions.json")
    def on_get_list(
        self,
        account_key: str,
        request: Request,
    ) -> JSONResponse:
        query_params = request.query_params
        for param_name in STATEMENT_QUERY_PARAMS:
            if len(query_params.getlist(param_name)) > 1:
                raise InvalidSchema(
                    f"Query parameter '{param_name}' must not be repeated"
                )

        page = int(query_params.get("page", DEFAULT_STATEMENT_PAGE))
        limit = int(query_params.get("limit", DEFAULT_STATEMENT_LIMIT))
        order_by = query_params.get("order_by", DEFAULT_STATEMENT_ORDER)

        controller = TransactionController()
        statement_page = controller.get_statement(
            account_key=account_key,
            page=page,
            limit=limit,
            order_by=order_by,
        )
        response = {
            "data": statement_page["data"],
            "pagination": {
                "current_page": page,
                "next_page": statement_page["next_page"],
                "rows_per_page": limit,
            },
        }

        return JSONResponse(
            content=jsonable_encoder(response),
            status_code=http_status.HTTP_200_OK,
        )
