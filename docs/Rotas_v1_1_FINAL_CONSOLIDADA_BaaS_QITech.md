# Rotas v1.1 — FINAL CONSOLIDADA
## BaaS Simplificado — Bootcamp QI Tech 2026

**Time:** João Vitor + Moha  
**Data:** 06/10/2026  
**Versão:** 1.1  
**Status:** ✅ FINAL / AUDITADA / CONSOLIDADA / CONGELADA

---

# 1. Objetivo deste documento

Este arquivo consolida, em uma única especificação, as convenções transversais e os contratos finais das rotas `R01` a `R10`.

A consolidação foi produzida a partir de:

```text
ERD_v1_1_FINAL_BaaS_QITech.md
00_CONVENCOES_TRANSVERSAIS_Rotas_v1_1_FINAL_BaaS_QITech.md
R01_POST_client_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R02_GET_client_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R03_POST_client_analysis_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R04_POST_client_account_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R05_GET_account_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R06_PATCH_account_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R07_POST_account_transaction_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R08_GET_account_transactions_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R09_PATCH_client_v1_1_FINAL_CONGELADA_BaaS_QITech.md
R10_GET_health_check_v1_1_FINAL_CONGELADA_BaaS_QITech.md
```

Os arquivos individuais foram usados na consolidação, mas não integram a documentação versionada deste repositório. Para implementar as rotas, use este documento como contrato de referência.

Este documento passa a ser a referência compacta das **Rotas v1.1** para implementação e para derivação da seção de rotas da RFC.

---

# 2. Resultado da auditoria

Foram comparados:

```text
contratos HTTP
modelo do ERD
lifecycle de CLIENT
lifecycle de ACCOUNT
modelo financeiro
idempotência
locks
atomicidade
timezone
paginação
catálogo de erros
```

Resultado:

```text
R01–R10 compatíveis com ERD v1.1
✅

nenhuma contradição de domínio identificada
✅

alterações posteriores ao ERD propagadas para as rotas
✅
```

Pontos da v1.1 confirmados durante a auditoria:

```text
CLIENT.timezone obrigatório e usado pela R08
reanálise REJECTED -> PENDING sem limite máximo
uma ACCOUNT por CLIENT durante toda a vida
CLOSED terminal
fechamento somente com balance_cents == 0
BRL como moeda única do D0
fee de TRANSFER por perfil da source, com piso, teto e HALF_UP
ordem PRINCIPAL -> FEE -> crédito do destino
request_control_key UNIQUE GLOBAL
request_hash SHA-256
locks de duas contas por ACCOUNT.id crescente
locks CLIENT -> ACCOUNT quando ambos são necessários
R10 como liveness sem PostgreSQL
```

---

# 3. Inventário final

| ID | Método | Path | Sucesso | Auth | Idempotência |
|---|---|---|---|---|---|
| R01 | `POST` | `/client` | `201` | `INTERNAL-TOKEN` | Não |
| R02 | `GET` | `/client/{client_key}` | `200` | `INTERNAL-TOKEN` | Sim |
| R03 | `POST` | `/client/{client_key}/analysis` | `200` | `INTERNAL-TOKEN` | Não |
| R04 | `POST` | `/client/{client_key}/account` | `201` | `INTERNAL-TOKEN` | Não |
| R05 | `GET` | `/account/{account_key}` | `200` | `INTERNAL-TOKEN` | Sim |
| R06 | `PATCH` | `/account/{account_key}` | `200` | `INTERNAL-TOKEN` | Não |
| R07 | `POST` | `/account/{account_key}/transaction` | `201` | `INTERNAL-TOKEN` | Sim, por key/hash |
| R08 | `GET` | `/account/{account_key}/transactions` | `200` | `INTERNAL-TOKEN` | Sim |
| R09 | `PATCH` | `/client/{client_key}` | `200` | `INTERNAL-TOKEN` | Não |
| R10 | `GET` | `/health_check` | `204` | Nenhuma | Sim |

---

# 4. Convenções transversais

## 4.1 Identificadores

```text
BIGINT id
-> interno

*_key UUID
-> público
```

IDs internos nunca são usados em URL ou devolvidos como identificador público.

Para `client_key` e `account_key` em path:

```text
UUID malformado
-> 400 QIT000001

UUID válido + recurso inexistente
-> 404
```

O comportamento automático do framework deve ser adaptado se divergir deste contrato.

---

## 4.2 Autenticação

R01–R09:

```text
INTERNAL-TOKEN obrigatório
```

Ausente ou inválido:

```text
403 QIT000002
```

A autenticação ocorre antes de resource lookup.

Consequência:

