import sys
from os import environ, path
from pathlib import Path

root = Path(__file__).resolve().parents[1]

if not environ.get("APP_ENV") or environ.get("APP_ENV") == "local":
    from dotenv import load_dotenv

    load_dotenv(path.join(str(root), ".env"))


# A coleta também importa módulos puros sob ``src/``. Definir o caminho e as
# configurações mínimas aqui evita depender da ordem em que outros testes
# importam a aplicação. Esses valores são defaults de desenvolvimento; nunca
# sobrescrevem variáveis fornecidas pelo ambiente de execução.
src_root = root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

for name, value in {
    "DATABASE_URL": "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5432/bootcamp",
    "TEST_DATABASE_URL": (
        "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
    ),
    "INTERNAL_TOKEN": "default_token",
    "ANALYSIS_PROVIDER_URL": "http://127.0.0.1:1080",
    "SERVER_LOCALHOST": "127.0.0.1",
    "MOCKSERVER_URL": "http://127.0.0.1:1080",
}.items():
    environ.setdefault(name, value)
