# BaaS Simplificado

**API REST de Banking as a Service (BaaS)** desenvolvida para o **Bootcamp QI Tech 2026** por **João Vitor Miranda Sousa** e **Mohamad Ahmad Barakat**.

O projeto implementa o ciclo bancário básico de uma plataforma parceira: cadastro de pessoas físicas (PF) e jurídicas (PJ), análise cadastral, abertura e gerenciamento de contas, depósitos, transferências e consulta de extrato. A solução prioriza **consistência financeira, integridade dos estados, idempotência, concorrência e rastreabilidade**, com desenvolvimento orientado a testes (**TDD — RED → GREEN → REFACTOR**).

> **Entrega — 12/10/2026:** as **10 rotas (R01–R10)** estão integradas à `main`. A última regressão integrada informada pela equipe concluiu com **426 testes aprovados em 64,58 s**. Esses números registram uma execução validada, não uma promessa de resultado em qualquer ambiente.

## Documentação

| Documento | Finalidade |
|---|---|
| [RFC — Markdown](docs/RFC.md) | Contexto, solução proposta, decisões arquiteturais, rotas, modelo de dados e principais fluxos |
| [RFC — PDF](docs/RFC.pdf) | Versão de apresentação da RFC, em A4 |
| [Modelo de Dados — ERD](docs/ERD.md) | Entidades, relacionamentos, integridade referencial e decisões de persistência |
| [Contratos da API — ROTAS](docs/ROTAS.md) | Headers, parâmetros, payloads, respostas, códigos HTTP e regras por endpoint |
| [Fluxos de Negócio — FLUXOS](docs/FLUXOS.md) | Diagramas Mermaid de sucesso, falha, transações, concorrência e idempotência |

