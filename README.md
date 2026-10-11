# BaaS Simplificado

API de **Banking as a Service (BaaS)** desenvolvida no **Bootcamp QI Tech 2026**. O projeto atende uma plataforma parceira por implantação e modela cadastro de clientes PF/PJ, análise cadastral, abertura e ciclo de vida de contas e movimentações em reais (BRL). O desenvolvimento segue **TDD (RED → GREEN → REFACTOR)**, com testes HTTP, integração com PostgreSQL real, concorrência e rollback.

> **Estado do projeto — 12/10/2026:** **R01–R06, R09 e R10 estão implementadas e integradas à `main`**. A **R07 (transações)** está em desenvolvimento por outro integrante; a **R08 (extrato paginado)** será implementada em seguida. A auditoria de DTOs das R01–R04 preservou os contratos e introduziu somente a projeção pública da R02, onde havia ganho concreto.
>
> **Última regressão confirmada na `main`: 271 testes aprovados, 1 warning não bloqueante** (`MovedIn20Warning` do SQLAlchemy). Esta é uma fotografia da `main` antes da integração das R07/R08; não representa testes dessas duas rotas.

## Escopo do produto

O fluxo do D0 começa no cadastro de clientes individuais e empresas, passa pela análise cadastral, abertura de uma única conta por cliente e prevê depósitos, transferências e consulta de extrato. O desenho inclui históricos de status, proteção contra saldo negativo, atomicidade das operações e tratamento de retentativas financeiras.

O D0 opera no Brasil, em BRL, com uma plataforma parceira por implantação. **PIX, TED, boleto, saque, KYC externo, múltiplas moedas e ledger contábil completo** estão fora do escopo. As decisões de produto e os seus motivos estão no [RFC](docs/RFC_v1_BaaS_Simplificado_QITech.md).

## Estado das rotas

| Rota | Método e endpoint | Situação na `main` |
| --- | --- | --- |
| R01 | `POST /client` | **Implementada e validada** — cadastro PF/PJ |
| R02 | `GET /client/{client_key}` | **Implementada e validada** — snapshot cadastral |
| R03 | `POST /client/{client_key}/analysis` | **Implementada e validada** — análise cadastral |
| R04 | `POST /client/{client_key}/account` | **Implementada e validada** — abertura de conta |
| R05 | `GET /account/{account_key}` | **Implementada e validada** — consulta de conta |
| R06 | `PATCH /account/{account_key}` | **Implementada e validada** — ciclo de vida da conta |
| R07 | `POST /account/{account_key}/transaction` | **Em desenvolvimento, fora da `main`** — depósito/transferência |
| R08 | `GET /account/{account_key}/transactions` | **Planejada, ainda não integrada** — extrato paginado |
| R09 | `PATCH /client/{client_key}` | **Implementada e validada** — ciclo de vida do cliente |
| R10 | `GET /health_check` | **Implementada e auditada** — `204 No Content`, pública, sem acesso SQL no caminho validado |

**Atenção:** R07 e R08 constam do contrato, mas **não devem ser apresentadas como disponíveis na `main`** até terem seus respectivos PRs integrados e validados. As rotas de negócio usam `INTERNAL-TOKEN`; a R10 é pública.

### Comportamentos implementados relevantes

- **R01–R02:** criação e consulta de clientes `INDIVIDUAL` e `COMPANY`. A R02 devolve apenas os campos públicos do snapshot e não expõe IDs internos, contas ou eventos.
- **R03:** análise por provider simulado no ambiente de desenvolvimento/teste (MockServer), com revalidação do CLIENT sob `SELECT ... FOR UPDATE` após a chamada externa, sem manter lock durante o HTTP.
- **R04:** abertura de uma única conta por CLIENT `ACTIVE`, com restrição de unicidade no banco, evento inicial e proteção contra aberturas concorrentes.
- **R05:** consulta por `account_key` com DTO público de resposta (`AccountDTO`).
- **R06:** transições coordenadas de CLIENT e ACCOUNT com lock na ordem **CLIENT → ACCOUNT**, histórico e rollback atômico. O encerramento exige saldo zero.
- **R09:** mudanças diretas permitidas no CLIENT com lock pessimista e histórico; atualizações `ACTIVE ↔ INACTIVE` são rejeitadas se o CLIENT já possui ACCOUNT, inclusive `CLOSED`.
- **R10:** `204` com corpo vazio, sem `INTERNAL-TOKEN`; os testes comprovam que o caminho instrumentado não adquire sessão ou conexão SQL.

## Arquitetura

