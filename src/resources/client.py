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

    def on_get_by_key(self, client_key: str) -> JSONResponse:
        controller = ClientController()
        client_response = controller.get_by_key(client_key)

        return JSONResponse(
            content=jsonable_encoder(client_response),
            status_code=http_status.HTTP_200_OK,
        )

    @SchemaHandler.validate("patch_client.json")
    def on_patch_by_key(self, client_key: str, payload: dict) -> JSONResponse:
        controller = ClientController()
        client_response = controller.update_status(client_key, payload)

        return JSONResponse(
            content=jsonable_encoder(client_response),
            status_code=http_status.HTTP_200_OK,
        )