**Modelo interativo:** [visualizar o ERD no dbdiagram.io](https://dbdiagram.io/d/ERD-bootcamp-QItech-6abc58be5869425612d24fa6). O esquema físico versionado encontra-se em [`database/database.sql`](database/database.sql).

## Funcionalidades e endpoints

As operações de negócio exigem o header **`INTERNAL-TOKEN`**. A rota de healthcheck é pública.

| ID | Método | Endpoint | Funcionalidade |
|---|---|---|---|
| R01 | `POST` | `/client` | Cadastro de cliente PF/PJ |
| R02 | `GET` | `/client/{client_key}` | Consulta cadastral |
| R03 | `POST` | `/client/{client_key}/analysis` | Análise cadastral por provedor externo simulado |
| R04 | `POST` | `/client/{client_key}/account` | Abertura de conta |
| R05 | `GET` | `/account/{account_key}` | Consulta de conta e saldo |
| R06 | `PATCH` | `/account/{account_key}` | Alteração do estado da conta |
| R07 | `POST` | `/account/{account_key}/transaction` | Depósito e transferência com idempotência |
| R08 | `GET` | `/account/{account_key}/transactions` | Extrato paginado de lançamentos |
| R09 | `PATCH` | `/client/{client_key}` | Alteração do estado cadastral |
| R10 | `GET` | `/health_check` | Verificação de vida da API (`204`, sem autenticação) |

Os contratos completos, com exemplos de requisição e resposta, estão em [`docs/ROTAS.md`](docs/ROTAS.md).

### Regras de negócio relevantes

- **Clientes:** perfis `INDIVIDUAL` e `COMPANY`, documentos validados, cadastro inicial `PENDING` e histórico de mudanças de estado.
- **Contas:** no máximo uma conta por cliente durante todo o ciclo de vida; abertura condicionada ao cliente elegível; saldo não negativo e encerramento somente com saldo zero.
- **Análise cadastral:** integração HTTP com o provedor simulado no ambiente local; revalidação do estado do cliente após a resposta externa.
- **Depósitos e transferências:** valores representados em **centavos de BRL**, com atualizações de saldo e lançamentos persistidos atomicamente.
- **Tarifa de transferência:** calculada no servidor conforme o perfil da conta de origem. Para PF, **0,50%**, mínimo de **R$ 0,50** e máximo de **R$ 10,00**; para PJ, **1,00%**, mínimo de **R$ 1,00** e máximo de **R$ 15,00**, com arredondamento `HALF_UP`.
- **Idempotência da R07:** header obrigatório `Idempotency-Key` (UUID), associado à intenção da operação. Retentativas idênticas não duplicam movimentações; reutilizações conflitantes são rejeitadas.
- **Concorrência financeira:** locks pessimistas ordenados, validação de saldo sob lock e `COMMIT` único; falhas antes da confirmação provocam `ROLLBACK`.
- **Extrato R08:** paginação por **lançamento** (`TRANSACTION_ENTRY`), incluindo principal e tarifa, ordenação determinística e filtros por datas civis interpretadas no timezone do cliente.

O produto atende **uma plataforma parceira por implantação**, no Brasil e em **BRL**. PIX, TED, boletos, saques, KYC comercial real, multi-tenancy e contabilidade completa por partidas dobradas estão fora do escopo deste MVP.

## Tecnologias e arquitetura

| Componente | Tecnologia / responsabilidade |
|---|---|
| API | Python, FastAPI |
| Persistência | PostgreSQL, SQLAlchemy |
| Validação de entrada | JSON Schema |
| Integração de análise | HTTP e MockServer no ambiente de desenvolvimento/testes |
| Ambiente | Docker e Docker Compose |
| Qualidade | pytest, testes unitários e de integração, TDD |

```text
Requisição HTTP
      |
      v
FastAPI / middlewares
      |
      v
resources + validação JSON Schema
      |
      v
controllers (regras de negócio e transações)
      |
      v
repositories + models (PostgreSQL)
      |
      v
DTOs / projeções de resposta, quando aplicáveis
      |
      v
Resposta HTTP
```

O banco possui **10 tabelas**, agrupadas em cadastro, contas e movimentações financeiras. Os históricos de mudança de estado são persistidos separadamente dos estados atuais, enquanto `financial_transaction` e `transaction_entry` registram as operações e seus efeitos. Consulte o [ERD](docs/ERD.md) para cardinalidades e restrições.

## Executar localmente com Docker

**Pré-requisitos:** Docker com Compose. Para executar a suíte de testes fora dos containers, também é necessário **Python 3.11 ou superior**.

Clone o repositório e entre na pasta do projeto:

```powershell
git clone https://github.com/mohamad347/bootcamp-qitech-bank-api.git
cd bootcamp-qitech-bank-api
```

Se necessário, crie o arquivo de configuração local a partir do exemplo versionado:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Inicie os serviços definidos no Compose principal:

```powershell
docker compose up -d --build --wait
docker compose ps
```

Verifique o funcionamento HTTP:

```powershell
curl.exe -i http://localhost:3000/health_check
```

**Resultado esperado:** `HTTP 204 No Content`, sem corpo. Esse endpoint verifica a resposta HTTP do processo, **não** a disponibilidade do PostgreSQL.

Para consultar logs ou parar os serviços sem remover volumes:

```powershell
docker compose logs -f api
docker compose stop
```

As portas locais de referência são **3000** (API), **5432** (PostgreSQL principal) e **1080** (MockServer, quando habilitado). Os valores de `.env.example` e as credenciais de desenvolvimento são destinados **somente ao ambiente local**. O script [`database/database.sql`](database/database.sql) inicializa o esquema no primeiro provisionamento de um volume PostgreSQL vazio; reconstruir um container não reinicializa automaticamente um volume persistente.

## Executar os testes

A suíte inclui testes de contrato HTTP, regras de domínio, persistência, estados, idempotência, concorrência, rollback, movimentações financeiras e extrato.

### 1. Instalar as dependências de desenvolvimento (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

No Linux/macOS, substitua a criação do ambiente por `python3.11 -m venv .venv` e utilize `.venv/bin/python` nos comandos seguintes.

### 2. Subir o PostgreSQL isolado para testes de esquema

Os testes de esquema usam uma instância separada: **não aponte `TEST_DATABASE_URL` para o banco principal**.

```powershell
$env:TEST_DB_PORT = "5433"
docker compose -f compose.test.yml up -d --build --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
```

> **Cuidado:** os testes em `tests/integration/database/` podem recriar o schema `public` **do banco de testes**. Nunca utilize dados reais ou a URL do banco principal nessa configuração.

### 3. Executar a regressão

Com os serviços necessários disponíveis:

```powershell
$env:SERVER_LOCALHOST = "127.0.0.1"
$env:MOCKSERVER_URL = "http://127.0.0.1:1080"
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"

.\.venv\Scripts\python.exe -m pytest -q
```

Para executar somente os testes físicos do esquema:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/database -q
```

**Última regressão integrada informada pela equipe:** `426 passed in 64.58s` (12/10/2026).

**Isolamento:** o banco `bootcamp_test` destina-se aos testes de esquema, mas certos testes HTTP de integração podem criar **dados exclusivamente de teste** no banco local principal por meio da API. Não execute a suíte apontando a aplicação para um banco de produção ou com dados reais. Para parar somente o banco de testes:

```powershell
docker compose -f compose.test.yml stop db_test
```

## Estrutura do repositório

```text
bootcamp-qitech-bank-api/
├── src/                       # API, regras de negócio e persistência
├── database/
│   └── database.sql           # Esquema PostgreSQL
├── tests/                     # Testes unitários, HTTP, integração e banco
├── docs/
│   ├── RFC.md                 # RFC no formato original Markdown
│   ├── RFC.pdf                # RFC para submissão
│   ├── ERD.md                 # Modelo de dados e decisões de persistência
│   ├── ROTAS.md               # Contratos HTTP
│   └── FLUXOS.md              # Fluxos Mermaid e cenários de falha
├── docker-compose.yml         # Ambiente principal
├── compose.test.yml           # Banco isolado para testes de esquema
├── requirements-dev.txt
└── README.md
```

A documentação complementar descreve as decisões e os trade-offs arquiteturais com mais profundidade. **Para conhecer o projeto, comece pela [RFC](docs/RFC.md); para integrar a API, consulte [ROTAS](docs/ROTAS.md); para entender a persistência, veja o [ERD](docs/ERD.md) e os [FLUXOS](docs/FLUXOS.md).**

---

**Autores:** João Vitor Miranda Sousa · Mohamad Ahmad Barakat

**Projeto acadêmico:** Bootcamp QI Tech 2026 — BaaS Simplificado.