```text
token inválido + recurso inexistente
-> 403
```

R10 é a única exceção:

```text
GET /health_check
-> sem INTERNAL-TOKEN
```

---

## 4.3 Corpo padrão de erro

```json
{
  "title": "string",
  "description": "string",
  "translation": "string",
  "code": "string"
}
```

Convenção de prefixos:

```text
QIT* -> erros genéricos/transversais
CLI* -> domínio CLIENT
ACC* -> domínio ACCOUNT
TRX* -> domínio financeiro
```

---

## 4.4 Semântica HTTP

```text
400
-> request/schema/parâmetro inválido

403
-> INTERNAL-TOKEN ausente/inválido

404
-> recurso público não existe

409
-> conflito com estado atual, unicidade ou identidade já utilizada

422
-> request estruturalmente válida, mas regra semântica de domínio impede execução

500
-> falha interna inesperada
```

---

## 4.5 Dinheiro

```text
BIGINT em centavos
moeda fixa = BRL
```

Não utilizar `float`.

Não persistir `currency_code` no D0.

---

## 4.6 Timestamps

Persistência:

```text
TIMESTAMPTZ
```

Resposta HTTP:

```text
UTC
ISO 8601 / RFC3339
sufixo Z
```

Exceção conceitual:

```text
date_from/date_to da R08
-> datas civis interpretadas em CLIENT.timezone
-> depois convertidas para UTC
```

---

## 4.7 Histórico

Após commit:

```text
CLIENT_STATUS_EVENT     -> append-only
ACCOUNT_STATUS_EVENT    -> append-only
FINANCIAL_TRANSACTION   -> append-only
TRANSACTION_ENTRY       -> append-only
```

Nenhuma correção deve reescrever histórico confirmado.

---

## 4.8 Atomicidade

Regra geral:

```text
todas as escritas de uma operação de domínio
-> uma única transação PostgreSQL

falha antes do COMMIT
-> ROLLBACK integral
```

---

## 4.9 Locks globais

Quando houver:

```text
CLIENT + ACCOUNT
```

ordem:

```text
CLIENT
↓
ACCOUNT
```

Quando houver duas contas:

```text
menor ACCOUNT.id
↓
maior ACCOUNT.id
```

---

# 5. Catálogo consolidado de códigos

| Código | HTTP | Significado |
|---|---:|---|
| `QIT000001` | 400 | request/schema/parâmetro inválido |
| `QIT000002` | 403 | `INTERNAL-TOKEN` ausente/inválido |
| `QIT000500` | 500 | falha interna inesperada |
| `CLI0001` | 404 | CLIENT não encontrado |
| `CLI0002` | 409 | estado de CLIENT incompatível |
| `CLI0003` | 409 | email duplicado |
| `CLI0004` | 409 | CPF duplicado |
| `CLI0005` | 409 | CNPJ duplicado |
| `CLI0006` | 400 | CPF/CNPJ inválido |
| `CLI0007` | 422 | PF abaixo da idade mínima |
| `CLI0008` | 400 | timezone inválido/não suportado |
| `CLI0009` | 409 | lifecycle do CLIENT deve passar pela R06 porque existe ACCOUNT |
| `ACC0001` | 404 | ACCOUNT não encontrada |
| `ACC0002` | 409 | CLIENT já possui ACCOUNT |
| `ACC0003` | 409 | transição de ACCOUNT não permitida |
| `ACC0004` | 409 | saldo impede encerramento |
| `ACC0005` | 409 | ACCOUNT não está ACTIVE para movimentação |
| `TRX0001` | 422 | saldo insuficiente |
| `TRX0002` | 409 | self-transfer |
| `TRX0003` | 409 | conflito de idempotência |
| `TRX0004` | 422 | amount inválido, abaixo do mínimo da operação ou fora do limite técnico |
| `TRX0005` | 422 | intervalo de datas semanticamente inválido |

---

# 6. R01 — POST /client

## Contrato

```text
POST /client
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
cadastrar CLIENT PF ou PJ
```

Cria atomicamente:

```text
CLIENT
+
INDIVIDUAL_CLIENT ou COMPANY_CLIENT
+
CLIENT_STATUS_EVENT
NULL -> PENDING
actor_type = SYSTEM
```

O cliente sempre nasce:

```text
PENDING
```

---

## Entrada PF

```json
{
  "client_type": "INDIVIDUAL",
  "email": "joao@email.com",
  "cpf": "123.456.789-09",
  "full_name": "João Vitor Miranda Sousa",
  "birth_date": "2003-01-01",
  "timezone": "America/Sao_Paulo"
}
```

Regras:

