from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import AccountController
from utils.schema_handler import SchemaHandler


class AccountResource:
    def on_post_for_client(self, client_key: str) -> JSONResponse:
        controller = AccountController()
        account_response = controller.create_for_client(client_key)

        return JSONResponse(
            content=jsonable_encoder(account_response),
            status_code=http_status.HTTP_201_CREATED,
        )

    def on_get_by_key(self, account_key: str) -> JSONResponse:
        controller = AccountController()
        account_response = controller.get_by_key(account_key)

        return JSONResponse(
            content=jsonable_encoder(account_response),
            status_code=http_status.HTTP_200_OK,
        )

    @SchemaHandler.validate("patch_account.json")
    def on_patch_by_key(self, account_key: str, payload: dict) -> JSONResponse:
        controller = AccountController()
        account_response = controller.update_status(account_key, payload)

        return JSONResponse(
            content=jsonable_encoder(account_response),
            status_code=http_status.HTTP_200_OK,
        )