A aplicação utiliza **FastAPI**, **SQLAlchemy** e **PostgreSQL** e organiza a API em camadas:

```text
HTTP request
    ↓
app.py / middlewares (autenticação e contexto)
    ↓
resources + JSON Schema (transporte e validação de entrada)
    ↓
controllers (regras de negócio, orquestração e transação)
    ↓
repositories + models (consultas, locks e persistência)
    ↓
DTOs / projeção pública (quando úteis)
    ↓
HTTP response
```

O projeto **já usa DTOs** nas R02 (`ClientDTO`), R03 (`ClientAnalysisDTO`), R05 (`AccountDTO`), R06 (`AccountPatchDTO`) e R09 (`ClientPatchDTO`). A auditoria das R01–R04 manteve os `dicts` simples de R01 e R04, porque não havia ganho concreto em novas classes. **JSON Schema valida a estrutura de entrada; DTOs, quando pertinentes, projetam dados públicos.** Nenhum DTO altera contratos HTTP ou invariantes de persistência. A R10 não necessita DTO porque retorna `204 No Content`.

As dez tabelas do schema v1.1 se distribuem em:

| Domínio | Tabelas |
| --- | --- |
| Cliente | `client_status`, `client`, `individual_client`, `company_client`, `client_status_event` |
| Conta | `account_status`, `account`, `account_status_event` |
| Financeiro | `financial_transaction`, `transaction_entry` |

A definição física está em [`database/database.sql`](database/database.sql) e no [ERD v1.1](docs/ERD_v1_1_FINAL_BaaS_QITech.md). O projeto ainda não utiliza migrations. Endpoints e entidades de demonstração não pertencem ao contrato bancário nem ao bootstrap principal.

## Preparar o ambiente

Pré-requisitos: **Docker com Compose** e **Python 3.11 ou superior** para executar os testes localmente.

Na raiz do repositório:

```powershell
docker compose up -d --build --wait
docker compose ps
curl.exe -i http://localhost:3000/health_check
```

O último comando deve retornar **HTTP 204**, sem corpo. É um teste de *liveness* HTTP e **não** comprova a disponibilidade do PostgreSQL. Para acompanhar logs, use `docker compose logs -f api`; para parar sem apagar volumes, `docker compose stop`.

O Compose principal executa `api`, `db` e, quando configurado na versão utilizada, `mockserver` para simular a integração da R03. Confira os serviços efetivos com `docker compose ps`. O bootstrap `database/database.sql` só é aplicado quando o diretório de dados do PostgreSQL é inicializado vazio; reiniciar/reconstruir o container não reaplica o SQL automaticamente.

Portas locais de referência: API `3000`, PostgreSQL principal `5432`, MockServer `1080` (quando ativo). Para personalizar configuração, copie [`.env.example`](.env.example) para `.env`. O `.env` é ignorado pelo Git. Valores padrão de usuário, senha e token são **somente para desenvolvimento local**.

## Rodar os testes

Crie o ambiente virtual e instale dependências de desenvolvimento uma vez:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Em macOS/Linux, use `python3.11 -m venv .venv` e `.venv/bin/python`.

### PostgreSQL isolado dos testes de schema

**Atenção: a suíte de schema recria o schema `public` do banco de testes.** Nunca use a URL do PostgreSQL principal para esse procedimento.

```powershell
$env:TEST_DB_PORT = "5433"
docker compose -f compose.test.yml up -d --build --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
.\.venv\Scripts\python.exe -m pytest tests/integration/database -q
```

A porta **5433 é o exemplo usado nesta configuração**; escolha outra livre se necessário, definindo o mesmo número em `TEST_DB_PORT` e `TEST_DATABASE_URL`. A proteção de testes recusa o banco principal e exige banco de testes dedicado. **Não execute DROP, TRUNCATE ou reset de volumes no banco principal.**

### Testes HTTP e regressão completa

Com API, PostgreSQL principal, PostgreSQL de testes e MockServer necessários à suíte disponíveis:

```powershell
$env:SERVER_LOCALHOST = "127.0.0.1"
$env:MOCKSERVER_URL = "http://127.0.0.1:1080"
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
.\.venv\Scripts\python.exe -m pytest -q
```