```text
email
-> obrigatório
-> trim
-> lowercase
-> UNIQUE global

cpf
-> aceitar formato canônico ou máscara convencional
-> persistir apenas 11 dígitos
-> validar dígitos verificadores
-> UNIQUE

full_name
-> trim
-> não vazio

birth_date
-> data válida
-> idade >= 18 anos

timezone
-> obrigatório
-> IANA
-> pertencente ao conjunto brasileiro suportado
```

---

## Entrada PJ

```json
{
  "client_type": "COMPANY",
  "email": "contato@empresa.com",
  "cnpj": "12.345.678/0001-99",
  "legal_name": "Empresa Exemplo Ltda.",
  "trade_name": "Empresa Exemplo",
  "timezone": "America/Manaus"
}
```

Regras:

```text
cnpj
-> persistir apenas 14 dígitos
-> validar dígitos verificadores
-> UNIQUE

legal_name
-> trim
-> não vazio

trade_name
-> opcional
-> trim
-> vazio após trim -> null
```

A especialização PF/PJ é exclusiva.

---

## Sucesso

```http
201 Created
```

```json
{
  "client_key": "...",
  "client_type": "INDIVIDUAL",
  "status": "PENDING"
}
```

---

## Erros

```text
400 QIT000001 -> schema/body/combinação inválida
400 CLI0006   -> CPF/CNPJ inválido
400 CLI0008   -> timezone inválido/não suportado
403 QIT000002 -> auth
409 CLI0003   -> email duplicado
409 CLI0004   -> CPF duplicado
409 CLI0005   -> CNPJ duplicado
422 CLI0007   -> PF abaixo de 18 anos
500 QIT000500 -> falha interna
```

Idempotência:

```text
não
```

Unicidades do banco são proteção concorrente, não replay.

---

# 7. R02 — GET /client/{client_key}

## Contrato

```text
GET /client/{client_key}
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
consultar snapshot cadastral atual
```

Todos os status são legíveis:

```text
PENDING
ACTIVE
REJECTED
INACTIVE
```

---

## Resposta PF

```json
{
  "client_key": "...",
  "client_type": "INDIVIDUAL",
  "email": "joao@email.com",
  "timezone": "America/Sao_Paulo",
  "status": "ACTIVE",
  "cpf": "12345678909",
  "full_name": "João Vitor Miranda Sousa",
  "birth_date": "2003-01-01",
  "created_at": "...Z",
  "updated_at": "...Z"
}
```

## Resposta PJ

```json
{
  "client_key": "...",
  "client_type": "COMPANY",
  "email": "contato@empresa.com",
  "timezone": "America/Manaus",
  "status": "ACTIVE",
  "cnpj": "12345678000199",
  "legal_name": "Empresa Exemplo Ltda.",
  "trade_name": "Empresa Exemplo",
  "created_at": "...Z",
  "updated_at": "...Z"
}
```

`trade_name` ausente:

```text
null
```

Não embute:

```text
ACCOUNT
CLIENT_STATUS_EVENT
IDs internos
```

---

## Erros

```text
400 QIT000001 -> client_key malformada
403 QIT000002 -> auth
404 CLI0001   -> CLIENT não encontrado
500 QIT000500 -> falha interna/inconsistência de especialização
```

Idempotência:

```text
sim
```

Locks de escrita:

```text
nenhum
```

---

# 8. R03 — POST /client/{client_key}/analysis

## Contrato

```text
POST /client/{client_key}/analysis
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
solicitar análise cadastral a um Analysis Provider externo
```

O caller não envia a decisão e a rota não exige body. Durante o
desenvolvimento e os testes, o fornecedor externo é representado pelo
MockServer; a aplicação conhece somente `ANALYSIS_PROVIDER_URL`.

---

## Contrato com o Analysis Provider

```http
POST /v1/client-analysis
```

```json
{
  "client_key": "<uuid>",
  "client_type": "INDIVIDUAL",
  "document": "<cpf-ou-cnpj-normalizado>"
}
```

Respostas válidas:

```json
{
  "decision": "APPROVE",
  "reason": null
}
```

ou:

```json
{
  "decision": "REJECT",
  "reason": "Dados cadastrais não atendem aos critérios da análise."
}
```

Para `REJECT`, `reason` é obrigatório, sofre trim, não pode ficar vazio e
possui no máximo 500 caracteres.

---

## Transições

```text
APPROVE:
PENDING -> ACTIVE

REJECT:
PENDING -> REJECTED
```

Evento:

```text
actor_type = INTERNAL
```

---

## Concorrência e atomicidade

