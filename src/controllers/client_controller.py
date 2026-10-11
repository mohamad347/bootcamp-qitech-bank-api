from datetime import date
from zoneinfo import ZoneInfo

from controllers.base_controller import BaseController
from models import ClientStatus, ClientStatusEvent
from repositories import ClientRepository
from utils.document_number import is_valid_cpf


MINIMUM_AGE = 18

SUPPORTED_BRAZIL_TIMEZONES = {
    "America/Noronha",
    "America/Belem",
    "America/Fortaleza",
    "America/Recife",
    "America/Araguaina",
    "America/Maceio",
    "America/Bahia",
    "America/Sao_Paulo",
    "America/Campo_Grande",
    "America/Cuiaba",
    "America/Santarem",
    "America/Porto_Velho",
    "America/Boa_Vista",
    "America/Manaus",
    "America/Eirunepe",
    "America/Rio_Branco",
}


class ClientController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.client_repository = ClientRepository(self.context)

    def create(self, client_data: dict) -> dict:
        self.logger.debug("Criando um novo Client")

        email = client_data["email"].strip().lower()
        timezone_name = client_data["timezone"]
        full_name = client_data["full_name"].strip()
        cpf = self._only_digits(client_data["cpf"])
        birth_date = date.fromisoformat(client_data["birth_date"])

        # Estas verificações ainda serão ligadas aos nossos erros CLI...
        # quando criarmos os testes específicos de falha.
        if timezone_name not in SUPPORTED_BRAZIL_TIMEZONES:
            raise ValueError("Unsupported timezone")

        if not is_valid_cpf(cpf):
            raise ValueError("Invalid CPF")

        if self._age_in_years(birth_date, timezone_name) < MINIMUM_AGE:
            raise ValueError("Underage client")

        pending_status = self.client_repository.get_status(ClientStatus.PENDING)

        client = self.client_repository.create_client(
            client_type="INDIVIDUAL",
            email=email,
            timezone_name=timezone_name,
            status=pending_status,
        )

        self.client_repository.create_individual_client(
            client=client,
            cpf=cpf,
            full_name=full_name,
            birth_date=birth_date,
        )

        self.client_repository.create_status_event(
            client=client,
            to_status=pending_status,
            actor_type=ClientStatusEvent.SYSTEM,
        )

        self.session.commit()

        return {
            "client_key": str(client.client_key),
            "client_type": client.client_type,
            "status": pending_status.enumerator,
        }

    @staticmethod
    def _only_digits(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    @staticmethod
    def _age_in_years(birth_date: date, timezone_name: str) -> int:
        from datetime import datetime

        today = datetime.now(ZoneInfo(timezone_name)).date()

        age = today.year - birth_date.year

        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        return age