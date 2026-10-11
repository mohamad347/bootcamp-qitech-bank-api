# BaaS Simplificado

API de Banking as a Service desenvolvida no Bootcamp QI Tech 2026. O projeto atende uma plataforma parceira por implantação e modela cadastro de clientes PF/PJ, contas e movimentações em reais. A proposta é evoluir o serviço com TDD, validando cada comportamento antes de implementá-lo.

**Estado atual:** o schema PostgreSQL v1.1 e seus testes de integração estão implementados. A R01 `POST /client` cadastra pessoas físicas e jurídicas e já está integrada à `main`. A R02 `GET /client/{client_key}` também está implementada e tecnicamente aprovada nesta branch, aguardando integração. As rotas R03–R09 continuam em desenvolvimento.

## Escopo do produto

O fluxo previsto começa com o cadastro e a análise de um cliente, segue para a abertura de uma única conta e permite depósitos, transferências e consulta de extrato. O desenho também prevê histórico de status, proteção contra saldo negativo, transações atômicas e controle de retentativas financeiras.

O D0 opera no Brasil, em BRL, com uma plataforma parceira por implantação. PIX, TED, boleto, saque, KYC externo, múltiplas moedas e um ledger contábil completo ficam fora deste escopo. As regras e seus motivos estão no [RFC](docs/RFC_v1_BaaS_Simplificado_QITech.md).

## O que já funciona

| Área | Situação |
| --- | --- |
| Banco | `database/database.sql` cria as dez tabelas do [ERD v1.1](docs/ERD_v1_1_FINAL_BaaS_QITech.md), com status iniciais, chaves, constraints e índices aprovados. |
| Testes do banco | A suíte em `tests/integration/database/` verifica a estrutura e as restrições em PostgreSQL real, usando um banco descartável separado. |
| API básica | `GET /health_check` responde `204` sem token. A aplicação também possui rota raiz, middlewares e tratamento de erros. |
| Rotas bancárias R01–R09 | R01 implementada e integrada à `main`; R02 implementada e aprovada tecnicamente, aguardando integração; R03–R09 pendentes. |

A R02 exige `INTERNAL-TOKEN` e consulta clientes `INDIVIDUAL` e `COMPANY`
nos estados `PENDING`, `ACTIVE`, `REJECTED` e `INACTIVE`. A resposta é um
snapshot público, sem IDs internos, contas ou eventos, e a operação é somente
leitura. A R02 utiliza os erros contratuais `400 QIT000001`, `403 QIT000002` e
`404 CLI0001`. Falhas internas seguem o tratamento centralizado
`500 QIT000500`. O marco de validação da implementação é **128 passed**.

As dez tabelas se dividem em:

- **Cliente:** `client_status`, `client`, `individual_client`, `company_client` e `client_status_event`.
- **Conta:** `account_status`, `account` e `account_status_event`.
- **Financeiro:** `financial_transaction` e `transaction_entry`.

A aplicação ainda contém endpoints de demonstração. Eles não fazem parte do contrato bancário, e suas tabelas não são criadas pelo SQL principal.

## Preparar o ambiente

Para subir a API e o PostgreSQL, você precisa de Docker com Compose. Para rodar os testes no computador, precisa também de Python 3.11 ou superior.

Na raiz do repositório:

```powershell
docker compose up -d --build --wait
docker compose ps
curl.exe -i http://localhost:3000/health_check
```

O último comando deve retornar `204 No Content`. Ele verifica se o processo HTTP está respondendo; não consulta o PostgreSQL. Para acompanhar a API, use `docker compose logs -f api`. Para parar os dois serviços, use `docker compose stop`.

O Compose principal sobe `api` e `db`. O PostgreSQL executa `database/database.sql` quando inicializa um diretório de dados vazio. Reconstruir a imagem ou reiniciar um banco já inicializado não reaplica esse arquivo; mudanças posteriores no SQL devem ser verificadas no banco descartável de testes. O projeto ainda não usa migrations.

As portas padrão são `3000` para a API e `5432` para o banco. Para mudar uma porta ou o token local, copie [`.env.example`](.env.example) para `.env` e edite os valores. O `.env` é ignorado pelo Git. Se alterar `DB_PORT`, atualize também a porta em `DATABASE_URL` usada pelos testes executados fora do Docker. Os valores padrão de usuário, senha e token são apenas para desenvolvimento local.

## Rodar os testes

No PowerShell, crie o ambiente virtual e instale as dependências de desenvolvimento uma vez:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

No macOS ou Linux, use `python3.11 -m venv .venv` e `.venv/bin/python` nos comandos seguintes.

### Testes do schema