```text
buscar CLIENT e validar PENDING
↓
encerrar a transação de leitura
↓
chamar Analysis Provider
↓
SELECT CLIENT ... FOR UPDATE
↓
revalidar PENDING
↓
status + evento + COMMIT
```

O lock não permanece aberto durante a chamada HTTP. Duas análises
concorrentes podem chamar o provider, mas somente uma consome o estado
`PENDING`; a segunda retorna conflito depois de adquirir o lock.

Reanálise:

```text
REJECTED -> PENDING
-> pertence à R09
```

---

## Sucesso

```http
200 OK
```

```json
{
  "client_key": "...",
  "status": "ACTIVE"
}
```

ou:

```json
{
  "client_key": "...",
  "status": "REJECTED"
}
```

---

## Erros

```text
400 QIT000010 -> client_key não é UUID válido
403 QIT000002 -> auth
404 CLI0001   -> CLIENT inexistente
409 CLI0002   -> CLIENT não está PENDING
500 QIT000500 -> provider indisponível, timeout ou resposta externa inválida
```

Idempotência:

```text
não

repetição após sucesso
-> 409
```

---

# 9. R04 — POST /client/{client_key}/account

## Contrato

```text
POST /client/{client_key}/account
Auth: INTERNAL-TOKEN
Body: nenhum
```

Finalidade:

```text
abrir a única ACCOUNT permitida para o CLIENT
```

Pré-condições:

```text
CLIENT existe
CLIENT.status = ACTIVE
CLIENT nunca possuiu ACCOUNT
```

Cria:

```text
ACCOUNT
status = ACTIVE
balance_cents = 0

ACCOUNT_STATUS_EVENT
NULL -> ACTIVE
actor_type = SYSTEM
reason = null
```

---

## Cardinalidade

```text
1 CLIENT
-> 0 ou 1 ACCOUNT durante toda a vida
```

Proteção:

```text
ACCOUNT.client_id UNIQUE
```

Mesmo conta `CLOSED` impede criação de outra.

---

## Concorrência

Lock:

```text
CLIENT FOR UPDATE
```

A constraint `UNIQUE` permanece como última barreira concorrente.

---

## Sucesso

```http
201 Created
```

```json
{
  "account_key": "...",
  "status": "ACTIVE",
  "balance_cents": 0
}
```

---

## Erros

```text
400 QIT000001 -> client_key/request inválida
403 QIT000002 -> auth
404 CLI0001   -> CLIENT inexistente
409 CLI0002   -> CLIENT não ACTIVE
409 ACC0002   -> ACCOUNT já existe
500 QIT000500 -> falha interna
```

Idempotência:

```text
não
```

---

# 10. R05 — GET /account/{account_key}

## Contrato

```text
GET /account/{account_key}
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
snapshot atual da ACCOUNT
```

Todos os status são legíveis:

```text
ACTIVE
INACTIVE
CLOSED
```

---

## Sucesso

```http
200 OK
```

```json
{
  "account_key": "...",
  "client_key": "...",
  "status": "ACTIVE",
  "balance_cents": 125000,
  "created_at": "...Z",
  "updated_at": "...Z"
}
```

`balance_cents`:

```text
saldo operacional atual
centavos de BRL
```

A rota não recalcula o saldo pelo extrato.

Não embute:

```text
CLIENT completo
ACCOUNT_STATUS_EVENT
FINANCIAL_TRANSACTION
TRANSACTION_ENTRY
IDs internos
```

---

## Erros

```text
400 QIT000001 -> account_key malformada
403 QIT000002 -> auth
404 ACC0001   -> ACCOUNT inexistente
500 QIT000500 -> falha interna/inconsistência estrutural
```

Idempotência:

```text
sim
```

Lock de escrita:

```text
nenhum
```

---

# 11. R06 — PATCH /account/{account_key}

## Contrato

```text
PATCH /account/{account_key}
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
alterar lifecycle da ACCOUNT
e coordenar CLIENT quando necessário
```

Body:

```json
{
  "status": "INACTIVE",
  "reason": "Solicitação operacional"
}
```

Campos aceitos:

```text
status
reason
```

`reason`:

```text
obrigatório
trim
não vazio
máximo 500
```

---

## Transições permitidas

```text
ACTIVE   -> INACTIVE
INACTIVE -> ACTIVE
ACTIVE   -> CLOSED
INACTIVE -> CLOSED
```

`CLOSED` é terminal.

Mesmo status:

```text
409
```

---

## Coordenação CLIENT + ACCOUNT

Inativação:

```text
ACCOUNT ACTIVE -> INACTIVE
CLIENT  ACTIVE -> INACTIVE
```

Reativação:

```text
CLIENT  INACTIVE -> ACTIVE
ACCOUNT INACTIVE -> ACTIVE
```

