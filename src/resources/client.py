from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import ClientController
from utils.schema_handler import SchemaHandler


class ClientResource:
    @SchemaHandler.validate("post_client.json")
    def on_post(self, payload: dict) -> JSONResponse:
        controller = ClientController()
        client_response = controller.create(payload)

        return JSONResponse(
            content=jsonable_encoder(client_response),
            status_code=http_status.HTTP_201_CREATED,
        )