Estes testes **apagam e recriam `public` no banco de teste**. Use uma URL descartável, diferente do banco da API. No PowerShell:

```powershell
$env:TEST_DB_PORT = "55432"
docker compose -f compose.test.yml up -d --build --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:55432/bootcamp_test"
.\.venv\Scripts\python.exe -m pytest tests/integration/database -q
```

`55432` é uma porta de exemplo; se estiver ocupada, escolha outra em `TEST_DB_PORT` e use o mesmo número na URL. A suíte exige que o nome do banco termine em `_test` e recusa a mesma URL de `DATABASE_URL`. O reset ocorre uma vez por sessão; as linhas inseridas por cada teste são desfeitas por transação.

### Testes da API básica

Com o Compose principal em execução:

```powershell
$env:SERVER_LOCALHOST = "127.0.0.1"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_healthcheck.py -q
```

Com a API **e** o banco de teste ativos e `TEST_DATABASE_URL` definido, `.\.venv\Scripts\python.exe -m pytest -q` executa a suíte inteira, incluindo os testes da R01 e da R02. O [guia dos testes de schema](docs/Testes_do_Schema_v1_1.md) explica a cobertura e como acrescentar novos cenários.

Os testes de persistência da R01 fazem POST na API e consultam, somente para leitura, o banco principal `bootcamp` por `DATABASE_URL` (padrão local: `localhost:5432`). Eles não usam `bootcamp_test` nem desfazem os commits da API; os dados de cada execução são únicos.

Para parar somente o banco de teste:

```powershell
docker compose -f compose.test.yml stop db_test
```

## Contratos da API

As rotas abaixo formam o contrato v1.1 do produto. **R01 e R10 estão disponíveis na `main`**. A R02 está implementada nesta branch e aguarda integração; R03–R09 indicam trabalho previsto, não endpoints já utilizáveis.

| Grupo | Rotas do contrato |
| --- | --- |
| Cliente | R01 `POST /client`, R02 `GET /client/{client_key}`, R03 `POST /client/{client_key}/analysis` e R09 `PATCH /client/{client_key}`. |
| Conta | R04 `POST /client/{client_key}/account`, R05 `GET /account/{account_key}` e R06 `PATCH /account/{account_key}`. |
| Movimentação | R07 `POST /account/{account_key}/transaction` para depósito e transferência; R08 `GET /account/{account_key}/transactions` para extrato. |
| Liveness | R10 `GET /health_check` — implementada, sem autenticação e sem dependência do banco. |

As rotas de negócio usarão `INTERNAL-TOKEN`. Consulte [Rotas v1.1](docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md) para payloads, respostas e códigos de erro. O [documento de fluxos](docs/Fluxos_v1_1_FINAL_BaaS_QITech.md) descreve validações, transações, locks e caminhos de falha.

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `database/database.sql` | Bootstrap físico do banco v1.1. |
| `src/` | API FastAPI; a infraestrutura básica existe, e as features bancárias serão adicionadas por fluxo. |
| `tests/integration/database/` | Testes diretos do schema PostgreSQL. |
| `tests/integration/client/` | Testes HTTP da R01 e da R02, além da verificação separada da persistência da R01. |
| `tests/integration/test_healthcheck.py` | Testes HTTP da API básica. |
| `docker-compose.yml` | API e banco de desenvolvimento. |
| `compose.test.yml` | PostgreSQL isolado para testes de schema. |
| `docs/` | Contratos e guia de testes versionados. |

O desenvolvimento seguirá ciclos pequenos de **RED → GREEN → REFACTOR**. Para cada rota, começaremos pelo comportamento observável em teste HTTP e implementaremos as camadas necessárias para fazê-lo passar. Os testes de schema protegem o contrato físico já criado; os próximos testes protegerão os fluxos de negócio.

## Documentação

- [ERD v1.1](docs/ERD_v1_1_FINAL_BaaS_QITech.md): entidades, relações e decisões do banco.
- [Rotas v1.1](docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md): contratos HTTP e regras transversais.
- [Fluxos v1.1](docs/Fluxos_v1_1_FINAL_BaaS_QITech.md): sequência de validações, escritas, locks e respostas.
- [RFC](docs/RFC_v1_BaaS_Simplificado_QITech.md): contexto, escolhas e limites do D0.
- [Organização do projeto](docs/como-o-projeto-e-organizado.md): mapa do código atual e caminho para implementar as próximas rotas.
- [Testes do schema v1.1](docs/Testes_do_Schema_v1_1.md): cobertura, isolamento e execução da suíte de banco.

`docs/pessoal/` contém anotações locais ignoradas pelo Git e não é necessária para seguir este README. As referências acima ficam em `docs/`, fora dessa pasta.