Fechamento a partir de ACTIVE:

```text
ACCOUNT ACTIVE -> CLOSED
CLIENT  ACTIVE -> INACTIVE
```

Fechamento a partir de INACTIVE:

```text
ACCOUNT INACTIVE -> CLOSED
CLIENT permanece INACTIVE
```

Neste último caso:

```text
não criar CLIENT_STATUS_EVENT INACTIVE -> INACTIVE
```

---

## Regra financeira de fechamento

```text
CLOSED somente se
ACCOUNT.balance_cents == 0
```

R06 nunca zera saldo automaticamente.

---

## Locks

Ordem global:

```text
CLIENT
↓
ACCOUNT
```

A decisão é revalidada após os locks.

Todas as mudanças e eventos necessários:

```text
um único COMMIT
```

---

## Sucesso

```http
200 OK
```

```json
{
  "account_key": "...",
  "status": "CLOSED"
}
```

---

## Erros

```text
400 QIT000001 -> key/body/status/reason inválido
403 QIT000002 -> auth
404 ACC0001   -> ACCOUNT inexistente
409 ACC0003   -> transição de ACCOUNT inválida
409 ACC0004   -> saldo impede CLOSED
409 CLI0002   -> estado CLIENT/ACCOUNT incompatível
500 QIT000500 -> falha interna
```

Idempotência:

```text
não
```

---

# 12. R07 — POST /account/{account_key}/transaction

## Contrato

```text
POST /account/{account_key}/transaction
Auth: INTERNAL-TOKEN
Idempotency-Key: UUID obrigatória
```

Tipos:

```text
DEPOSIT
TRANSFER
```

Modelo:

```text
FINANCIAL_TRANSACTION
+
TRANSACTION_ENTRY
+
ACCOUNT.balance_cents
```

---

## DEPOSIT

Request:

```json
{
  "transaction_type": "DEPOSIT",
  "amount_cents": 10000
}
```

A conta do path recebe o crédito.

Pré-condições:

```text
ACCOUNT ACTIVE
amount_cents >= 1
```

Efeito:

```text
1 CREDIT / PRINCIPAL
```

Sem tarifa.

---

## TRANSFER

Request:

```json
{
  "transaction_type": "TRANSFER",
  "amount_cents": 10000,
  "target_account_key": "..."
}
```

Semântica:

```text
path account_key
-> source

target_account_key
-> target
```

As duas contas precisam estar:

```text
ACTIVE
```

Valor mínimo:

```text
amount_cents >= 1000
```

Self-transfer:

```text
409 TRX0002
```

---

## Tarifa

```text
source INDIVIDUAL:
rate_bps = 50
minimum_fee_cents = 50
maximum_fee_cents = 1000

source COMPANY:
rate_bps = 100
minimum_fee_cents = 100
maximum_fee_cents = 1500
```

O percentual é arredondado por `HALF_UP`, com piso e teto aplicados em
seguida. Somente o `client_type` da source define a política; o target não
influencia o pricing.

A source precisa ter:

```text
balance_cents >= amount_cents + fee_cents
```

A tarifa é calculada pelo servidor.

---

## Ordem congelada das entries

```text
1. source -> DEBIT  / PRINCIPAL
2. source -> DEBIT  / FEE
3. target -> CREDIT / PRINCIPAL
```

Invariante:

```text
último TRANSACTION_ENTRY.balance_after_cents
=
ACCOUNT.balance_cents
```

---

## Locks

DEPOSIT:

```text
lock ACCOUNT
```

TRANSFER:

```text
lock menor ACCOUNT.id
↓
lock maior ACCOUNT.id
```

Após os locks:

```text
revalidar status
reler saldo
```

---

## Idempotência

Identidade:

```text
request_control_key UUID UNIQUE GLOBAL
+
request_hash SHA-256
```

Canonicalização antes do hash:

```text
UUIDs -> forma canônica lowercase com hífens
amount_cents -> inteiro decimal canônico
transaction_type -> enum canônico
```

Hash DEPOSIT:

```text
DEPOSIT|source_account_key|amount_cents
```

Hash TRANSFER:

```text
TRANSFER|source_account_key|target_account_key|amount_cents
```

Não entram no hash:

```text
fee_cents
request_id
timestamp HTTP
JSON bruto
transaction_key
created_at
```

Semântica:

```text
key nova
-> executa

mesma key + mesmo hash
-> replay da transaction original
-> mesmo transaction_key
-> 201
-> sem novo efeito financeiro

mesma key + hash diferente
-> 409 TRX0003

falha antes do COMMIT
-> key não consumida
```

