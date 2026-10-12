import sys
from os import environ
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# A coleta também importa módulos puros sob ``src/``. Definir o caminho e as
# configurações mínimas aqui evita depender da ordem em que outros testes
# importam a aplicação. Os defaults apontam exclusivamente para a stack de
# teste do Compose principal. O pytest não carrega .env porque esse arquivo
# configura a demonstração e poderia direcionar a suíte aos serviços principais.
# Variáveis definidas explicitamente no processo continuam tendo precedência.
src_root = root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

for name, value in {
    "DATABASE_URL": "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:55433/bootcamp",
    "TEST_DATABASE_URL": (
        "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:55432/bootcamp_schema_test"
    ),
    "INTERNAL_TOKEN": "default_token",
    "ANALYSIS_PROVIDER_URL": "http://127.0.0.1:1081",
    "SERVER_LOCALHOST": "127.0.0.1",
    "API_PORT": "3001",
    "MOCKSERVER_URL": "http://127.0.0.1:1081",
}.items():
    environ.setdefault(name, value)
