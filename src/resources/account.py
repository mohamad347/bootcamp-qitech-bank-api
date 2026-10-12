from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import AccountController


class AccountResource:
    def on_post_for_client(self, client_key: str) -> JSONResponse:
        controller = AccountController()
        account_response = controller.create_for_client(client_key)

        return JSONResponse(
            content=jsonable_encoder(account_response),
            status_code=http_status.HTTP_201_CREATED,
        )