Replay idêntico continua válido mesmo se a conta mudar de estado depois da transação original.

---

## Atomicidade

Confirmam juntos:

```text
FINANCIAL_TRANSACTION
TRANSACTION_ENTRY(s)
ACCOUNT.balance_cents
```

Falha:

```text
ROLLBACK integral
```

---

## Sucesso DEPOSIT

```http
201 Created
```

```json
{
  "transaction_key": "...",
  "transaction_type": "DEPOSIT",
  "account_key": "...",
  "counterparty_account_key": null,
  "amount_cents": 10000,
  "fee_cents": 0,
  "created_at": "...Z"
}
```

## Sucesso TRANSFER

```json
{
  "transaction_key": "...",
  "transaction_type": "TRANSFER",
  "account_key": "<source_account_key>",
  "counterparty_account_key": "<target_account_key>",
  "amount_cents": 50000,
  "fee_cents": 250,
  "created_at": "...Z"
}
```

O exemplo usa source `INDIVIDUAL`; `50000 × 50 / 10000 = 250` cents.

---

## Erros

```text
400 QIT000001 -> keys/body/tipo/combinação inválida
403 QIT000002 -> auth
404 ACC0001   -> source ou target inexistente
409 ACC0005   -> conta envolvida não ACTIVE
409 TRX0002   -> self-transfer
409 TRX0003   -> conflito de idempotência
422 TRX0004   -> amount inválido, abaixo do mínimo ou fora do limite técnico
422 TRX0001   -> saldo insuficiente para amount + fee
500 QIT000500 -> falha interna
```

---

# 13. R08 — GET /account/{account_key}/transactions

## Contrato

```text
GET /account/{account_key}/transactions
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
extrato histórico paginado da ACCOUNT
```

Unidade:

```text
1 item
=
1 TRANSACTION_ENTRY
```

Consequência:

```text
DEPOSIT
-> 1 item

TRANSFER na source
-> PRINCIPAL + FEE

TRANSFER no target
-> PRINCIPAL
```

---

## Query params

```text
page
default = 1
min = 1

limit
default = 20
min = 1
max = 100

order_by
asc | desc
default = desc

date_from
opcional
YYYY-MM-DD

date_to
opcional
YYYY-MM-DD
```

Offset:

```text
(page - 1) * limit
```

---

## Timezone e datas

`date_from/date_to`:

```text
datas civis locais
interpretadas no CLIENT.timezone do dono da ACCOUNT
```

`date_from`:

```text
inclusivo
```

`date_to`:

```text
inclusivo para o caller
```

Internamente:

```text
[lower_bound, upper_bound)
```

com:

```text
upper_bound
=
início local do dia seguinte
```

e depois conversão para UTC.

Se:

```text
date_from > date_to
-> 422 TRX0005
```

Timestamp público do item:

```text
FINANCIAL_TRANSACTION.created_at
```

Resposta:

```text
UTC + Z
```

---

## Ordenação determinística

DESC:

```text
FINANCIAL_TRANSACTION.created_at DESC
FINANCIAL_TRANSACTION.id         DESC
TRANSACTION_ENTRY.id             ASC
```

ASC:

```text
FINANCIAL_TRANSACTION.created_at ASC
FINANCIAL_TRANSACTION.id         ASC
TRANSACTION_ENTRY.id             ASC
```

Dentro da mesma TRANSFER:

```text
PRINCIPAL
antes de
FEE
```

nos dois sentidos.

---

## Item

```json
{
  "transaction_key": "...",
  "transaction_type": "TRANSFER",
  "entry_type": "PRINCIPAL",
  "direction": "DEBIT",
  "amount_cents": 10000,
  "balance_after_cents": 90000,
  "counterparty_account_key": "...",
  "created_at": "...Z"
}
```

Counterparty:

```text
TRANSFER / PRINCIPAL / DEBIT
-> target account_key

TRANSFER / PRINCIPAL / CREDIT
-> source account_key

TRANSFER / FEE
-> null

DEPOSIT
-> null
```

---

## Paginação

Resposta:

```json
{
  "data": [],
  "pagination": {
    "current_page": 1,
    "next_page": null,
    "rows_per_page": 20
  }
}
```

Regra:

```text
rows_per_page = limit efetivo
```

Para detectar próxima página:

```text
buscar limit + 1
```

Não há obrigação de:

```text
COUNT(*)
total_items
total_pages
```

Página vazia ou além do fim:

```text
200 + []
```

Todos os status são legíveis:

```text
ACTIVE
INACTIVE
CLOSED
```

A fronteira de página pode separar `PRINCIPAL` e `FEE` da mesma transaction.

---

## Erros

