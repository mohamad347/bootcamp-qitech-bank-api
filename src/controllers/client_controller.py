from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from errors import (
    DuplicateClientCPF,
    DuplicateClientCNPJ,
    DuplicateClientEmail,
    InvalidClientDocument,
    InvalidSchema,
    UnderageClient,
    UnsupportedClientTimezone,
)
from models import ClientStatus, ClientStatusEvent
from repositories import ClientRepository
from utils.document_number import is_valid_cnpj, is_valid_cpf


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

        client_type = client_data["client_type"]
        email = client_data["email"].strip().lower()
        timezone_name = client_data["timezone"]

        if client_type == "INDIVIDUAL":
            full_name = client_data["full_name"].strip()
            if not full_name:
                raise InvalidSchema("full_name must not be empty after trimming")

            cpf = self._only_digits(client_data["cpf"])
            try:
                birth_date = date.fromisoformat(client_data["birth_date"])
            except ValueError:
                raise InvalidSchema(
                    "birth_date must be a valid calendar date"
                ) from None

        if timezone_name not in SUPPORTED_BRAZIL_TIMEZONES:
            raise UnsupportedClientTimezone()

        if client_type == "INDIVIDUAL":
            if not is_valid_cpf(cpf):
                raise InvalidClientDocument("CPF")

            age = self._age_in_years(birth_date, timezone_name)
            if age < MINIMUM_AGE:
                raise UnderageClient(age, MINIMUM_AGE)
        else:
            cnpj = self._only_digits(client_data["cnpj"])
            if not is_valid_cnpj(cnpj):
                raise InvalidClientDocument("CNPJ")
            legal_name = client_data["legal_name"].strip()
            if not legal_name:
                raise InvalidSchema("legal_name must not be empty after trimming")
            trade_name = (client_data.get("trade_name") or "").strip() or None

        pending_status = self.client_repository.get_status(ClientStatus.PENDING)

        try:
            client = self.client_repository.create_client(
                client_type=client_type,
                email=email,
                timezone_name=timezone_name,
                status=pending_status,
            )

            if client_type == "INDIVIDUAL":
                self.client_repository.create_individual_client(
                    client=client,
                    cpf=cpf,
                    full_name=full_name,
                    birth_date=birth_date,
                )
            else:
                self.client_repository.create_company_client(
                    client=client,
                    cnpj=cnpj,
                    legal_name=legal_name,
                    trade_name=trade_name,
                )

            self.client_repository.create_status_event(
                client=client,
                to_status=pending_status,
                actor_type=ClientStatusEvent.SYSTEM,
            )

            # Captura os dados antes do commit, que expira os atributos ORM.
            response_data = {
                "client_key": str(client.client_key),
                "client_type": client.client_type,
                "status": pending_status.enumerator,
            }

            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if isinstance(error.orig, UniqueViolation):
                constraint_name = error.orig.diag.constraint_name
                if constraint_name == "client_email_key":
                    raise DuplicateClientEmail(email) from error
                if constraint_name == "individual_client_cpf_key":
                    raise DuplicateClientCPF() from error
                if constraint_name == "company_client_cnpj_key":
                    raise DuplicateClientCNPJ() from error
            raise

        return response_data

    def get_by_key(self, client_key: str) -> dict:
        self.logger.debug(f"Buscando o Client de chave {client_key}")

        client = self.client_repository.get_by_key(client_key)
        if client is None:
            raise RuntimeError(f"Client {client_key} was not found")

        response_data = {
            "client_key": str(client.client_key),
            "client_type": client.client_type,
            "email": client.email,
            "timezone": client.timezone,
            "status": client.status.enumerator,
            "created_at": self._as_utc_isoformat(client.created_at),
            "updated_at": self._as_utc_isoformat(client.updated_at),
        }

        if client.client_type == "INDIVIDUAL":
            individual_client = self.client_repository.get_individual_by_client_id(
                client.id
            )
            if individual_client is None:
                raise RuntimeError(
                    f"Individual profile for Client {client_key} was not found"
                )

            response_data.update(
                {
                    "cpf": individual_client.cpf,
                    "full_name": individual_client.full_name,
                    "birth_date": individual_client.birth_date.isoformat(),
                }
            )
        elif client.client_type == "COMPANY":
            company_client = self.client_repository.get_company_by_client_id(
                client.id
            )
            if company_client is None:
                raise RuntimeError(
                    f"Company profile for Client {client_key} was not found"
                )

            response_data.update(
                {
                    "cnpj": company_client.cnpj,
                    "legal_name": company_client.legal_name,
                    "trade_name": company_client.trade_name,
                }
            )
        else:
            raise RuntimeError(
                f"Unsupported client type {client.client_type} for Client {client_key}"
            )

        return response_data

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _only_digits(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    @staticmethod
    def _age_in_years(birth_date: date, timezone_name: str) -> int:
        today = datetime.now(ZoneInfo(timezone_name)).date()

        age = today.year - birth_date.year

        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        return age
