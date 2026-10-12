# R04 — Plano Completo de Testes e Implementação
## `POST /client/{client_key}/account` | BaaS Simplificado — Bootcamp QI Tech 2026

**Status:** PLANEJAMENTO DOCUMENTAL CONCLUÍDO — aguarda inspeção do repositório atual e aprovação humana antes do primeiro RED.  
**Rota:** R04 — abertura da única conta vitalícia de um CLIENT.  
**Responsabilidade:** desenvolvimento da R04 em paralelo à R03, atribuída ao outro integrante.  
**Branch sugerida:** `feature/r04-account-create`, criada a partir da `main` sincronizada.  
**Referência histórica de base:** `3fa24d2` (merge do PR #23, R02); confirmar o HEAD real antes de criar a branch.  
**Baseline conhecida:** 128 testes aprovados após R02; reproduzir no ambiente atual, nunca presumir o resultado.  
**Método:** TDD em pequenos blocos, RED → GREEN → REFACTOR, auditoria de diff antes de cada commit/push.

> **Natureza e autoridade.** Este arquivo é um plano de execução, **não altera o contrato bancário**. Foi elaborado com base nos arquivos `Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` (seção 9, R04, e seção 4), `Fluxos_v1_1_FINAL_BaaS_QITech.md` (F01, §1.4–1.5, e F02, §2.6), `ERD_v1_1_FINAL_BaaS_QITech.md` (§2.3) e `database/database.sql`, além do histórico e arquitetura já implementados para R01/R02. Os caminhos de código e nomes de testes **ainda não existentes** são sugestões e devem ser ajustados após inspeção. A evolução contratual **proposta** para a R03 não muda, por si, a R04.

---

## 1. Objetivo e fronteira da feature

A R04 abre a **primeira e única** conta bancária de um CLIENT cuja situação cadastral atual é `ACTIVE`. A operação gera uma `account_key` pública, persiste `ACCOUNT` com saldo zero e estado `ACTIVE`, registra o primeiro evento de status da conta e retorna HTTP `201`.

```text
R01 — POST /client
    CLIENT PENDING, com evento cadastral inicial
            │
            ├── R03 — análise, desenvolvida em paralelo
            │       PENDING -> ACTIVE (quando aprovada)
            │
            └── fixture controlada de testes da R04
                    PENDING -> ACTIVE com evento coerente
                            │
                            ▼
R04 — POST /client/{client_key}/account
    auth → UUID → lock CLIENT → status ACTIVE? → já tem conta?
         → cria ACCOUNT ACTIVE/saldo 0 + evento inicial → COMMIT
                            │
                            ▼
                        HTTP 201
```

**Dentro do escopo:** entrada HTTP, autenticação existente, validação da key, consulta e lock transacional, criação da conta, criação do evento, resposta pública, erros contratuais, testabilidade, rollback, concorrência, documentação e PR.

**Fora do escopo:** implementar R03/MockServer, R05 (consulta de conta), R06 (mudança de status de conta), R07/R08 (transações/extrato), R09 (lifecycle de CLIENT), criação de segunda conta, movimentação de dinheiro, edição do ERD/SQL físico e mecanismos de idempotência não contratados.

### 1.1 Fontes de verdade

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` — seção **9. R04**, catálogo de erros e convenções §4.
2. `docs/ERD_v1_1_FINAL_BaaS_QITech.md` e `database/database.sql` — estrutura, constraints, status e eventos.
3. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md` — **F01 §1.4, §1.5**, concorrência **F02 §2.6** e invariantes.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md` — decisões gerais e arquitetura.
5. Implementação atual de R01/R02, documentação operacional, testes e convenções reais.
6. Este plano e a issue da R04 — orientação de execução e rastreabilidade, **não** substituem o contrato.

**GATE documental:** se o contrato R04 for alterado formalmente para outra versão, comparar as versões e registrar o impacto antes de editar qualquer teste. Não transportar automaticamente as decisões do novo provider da R03 para a R04.

---

## 2. Contrato público da R04 — confirmado na Rotas v1.1

```http
POST /client/{client_key}/account
INTERNAL-TOKEN: <token interno>
```

**Body:** nenhum. Não receber dados de cliente, conta, status, saldo ou `account_key` fornecidos pelo caller. Antes de implementar, conferir como o FastAPI atual lida com ausência/presença indevida de body; não inventar schema vazio sem necessidade e não assumir uma regra de rejeição de body não especificada.

**Pré-condições cumulativas:**

- `client_key` é um UUID válido que identifica um CLIENT existente;
- `CLIENT.status` atual é `ACTIVE`;
- o CLIENT **nunca possuiu** uma ACCOUNT, seja `ACTIVE`, `INACTIVE` ou `CLOSED`.

**Sucesso:** HTTP **201 Created** e exatamente as três chaves públicas abaixo:

```json
{
  "account_key": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ACTIVE",
  "balance_cents": 0
}
```

O UUID exibido é apenas ilustrativo; gerar identificador novo na implementação. `balance_cents` deve ser inteiro, nunca `float` e nunca formato textual de moeda. Nenhum `id`, `client_id`, `status_id`, CPF/CNPJ, dados cadastrais ou histórico de eventos aparece na resposta.

**Semântica de repetição:** R04 **não é idempotente**. Depois de abrir uma conta, nova chamada para o mesmo CLIENT não cria outra nem retorna `201` de replay; retorna conflito contratual.

### 2.1 Persistência de sucesso

| Tabela | Estado depois de 201 | Regra |
|---|---|---|
| `client` | Permanece `ACTIVE` | R04 não altera o status do CLIENT nem cria evento cadastral |
| `account` | Uma linha para o `client_id` | `account_key` UUID, `status_id` do enumerador `ACTIVE`, `balance_cents=0` |
| `account_status_event` | Exatamente um evento inicial | `from_status_id=NULL`, `to_status_id=ACTIVE`, `actor_type=SYSTEM`, `reason=NULL` |

O `account.created_at`, `account.updated_at` e `account_status_event.created_at` usam os tipos `TIMESTAMPTZ` do SQL e instantes UTC conscientes de timezone (coerência com o padrão da R01). Nenhum timestamp faz parte dos três campos de resposta pública.

**Invariante vitalícia:** `account.client_id UNIQUE`; uma ACCOUNT `CLOSED` **continua bloqueando** abertura posterior.

### 2.2 Catálogo de erros

| Condição | HTTP | Código | Observação |
|---|---:|---|---|
| `client_key` inválido / parâmetro inválido | 400 | `QIT000001` | Não deixar FastAPI devolver `422` automático para UUID malformado |
| `INTERNAL-TOKEN` ausente ou inválido | 403 | `QIT000002` | Autenticação precede validação e lookup |
| UUID válido sem CLIENT | 404 | `CLI0001` | Reutilizar exceção existente da R02 |
| CLIENT não `ACTIVE` | 409 | `CLI0002` | Inclui `PENDING`, `REJECTED`, `INACTIVE` |
| CLIENT já possuiu ACCOUNT | 409 | `ACC0002` | Inclui conta encerrada |
| Falha interna inesperada | 500 | `QIT000500` | Sem expor SQL/traceback ao caller |

Corpo público dos erros (convenção §4.3):

```json
{
  "title": "string",
  "description": "string",
  "translation": "string",
  "code": "string"
}
```

Nos testes, validar **HTTP**, código **exato**, conjunto **exato** de quatro chaves, tipos e ausência de mensagens SQL.

**Precedência conhecida:** middleware de autenticação antes de resource e consulta; portanto token inválido + UUID inexistente/malformado → `403 QIT000002`. Dentro da rota, F01 ordena CLIENT inexistente → estado ACTIVE → existência de ACCOUNT. O cenário misto `CLIENT não ACTIVE + ACCOUNT preexistente` deve respeitar essa ordem, salvo decisão formal posterior.

**Não criar novos códigos** nem usar `ACC0001` (conta inexistente) para CLIENT inexistente.

---

## 3. Dados físicos e invariantes do PostgreSQL

As tabelas já existem em `database/database.sql`; **não há migration de schema prevista**.

```text
CLIENT
  id BIGINT interno
  client_key UUID UNIQUE público
  status_id FK -> CLIENT_STATUS

ACCOUNT
  id BIGINT interno
  account_key UUID NOT NULL UNIQUE
  client_id BIGINT NOT NULL UNIQUE -> CLIENT.id
  status_id BIGINT NOT NULL -> ACCOUNT_STATUS.id
  balance_cents BIGINT NOT NULL DEFAULT 0 CHECK >= 0
  created_at TIMESTAMPTZ NOT NULL
  updated_at TIMESTAMPTZ NOT NULL

ACCOUNT_STATUS
  ACTIVE | INACTIVE | CLOSED

ACCOUNT_STATUS_EVENT
  id BIGINT interno
  account_id BIGINT NOT NULL -> ACCOUNT.id
  from_status_id BIGINT NULL -> ACCOUNT_STATUS.id
  to_status_id BIGINT NOT NULL -> ACCOUNT_STATUS.id
  actor_type SYSTEM | INTERNAL
  reason VARCHAR(500) NULL
  created_at TIMESTAMPTZ NOT NULL
```

Invariantes obrigatórios:

1. CLIENT precisa estar `ACTIVE` **no instante da criação**, sob o lock pertinente.
2. A conta só nasce `ACTIVE` e com `balance_cents=0`.
3. Uma única conta por CLIENT **durante toda a vida**.
4. Um e somente um evento inicial para a conta criada.
5. Criação de conta e evento são **atômicos**: ambos persistem ou nenhum persiste.
6. Não alterar historicamente a decisão da R03 nem inventar outra análise.
7. IDs de status devem ser consultados por `enumerator`, nunca codificados numericamente.
8. Nenhum lançamento financeiro ocorre na abertura de conta.

---

## 4. Arquitetura mínima proposta

```text
FastAPI / src/app.py
   ↓
middlewares já existentes (token, sessão, contexto, logging)
   ↓
Resource de ACCOUNT/R04 [entrada, retorno 201]
   ↓
Controller de abertura de conta [precondições e transação]
   ↓
Repository(s) [SELECT FOR UPDATE, SELECT conta, INSERT conta/evento]
   ↓
PostgreSQL [UNIQUE(account.client_id)]
```

**A decisão de nomes/arquivos será feita após inspeção de `src/`.** O endpoint é aninhado sob `/client/{client_key}`, mas isso não exige colocar toda a lógica de conta no `ClientController`. Comparar alternativas:

- estender `ClientResource`/`ClientController` com delegação pontual a um `AccountController`;
- criar `AccountResource`/`AccountController` para R04;
- reutilizar `ClientRepository` para lookup/lock, mas separar operações de ACCOUNT quando melhorar coesão;
- reutilizar o mesmo contexto/sessão para **toda** a transação; não abrir sessões independentes no meio do fluxo.

### 4.1 Responsabilidades

| Camada | Faz | Não faz |
|---|---|---|
| Resource | recebe `client_key`, delega, retorna JSON 201 | SQL, commit, transição de domínio, autenticação duplicada |
| Controller | valida key/estado, orquestra leitura sob lock, cria conta/evento com mesma transação e lida com erros de domínio | SQL bruto espalhado, lógica de MockServer/R03 |
| Repository | consulta, `FOR UPDATE`, insere/`flush`, busca status/conta por FK | HTTP, decisão de status, commit próprio |
| Models | mapeiam ACCOUNT/ACCOUNT_STATUS/ACCOUNT_STATUS_EVENT conforme SQL | introduzir tabela ou regra fora do contrato |
| Errors | `CLI0001`, `CLI0002`, `ACC0002` e infraestrutura QIException | expor exception SQL bruta |
| Middleware | autenticação e lifecycle da sessão, já implementados | autenticação reimplementada dentro da R04 |

### 4.2 Itens a inspecionar no repositório atual

- `src/app.py`, `src/resources/`, `src/controllers/`, `src/repositories/` e seus `__init__.py`.
- `src/models/`: verificar se `Account`, `AccountStatus`, `AccountStatusEvent` já possuem ORM; **não presumir que existam** após R02.
- `src/database.py`, `src/middlewares/session_manager.py`, `src/controllers/base_controller.py`: dono do commit, rollback e contexto de sessão.
- `src/errors/` e código `ClientNotFound` da R02: classes disponíveis e catálogo único.
- `tests/utils/`, `tests/integration/client/`: geradores de dados, helper HTTP e fixtures.
- `docker-compose.yml`, `compose.test.yml`, `.env.example`: identidade das conexões de teste.

### 4.3 Decisão inicial sobre DTO

A resposta da R04 tem **apenas três campos**. Partir da solução simples já utilizada nas R01/R02 (dict ou serialização mínima), e reavaliar somente se padrões reais do repositório/contrato exigirem DTO. Não criar camada nova como premissa obrigatória.

---

## 5. Fluxo transacional e concorrência

### 5.1 Happy path — contrato F01

```text
1. Autenticar INTERNAL-TOKEN no middleware (antes de abrir a operação).
2. Validar client_key (UUID) sem depender de erro SQL.
3. Usar UMA sessão de banco para todas as operações da R04.
4. Iniciar transação no momento coerente com o lifecycle real.
5. SELECT CLIENT ... FOR UPDATE pelo UUID.
6. Se não existe → 404 CLI0001 (sem escrita).
7. Se status != ACTIVE → 409 CLI0002 (sem escrita).
8. Consultar ACCOUNT existente para o client_id, sem filtrar status.
9. Se existe → 409 ACC0002 (sem escrita).
10. Resolver ACCOUNT_STATUS enumerator ACTIVE.
11. Gerar account_key novo e timestamps UTC aware.
12. INSERT ACCOUNT ACTIVE, balance_cents = 0.
13. flush para obter ACCOUNT.id sem commit.
14. INSERT ACCOUNT_STATUS_EVENT NULL → ACTIVE, SYSTEM, reason NULL.
15. COMMIT ÚNICO; em erro, ROLLBACK de tudo.
16. Retornar 201 com account_key, status, balance_cents.
```

**Atenção à precedência do ORM:** `SELECT FOR UPDATE` precisa efetivamente atingir a linha `client`, sem ser descaracterizado por eager joins/relationship. Se `client.status` estiver em cache da identidade ORM, confirmar estratégia de refresh sob lock (`populate_existing`, refresh explícito ou query adequada) para validar o estado **atual**, não valor stale.

**Atenção ao lifecycle real:** controller/repository não podem fazer commit disperso; conferir a sessão criada pelo middleware/contexto antes de implementar. Exceções devem permitir rollback apropriado antes do retorno HTTP. Não retornar `201` antes da confirmação do commit.

### 5.2 Duas aberturas simultâneas para o mesmo CLIENT

```text
Request A                         Request B
---------                         ---------
lock CLIENT ACTIVE                tenta lock; aguarda
não há ACCOUNT                    —
INSERT ACCOUNT + EVENT            —
COMMIT                            obtém lock
                                  vê ACCOUNT existente
201 account_key                   409 ACC0002
```

**Proteções complementares:**

- serialização por `CLIENT FOR UPDATE`;
- reconsulta de ACCOUNT **depois** de adquirir o lock;
- `UNIQUE (account.client_id)` no PostgreSQL como barreira estrutural final;
- se ocorrer `IntegrityError` por colisão comprovadamente atribuível a `ACCOUNT.client_id`, rollback e tradução para `409 ACC0002` de modo seguro; **não** capturar toda `IntegrityError` como duplicidade;
- verificar o comportamento de transação/visibilidade do isolamento padrão (tipicamente READ COMMITTED) sem pressupor resultado de sessões com isolamento diferente.

### 5.3 Concorrência futura R04 × R09 / R03

- R04 × R09: se a inativação do CLIENT vencer primeiro, R04 deve reler `INACTIVE` e retornar `409 CLI0002`; se R04 criar conta primeiro, R09 deve respeitar a existência de ACCOUNT, conforme F02.
- R04 × R03: R04 só abre conta se encontrar `ACTIVE` sob lock. A implementação da análise pelo Moha deve usar a mesma estratégia de proteção do CLIENT, mas R04 **não depende de chamada ao provider**.
- Não implementar R09 nem R03 para simular este conflito. Registrar o caso para teste cross-route quando essas rotas forem integradas.
- Se outras operações futuramente travarem CLIENT e ACCOUNT, revisar a **ordem global de locks** documentada em F02 antes de acrescentar locks novos.

### 5.4 Atomicidade sob falha

Se qualquer etapa após o INSERT ACCOUNT falhar antes do commit:

```text
ACCOUNT inserida provisoriamente
   + falha ao inserir ACCOUNT_STATUS_EVENT
             ↓
           ROLLBACK
             ↓
nenhuma ACCOUNT persistida, nenhum evento persistido
```

A prova de rollback deve ser feita com mecanismo **isolado, determinístico e seguro** (teste de unidade/integrado com falha controlada ou infraestrutura de teste própria), sem triggers artificiais persistentes, corrupção de dados reais, alteração do schema principal ou exceção genérica introduzida no código de produção. Não criar endpoint para injetar falhas.

---

## 6. Testes: isolamento, dados e fixture ACTIVE sem R03

### 6.1 Ambientes de banco — risco prioritário

O histórico do projeto usa:

| Uso | Ambiente histórico | Proibição |
|---|---|---|
| API Docker de desenvolvimento | `bootcamp`, porta host 5432 | nunca resetar `public` aqui |
| Testes descartáveis de schema | `bootcamp_test`, porta host 5433 | nunca usar sua URL como se fosse a API |

**O ambiente atual deve ser comprovado**, inclusive configuração da API real e das fixtures. O host Docker interno difere do host da máquina. Antes de qualquer fixture de escrita, verificar hostname, porta, nome do banco, identidade real da instância e ausência de conexão remota/produção. Não exibir credenciais nos relatórios.

O pytest de R01/R02 envia HTTP real à API, que persiste registros no banco de desenvolvimento; esses dados continuam existindo. A suíte de schema usa banco descartável separado e pode recriar `public` **somente nele**.

### 6.2 Criação de CLIENT por teste

O teste não deve importar CLIENTs existentes, usar CPF/email fixo nem depender de IDs numéricos.

1. `POST /client` da R01 com token válido e dados únicos.
2. Confirmar `201`, extrair UUID público.
3. Confirmar fisicamente, por conexão segura, que CLIENT pertence ao teste e nasceu `PENDING`.
4. Confirmar evento inicial `NULL → PENDING`, `SYSTEM`, `reason=NULL`.
5. Para cenários ACTIVE, preparar `PENDING → ACTIVE` de forma controlada em **uma transação**, inserindo `CLIENT_STATUS_EVENT` `INTERNAL` e atualizando `CLIENT.updated_at`, sem duplicar evento inicial.
6. Limitar UPDATE a `id`, UUID e `status_id` esperado; exigir `rowcount == 1`.
7. Confirmar ausência de ACCOUNT antes do teste de sucesso.
8. Em caso de verificação falha, rollback; não tocar em registro preexistente.

**Referência:** `api_database_engine` e `_prepare_client_status` do Bloco C da R02. Antes de reutilizar, revisar a implementação real e sua segurança. Evitar importação de helpers privados diretamente de outro módulo de testes; considerar extrair helper compartilhado em `tests/utils/` **se** houver ganho demonstrado e testes de regressão, ou usar uma fixture R04 local pequena e explícita.

### 6.3 Preparação de outros estados

- `PENDING`: CLIENT recém-criado pela R01; não precisa SQL de transição.
- `REJECTED`: fixture controlada `PENDING → REJECTED`, justificativa válida e evento correto.
- `INACTIVE`: fixture controlada `PENDING → ACTIVE → INACTIVE` **sem ACCOUNT** e com histórico compatível.
- `ACTIVE`: fixture controlada `PENDING → ACTIVE` sem ACCOUNT.

Nenhuma dessas preparações exige implementar R03 ou R09. O nome da fixture e suas queries devem ser aprovados em auditoria antes de qualquer escrita no banco local.

### 6.4 Evidências de persistência

Após o HTTP 201:

- `SELECT` por `account_key` e por `client_id` comprova **uma única ACCOUNT**;
- `ACCOUNT.client_id` corresponde ao CLIENT recém-criado;
- `status_id` aponta a `ACCOUNT_STATUS.enumerator=ACTIVE`;
- `balance_cents=0` como inteiro;
- timestamps aware/UTC, com `created_at` e `updated_at` coerentes;
- **um evento** `NULL → ACTIVE`, `SYSTEM`, `reason=NULL`;
- `CLIENT.status_id`, `CLIENT.updated_at` e seus eventos não foram alterados **pela R04**;
- não há `FINANCIAL_TRANSACTION` ou `TRANSACTION_ENTRY` criados pela abertura.

Separar claramente a fixture **que prepara** o CLIENT da ação **sob teste** que abre a ACCOUNT, para não atribuir escrita da fixture à R04.

### 6.5 Regras gerais dos testes

- Preferir HTTP real via helper existente e PostgreSQL real para integração.
- Preservar independência de ordem e unicidade de email/CPF/CNPJ/UUID.
- Asserts de conjunto **exato** das três chaves públicas no sucesso.
- Não confiar somente no HTTP 201: verificar persistência física nos blocos pertinentes.
- Proteger banco de testes de schema contra apontamento acidental à API.
- Não usar `sleep` como sincronizador de concorrência determinística.
- Reset destrutivo (`DROP SCHEMA`, `TRUNCATE`, `DELETE` em lote) proibido no banco API.
- Não criar MockServer/Connector para a R04.

---

## 7. Matriz de rastreabilidade e cobertura planejada

| ID | Cenário | HTTP/código | Banco/efeito | Momento |
|---|---|---|---|---|
| A1 | CLIENT PF ACTIVE sem ACCOUNT | `201` | nova conta+evento | A |
| B1 | Corpo exato da resposta | `201` | `account_key` válido, `ACTIVE`, saldo `0` | B |
| B2 | CLIENT PJ ACTIVE sem ACCOUNT | `201` | mesma regra PF | B |
| C1 | Persistência da conta | `201` | FK, status, saldo, timestamps | C |
| C2 | Evento inicial | `201` | NULL→ACTIVE/SYSTEM/reason NULL | C |
| C3 | Ausência de efeitos colaterais indevidos | `201` | CLIENT não modificado, sem transações financeiras | C |
| D1 | UUID malformado + token válido | `400 QIT000001` | sem ACCOUNT | D |
| D2 | UUID válido inexistente + token válido | `404 CLI0001` | sem ACCOUNT | D |
| D3 | Token ausente | `403 QIT000002` | sem consulta de domínio/conta | D |
| D4 | Token inválido | `403 QIT000002` | sem consulta de domínio/conta | D |
| D5 | Token inválido + UUID malformado/inexistente | `403 QIT000002` | autenticação precede lookup | D |
| D6 | CLIENT PENDING | `409 CLI0002` | sem conta/evento | D |
| D7 | CLIENT REJECTED | `409 CLI0002` | sem conta/evento | D |
| D8 | CLIENT INACTIVE | `409 CLI0002` | sem conta/evento | D |
| D9 | Segunda chamada após sucesso | `409 ACC0002` | continua uma única conta/evento | D |
| D10 | ACCOUNT existente em estado diferente, inclusive CLOSED | `409 ACC0002` | regra vitalícia | D / F, quando fixture segura |
| E1 | Duas aberturas concorrentes do mesmo CLIENT | um `201`, um `409 ACC0002` | única conta, único evento | E |
| E2 | Falha entre criação de ACCOUNT e EVENT | erro controlado, sem parcial | rollback integral | E |
| F1 | R01 e R02 continuam íntegros | suite verde | não há regressão | F |
| F2 | R04 × R03/R09 após merge futuro | conforme Fluxos | integridade de status e account | integração futura |

**Classificação honesta:** D10 e F2 não autorizam corromper dados ou implementar outras rotas. Se a prova dinâmica exigir infraestrutura inexistente, indicar limite de evidência e sustentar o comportamento possível via SQL/inspeção até haver preparação segura.

---

## 8. Execução em blocos TDD — sem antecipar escopo

### BLOCO 0 — Inspeção e planejamento humano

**Objetivo:** confirmar branch, baseline, código real, separação das conexões e viabilidade da fixture antes de tocar no produto.

1. Conferir `main` e criar `feature/r04-account-create` a partir dela, após garantir working tree limpa.
2. Reproduzir baseline, esperada historicamente em **128 passed**.
3. Ler os contratos de R04/F01/F02 e este plano.
4. Verificar ORM de ACCOUNT e EVENT, repository, ciclo transacional e erros existentes.
5. Propor nomes/arquivos mínimos e matriz de testes; identificar riscos de conflitos com branch R03.
6. Preparar a estratégia de fixture ACTIVE, sem executá-la ainda.
7. Elaborar relatório de viabilidade e **parar para aprovação humana**.

**Critério de saída:** viabilidade comprovada, divergências listadas, sem arquivos de produção alterados.

### BLOCO A — Primeiro RED e happy path mínimo

**Objetivo:** exercitar R04 por HTTP com CLIENT PF ACTIVE preparado de modo seguro.

1. Configurar ambiente de teste e preparar CLIENT novo ACTIVE por fixture já auditada.
2. Escrever `test_create_account_for_active_individual_returns_201`.
3. Executar isoladamente e registrar **RED real** (provavelmente 404 rota inexistente, mas não presumir).
4. Implementar somente registro HTTP, Resource, mínimo Controller/Repository/ORM necessário para obter **201** sem violar a transação.
5. Executar teste isolado e regressão curta; conferir diff antes de commit.

**Não antecipar:** PJ, bateria completa de erros, testes de concorrência e rollback instrumentado. Embora o teste inicial seja pequeno, **não é permitido obter HTTP 201 com conta fictícia ou sem persistência correta**: o GREEN deve cumprir o contrato do cenário.

### BLOCO B — Resposta pública e especialização independente

1. Testar três chaves exatas: `account_key`, `status`, `balance_cents`.
2. Confirmar UUID válido e diferente do client_key, string `ACTIVE` e inteiro zero.
3. Adicionar cenário COMPANY ACTIVE.
4. Demonstrar que abertura não depende de CPF/CNPJ no contrato externo.
5. Não criar DTO sem evidência de necessidade; manter código simples.

### BLOCO C — Persistência física e evento inicial

1. Verificar conta persistida por `client_id`/`account_key`.
2. Status via enumerador `ACCOUNT_STATUS.ACTIVE`; saldo 0.
3. Evento `NULL → ACTIVE`, `SYSTEM`, `reason=NULL` exatamente uma vez.
4. Verificar timestamps e ausência de atualização cadastral atribuível à R04.
5. Verificar que não há movimentação financeira na criação.
6. Confirmar transação única, sem commit no Repository.

### BLOCO D — Erros, conflitos e precedência

1. UUID inválido → `400 QIT000001`.
2. CLIENT não existe → `404 CLI0001`.
3. Token ausente/inválido → `403 QIT000002`.
4. Autenticação precede URI malformada/lookup.
5. CLIENT PENDING/REJECTED/INACTIVE → `409 CLI0002`.
6. ACCOUNT preexistente para CLIENT ACTIVE → `409 ACC0002`.
7. Segunda chamada após sucesso → `409 ACC0002` com mesma conta física.
8. Conta anteriormente CLOSED bloqueia nova conta (prova segura, se viável; caso contrário validar estruturalmente e registrar limite).
9. Validar corpo padrão de erro e ausência de writes nos erros.

### BLOCO E — Concorrência, rollback e integridade

1. Exercitar duas requests concorrentes sobre mesmo CLIENT, preferencialmente com sincronização explícita ou mecanismo de teste determinístico, **sem depender de sleeps**.
2. Provar exatamente um `201`, um `409 ACC0002`, uma ACCOUNT e um evento.
3. Revisar `SELECT FOR UPDATE` e refresh/visibilidade da sessão ORM.
4. Provar a proteção `UNIQUE (account.client_id)` como última defesa, verificando tradução seletiva da violação.
5. Injetar falha controlada após INSERT ACCOUNT e antes de EVENT/commit, sem alterar código de produção permanentemente.
6. Confirmar rollback: nenhuma ACCOUNT/evento parcial para CLIENT do cenário.
7. Reexecutar regressão R01/R02 e suite completa.

### BLOCO F — Auditoria final / Definition of Done

1. Auditoria independente requisito a requisito com arquivo/linha/teste/evidência.
2. Comprovar response 201, erros 400/403/404/409/500, fluxos e precedência.
3. Auditar SQL físico, ORM, `FOR UPDATE`, unicidade vitalícia e commit único.
4. Auditar segurança das fixtures e isolamento das instâncias PostgreSQL.
5. Auditar snapshot público sem campos internos e ausência de writes indevidos.
6. Rodar suites R04, R01, R02, integração CLIENT e full suite.
7. Decisão arquitetural explícita sobre DTO e separação de account resources.
8. Atualizar documentação operacional **somente depois** da aprovação técnica; preservar contratos congelados.
9. Verificar branch/commit/working tree/diff e preparar PR da R04.
10. Encerrar apenas após revisão humana, checks disponíveis, revisão do PR e merge.

**Regra universal de cada bloco:** relatório TDD → diff real → revisão humana → autorização para commit e push. Não implementar bloco seguinte automaticamente.

---

## 9. Roteiro Git e colaboração com a R03

### 9.1 Criar a branch da R04

Partindo de working tree limpa:

```powershell
git switch main
git status
git fetch origin
git pull --ff-only origin main
python -m pytest -q
git switch -c feature/r04-account-create
git branch --show-current
git log -1 --oneline
git status
```

Se existir branch R04 local/remota anterior, **não recriar ou sobrescrever**: inspecionar histórico e reconciliar.

A branch R04 sai da `main` que já contém R01/R02. **Não usar** `feature/r03-client-analysis` como branch-base da R04.

### 9.2 Zonas de conflito prováveis

| Arquivos | Medida |
|---|---|
| `src/app.py` | Adicionar registro de rota de modo mínimo; após integração de R03, revisar diffs de ambos |
| `src/resources/__init__.py` | Acrescentar export sem sobrescrever export do Moha |
| `src/controllers/__init__.py` | Mesmo cuidado |
| `src/repositories/__init__.py` | Mesmo cuidado |
| `src/models/__init__.py` | Importar Account/Status/Event preservando modelos atuais |
| `src/errors/client_errors.py`, `src/errors/__init__.py` | Evitar conflitos de catálogo/códigos e duplicação de classes |
| `src/repositories/client_repository.py` | Preferir mudanças pequenas; evitar refactor global durante trabalho paralelo |
| `docker-compose.yml` e `.env.example` | A R04 não precisa do MockServer; não incorporar mudanças da R03 antecipadamente |

Se a R03 entrar na `main` antes da R04: atualizar a branch de forma consciente, inspecionar conflitos, rodar a R04 e a suíte inteira. Não aceitar automaticamente `ours`/`theirs` em arquivos compartilhados.

Se a R04 entrar primeiro: não alterar o protocolo planejado da R03; documentar apenas eventual teste ponta a ponta posterior `R01 → R03 → R04`.

### 9.3 Disciplina de commits

- Cada bloco revisado tem commit com escopo claro, por exemplo `feat(r04): create active client account` / `test(r04): validate account lifecycle constraints`.
- Não executar `git add .` sem necessidade; preferir paths explícitos aprovados.
- Sempre `git diff --check`, `git diff --cached --check`, `git status` e suíte correspondente.
- Merge/PR apenas após Bloco F e avaliação do efeito das branches paralelas.

---

## 10. Definition of Done da R04

- [ ] Contrato R04 conferido com Rotas v1.1/F01/ERD/SQL atuais; divergências resolvidas.
- [ ] `POST /client/{client_key}/account` registrado com autenticação existente.
- [ ] Sem body exigido; nenhum campo de entrada artificial adicionado.
- [ ] CLIENT PF `ACTIVE` sem ACCOUNT recebe HTTP `201`.
- [ ] CLIENT PJ `ACTIVE` sem ACCOUNT recebe HTTP `201`.
- [ ] Resposta tem **exatamente** `account_key`, `status`, `balance_cents`.
- [ ] UUID público válido, status `ACTIVE`, saldo inteiro `0`.
- [ ] ACCOUNT persistida com FK CLIENT correta e status ACTIVE.
- [ ] ACCOUNT_STATUS_EVENT inicial único (`NULL → ACTIVE`, `SYSTEM`, reason NULL).
- [ ] ACCOUNT e evento persistidos atomicamente; um commit.
- [ ] R04 não altera status/eventos do CLIENT nem cria movimentação financeira.
- [ ] R04 bloqueia CLIENT com `FOR UPDATE`, revalida status e existência de conta.
- [ ] `ACCOUNT.client_id UNIQUE` preservado; nenhuma segunda conta mesmo se CLOSED.
- [ ] Segunda chamada dá `409 ACC0002`, sem segunda conta/evento.
- [ ] PENDING/REJECTED/INACTIVE retornam `409 CLI0002`.
- [ ] UUID malformado retorna `400 QIT000001`.
- [ ] UUID inexistente retorna `404 CLI0001`.
- [ ] Token ausente/inválido retorna `403 QIT000002` antes do lookup.
- [ ] Falha interna não expõe detalhes SQL (`500 QIT000500`).
- [ ] Teste concorrente comprova um sucesso, um conflito e uma única persistência.
- [ ] Teste seguro demonstra rollback integral sob falha de evento.
- [ ] Fixtures ACTIVE/REJECTED/INACTIVE independem da R03/MockServer.
- [ ] Banco principal da API protegido de operações destrutivas da suíte.
- [ ] R01 e R02 não regrediram; full suite GREEN e contagem real registrada.
- [ ] Documentação operacional e matriz de rastreabilidade revisadas.
- [ ] Auditoria final independente concluída, incluindo decisão sobre DTO.
- [ ] Diff revisado, commits/push autorizados humanamente, PR revisado e integrado à `main`.

---

## 11. Formato de relatório obrigatório para os ciclos Codex

Em cada bloco, solicitar:

1. **Estado inicial:** branch, HEAD, working tree, baseline reproduzida.
2. **Contrato:** trechos exatos dos documentos usados; eventuais divergências.
3. **TDD:** teste novo, RED verdadeiro com saída, alterações mínimas e GREEN real.
4. **Persistência:** tabelas tocadas, transação/locks, fixtures e efeitos colaterais.
5. **Diff:** paths alterados, status, diff check, arquivos untracked.
6. **Testes:** comando e contagem reais (R04, R01/R02, suíte integral conforme escopo).
7. **Achados:** bloqueantes e melhorias não bloqueantes, com severidade.
8. **Veredito:** GREEN / GREEN COM PENDÊNCIA / BLOQUEADO e recomendação do próximo bloco.
9. **Confirmação:** nenhum commit/push/merge/rebase sem autorização humana.

**Não declarar comportamento comprovado via HTTP quando a evidência for só inspeção de código. Não declarar rollback ou concorrência comprovados sem execução apropriada.**

---

## 12. Primeiro comando para o Codex (não é autorização para implementar)

Depois de colocar **este arquivo** em `docs/R04_Plano_Completo_Testes_e_Implementacao.md` na branch R04, a primeira missão do Codex deve ser:

> Leia este plano e as fontes de verdade da R04. Confirme a branch, HEAD e baseline; inspecione ORM, Resource, Controller, Repository, middleware/sessão, errors e a fixture R02. Compare a estratégia com o projeto real, produza a matriz de arquivos e riscos para a R04 e a proposta do primeiro teste RED. **Não altere arquivos; não crie fixtures nem execute SQL de escrita; não implemente R04; não faça commit/push.** Pare após o diagnóstico para auditoria humana.

**Critério de partida:** a R04 só entra no Bloco A após confirmação do Bloco 0 e da segurança da preparação de CLIENT ACTIVE.