```text
400 QIT000001 -> key/query/formato inválido
403 QIT000002 -> auth
404 ACC0001   -> ACCOUNT inexistente
422 TRX0005   -> date_from > date_to
500 QIT000500 -> falha interna
```

Idempotência:

```text
sim
```

Lock de escrita:

```text
nenhum
```

Índice físico:

```text
decidido na implementação
com query real + EXPLAIN
```

---

# 14. R09 — PATCH /client/{client_key}

## Contrato

```text
PATCH /client/{client_key}
Auth: INTERNAL-TOKEN
```

Finalidade:

```text
lifecycle direto do CLIENT
fora da análise R03
e fora da coordenação conjunta R06
```

Body:

```json
{
  "status": "PENDING",
  "reason": "Solicitação de nova análise cadastral"
}
```

`reason`:

```text
obrigatório
trim
não vazio
máximo 500
```

Evento:

```text
actor_type = INTERNAL
```

---

## Transições permitidas

```text
REJECTED -> PENDING
ACTIVE   -> INACTIVE
INACTIVE -> ACTIVE
```

Não realiza:

```text
PENDING -> ACTIVE
PENDING -> REJECTED
```

Essas pertencem à R03.

`REJECTED` não é destino válido da R09.

Mesmo status:

```text
409
```

---

## Reanálise

```text
REJECTED -> PENDING
```

Não existe:

```text
limite máximo de reanálises
reanalysis_count
```

Cada ciclo cria novo `CLIENT_STATUS_EVENT`.

---

## Regra quando existe ACCOUNT

Sem ACCOUNT:

```text
ACTIVE -> INACTIVE
✅ R09

INACTIVE -> ACTIVE
✅ R09
```

Com qualquer ACCOUNT existente:

```text
ACTIVE <-> INACTIVE
❌ R09
```

inclusive se a conta estiver:

```text
CLOSED
```

A coordenação deve passar por:

```text
R06 PATCH /account/{account_key}
```

---

## Concorrência

```text
SELECT CLIENT ... FOR UPDATE
```

Isso serializa:

```text
R09 vs R09
R09 vs R03
R09 vs R04
```

Estado + evento:

```text
mesmo COMMIT
```

---

## Sucesso

```http
200 OK
```

```json
{
  "client_key": "...",
  "status": "PENDING"
}
```

---

## Erros

```text
400 QIT000001 -> key/body/status/reason inválido
403 QIT000002 -> auth
404 CLI0001   -> CLIENT inexistente
409 CLI0002   -> transição incompatível
409 CLI0009   -> existe ACCOUNT; lifecycle deve passar pela R06
500 QIT000500 -> falha interna
```

Idempotência:

```text
não
```

---

# 15. R10 — GET /health_check

## Contrato

```text
GET /health_check
Auth: nenhuma
```

Finalidade:

```text
liveness
```

Não é:

```text
readiness
```

Não possui:

```text
path params
query params
body
```

---

## Dependências

R10 não acessa:

```text
PostgreSQL
CLIENT
ACCOUNT
FINANCIAL_TRANSACTION
TRANSACTION_ENTRY
connectors externos
repository de domínio
```

Se:

```text
processo HTTP vivo
+
PostgreSQL indisponível
```

R10 continua conceitualmente:

```text
204
```

---

## Sucesso

```http
204 No Content
```

Body:

```text
nenhum
```

Não exige `INTERNAL-TOKEN`, inclusive se um token inválido for enviado.

Não possui erros de domínio:

```text
400
403
404
409
422
```

Uma exceção interna inesperada ainda pode resultar em:

```text
500
```

Processo realmente morto:

```text
sem resposta HTTP válida
```

Idempotência:

```text
sim
```

Locks/escrita:

```text
nenhum
```

Readiness permanece fora do D0.

---

# 16. Matriz final de lifecycle — CLIENT

Estado inicial:

```text
NULL -> PENDING
R01
actor_type = SYSTEM
```

Análise:

```text
PENDING -> ACTIVE
R03 APPROVE
actor_type = INTERNAL

PENDING -> REJECTED
R03 REJECT
actor_type = INTERNAL
```

Reanálise:

```text
REJECTED -> PENDING
R09
actor_type = INTERNAL
sem limite máximo
```

Lifecycle direto sem ACCOUNT:

```text
ACTIVE -> INACTIVE
R09

INACTIVE -> ACTIVE
R09
```

Lifecycle com ACCOUNT:

```text
ACTIVE -> INACTIVE
R06

INACTIVE -> ACTIVE
R06
```

Fechamento de conta pode provocar:

```text
CLIENT ACTIVE -> INACTIVE
R06
```