O teste específico do healthcheck pode ser executado com:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_healthcheck.py -q
```

**Última baseline validada após o merge da R10:** `271 passed, 1 warning`. O warning `MovedIn20Warning`, originado no import legado de `declarative_base()` em `src/models/base.py`, é conhecido e não bloqueante. A contagem mudará quando novos testes e R07/R08 forem integrados.

Os testes HTTP das rotas de negócio podem gravar **registros exclusivos de teste** no banco principal `bootcamp` por meio da API. Eles não são automaticamente revertidos pelo banco `bootcamp_test`. Use o banco descartável exclusivamente para os testes de schema, como previsto na configuração do projeto; coordene execuções concorrentes com outras pessoas se compartilharem a instância.

Para parar somente o PostgreSQL de testes:

```powershell
docker compose -f compose.test.yml stop db_test
```

## Contratos e documentação

A [especificação de Rotas v1.1](docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md) define payloads, respostas, autenticação e erros. O [documento de Fluxos v1.1](docs/Fluxos_v1_1_FINAL_BaaS_QITech.md) cobre validações, atomicidade, eventos, locks e cenários de falha. A [especificação de implementação da R07](docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md) não substitui decisões posteriores formalizadas pela equipe para a rota financeira: conflitos contratuais devem ser resolvidos antes do merge, sem atualizar silenciosamente contratos públicos.

| Documento | Conteúdo |
| --- | --- |
| [RFC v1](docs/RFC_v1_BaaS_Simplificado_QITech.md) | Objetivo, decisões de produto e limitações do D0 |
| [ERD v1.1](docs/ERD_v1_1_FINAL_BaaS_QITech.md) | Modelo físico e relacionamentos |
| [Rotas v1.1](docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md) | Contrato HTTP das R01–R10 |
| [Fluxos v1.1](docs/Fluxos_v1_1_FINAL_BaaS_QITech.md) | Caminhos de sucesso, falhas e concorrência |
| [Organização do projeto](docs/como-o-projeto-e-organizado.md) | Visão geral das camadas e do repositório (pode conter informações históricas) |
| [Testes do schema](docs/Testes_do_Schema_v1_1.md) | Isolamento e testes físicos de banco |
| [R02 — Plano](docs/R02_Plano_Completo_Testes_e_Implementacao.md) | Consulta de CLIENT |
| [R03 — Testes por comportamento](tests/integration/client/r03/) | Análise externa e concorrência |
| [R04 — Plano](docs/R04_Plano_Completo_Testes_e_Implementacao.md) | Abertura de ACCOUNT |
| [R05 — Plano](docs/R05_Plano_Completo_Testes_e_Implementacao.md) | GET ACCOUNT e DTO |
| [R06 — Plano](docs/R06_Plano_Completo_Testes_e_Implementacao.md) | Lifecycle coordenado de ACCOUNT |
| [R09 — Plano](docs/R09_Plano_Completo_Testes_e_Implementacao.md) | Lifecycle de CLIENT |
| [R10 — Plano](docs/R10_Plano_Completo_Testes_e_Implementacao.md) | Auditoria do healthcheck |

A padronização de DTOs das R01–R04 está documentada em [`docs/R01_R04_Plano_Padronizacao_DTOs.md`](docs/R01_R04_Plano_Padronizacao_DTOs.md). Ela introduziu apenas o `ClientDTO` da R02 e não alterou R07/R08 nem contratos públicos.

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `src/app.py`, `src/middlewares/` | Registro de rotas, autenticação e contexto |
| `src/resources/`, `src/schemas/` | HTTP e validação de entrada |
| `src/controllers/`, `src/repositories/` | Domínio, transações e persistência |
| `src/models/`, `src/dtos/` | Modelos internos e projeções públicas |
| `database/database.sql` | Bootstrap do PostgreSQL v1.1 |
| `tests/integration/client/` | Testes de rotas e cenários bancários |
| `tests/integration/database/` | Testes do schema em banco descartável |
| `tests/integration/test_healthcheck.py` | Contrato e isolamento da R10 |
| `docker-compose.yml`, `compose.test.yml` | Serviços e banco de testes |
| `docs/` | Especificações, planos e evidências de TDD |

`docs/pessoal/` contém anotações locais ignoradas pelo Git e não é necessária para seguir este README.

## Colaboração e próximos passos

O desenvolvimento ocorre em **branches independentes**, com PRs integradas à `main` somente após validação. No momento, um integrante desenvolve **R07**, depois seguirá com **R08**. Em paralelo, a **auditoria de DTOs de R01–R04** foi concluída, priorizando diferenças reais entre representação HTTP e domínio, sem alterações de locks, migrations, eventos ou contratos de respostas.

Após o merge de R07 e R08, a equipe fará **regressão integrada e auditoria das dez rotas**, incluindo contratos, DTOs, concorrência financeira, idempotência, segurança e documentação.
