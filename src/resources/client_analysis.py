from fastapi import status as http_status
from fastapi.responses import JSONResponse

from controllers import ClientAnalysisController


class ClientAnalysisResource:
    def on_post(self, client_key: str) -> JSONResponse:
        controller = ClientAnalysisController()
        analysis_response = controller.analyze(client_key)

        return JSONResponse(
            content=analysis_response,
            status_code=http_status.HTTP_200_OK,
        )