---

# 17. Matriz final de lifecycle — ACCOUNT

Criação:

```text
NULL -> ACTIVE
R04
actor_type = SYSTEM
balance_cents = 0
```

Transições:

```text
ACTIVE   -> INACTIVE
INACTIVE -> ACTIVE
ACTIVE   -> CLOSED
INACTIVE -> CLOSED
```

Todas pela:

```text
R06
```

`CLOSED`:

```text
terminal
```

Pré-condição de fechamento:

```text
balance_cents == 0
```

---

# 18. Matriz final financeira

## DEPOSIT

```text
1 CREDIT / PRINCIPAL
fee = 0
```

## TRANSFER

```text
1 source DEBIT  / PRINCIPAL
2 source DEBIT  / FEE
3 target CREDIT / PRINCIPAL
```

Tarifa:

```text
200 cents
```

Saldo:

```text
nunca negativo
```

Idempotência:

```text
request_control_key UNIQUE GLOBAL
+
request_hash SHA-256
```

---

# 19. Regras de concorrência por rota

```text
R01
-> UNIQUE de email/cpf/cnpj

R02
-> leitura, sem FOR UPDATE

R03
-> chamada ao Analysis Provider sem lock aberto
-> CLIENT FOR UPDATE + revalidação PENDING

R04
-> CLIENT FOR UPDATE + UNIQUE ACCOUNT.client_id

R05
-> leitura, sem FOR UPDATE

R06
-> CLIENT FOR UPDATE
-> ACCOUNT FOR UPDATE

R07 DEPOSIT
-> ACCOUNT FOR UPDATE

R07 TRANSFER
-> duas ACCOUNTs por id crescente

R08
-> leitura, sem FOR UPDATE

R09
-> CLIENT FOR UPDATE

R10
-> sem lock
```

---

# 20. Regras de idempotência por rota

```text
R01 -> não
R02 -> sim, GET
R03 -> não
R04 -> não
R05 -> sim, GET
R06 -> não
R07 -> sim, Idempotency-Key + request_hash
R08 -> sim, GET
R09 -> não
R10 -> sim, GET/liveness
```

Importante:

```text
UNIQUE que impede duplicação
!=
replay idempotente
```

R07 é a única rota de escrita com mecanismo explícito de replay idempotente.

---

# 21. Escopo negativo consolidado

Fora do D0:

```text
multi-tenancy / PARTNER no ERD
múltiplas moedas
currency_code persistido
phone
address
UF
fornecedor comercial real de KYC/bureau
integração com Receita
full double-entry ledger
FEE_REVENUE account
EXTERNAL_CLEARING account
WITHDRAW
PIX
TED
BOLETO
REVERSAL
cursor/keyset pagination
readiness endpoint
múltiplas contas por cliente
reabertura de ACCOUNT CLOSED
```

---

# 22. Fonte de verdade e precedência

Após esta consolidação:

```text
1. ERD v1.1 FINAL
   -> fonte do modelo de dados e invariantes estruturais

2. Rotas v1.1 FINAL CONSOLIDADA
   -> fonte compacta dos contratos HTTP e regras por endpoint

3. arquivos individuais R01–R10, quando disponíveis
   -> material histórico de rastreabilidade; não substituem a versão consolidada

4. artefatos v1 antigos
   -> históricos; não prevalecem sobre v1.1
```

Nenhuma implementação deve reabrir silenciosamente decisão já congelada.

Mudança futura exige:

```text
novo requisito
ou
conflito objetivo identificado
```

e atualização explícita dos artefatos afetados.

---

# 23. Veredito final

```text
ERD v1.1
✅ FINAL / CONGELADO

R01
✅ FINAL

R02
✅ FINAL

R03
✅ FINAL

R04
✅ FINAL

R05
✅ FINAL

R06
✅ FINAL

R07
✅ FINAL

R08
✅ FINAL

R09
✅ FINAL

R10
✅ FINAL

Rotas v1.1 consolidadas
✅ AUDITADAS
✅ COMPATÍVEIS COM ERD v1.1
✅ PRONTAS PARA IMPLEMENTAÇÃO
✅ PRONTAS PARA DERIVAÇÃO DA RFC FINAL
```

---

# 24. Regra de congelamento

```text
Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md
✅ FINAL / AUDITADA / CONSOLIDADA / CONGELADA
```

Qualquer alteração posterior deverá informar:

```text
qual requisito mudou
qual rota é afetada
qual regra anterior deixa de valer
quais artefatos precisam ser atualizados
```

Não alterar silenciosamente contrato, status HTTP, lifecycle, lock, idempotência, modelo financeiro ou comportamento de erro.
