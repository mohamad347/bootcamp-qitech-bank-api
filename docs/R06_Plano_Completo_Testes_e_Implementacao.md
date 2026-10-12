# R06 — Plano Completo de Testes e Implementação
## `PATCH /account/{account_key}` | BaaS Simplificado — Bootcamp QI Tech 2026

**Projeto:** `bootcamp-qitech-bank-api`
**Rota:** R06 — atualização do lifecycle de ACCOUNT e coordenação de CLIENT
**Documento canônico:** `docs/R06_Plano_Completo_Testes_e_Implementacao.md`
**Branch:** `feature/r06-account-patch` (criada a partir de `main` sincronizada após R05)
**Baseline de regressão:** 175 testes aprovados na `main` após integração da R05 (execução local reportada: `175 passed in 36.07s`); medir novamente antes da R06
**Status:** PLANEJADO — não presumir blocos executados nem sucesso de testes
**Metodologia:** INSPEÇÃO → TDD RED → GREEN → INTEGRIDADE → CONCORRÊNCIA → REFACTOR/AUDITORIA → REGRESSÃO → RELATÓRIO

> **Documento-mestre, não novo contrato.** Este plano é um roteiro técnico executável e verificável para o Codex. A especificação oficial prevalece: `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` (§11 e §4), `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md` (F02 §2.7–2.16), `docs/ERD_v1_1_FINAL_BaaS_QITech.md`, `database/database.sql` e `docs/RFC_v1_BaaS_Simplificado_QITech.md`. Não criar arquivos `00.md` alternativos nem `docs/R06/`. Ao executar, atualizar este documento com evidências reais, preservando o texto do contrato.

---

## 0. Escopo, dependências e gates

### 0.1 Objetivo e fronteiras

Implementar endpoint PATCH autenticado que recebe `account_key`, `status` de destino e `reason` obrigatório, executa **uma transição permitida de ACCOUNT**, coordena o estado de seu CLIENT quando aplicável, persiste **todos os eventos reais** e confirma todas as escritas em **um único commit atômico**. Falhas devem impedir alterações parciais.

**Incluído:** validação do HTTP/schema, DTO de entrada (e projeção de resposta conforme padrão), domínio lifecycle, erros `ACC0003`, `ACC0004`, `CLI0002`, eventos de ACCOUNT e CLIENT, locks pessimistas em ordem, concorrência, rollback, regressão e documentação.

**Excluído:** alterar `balance_cents`, criar/debitar/creditar/estornar transações, atualizar titular, reabrir CLOSED, implementar R07/R08/R09, modificar migrations/schema sem justificativa, refatorar globalmente R01–R05, criar idempotência, criar código ou regra não definida no contrato.

### 0.2 Ordem das fontes da verdade

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md`: §11 R06, §4 convenções, §5 catálogo de erros.
2. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md`: F02, especialmente §2.5–2.16 (R06 e coordenação com R09).
3. `docs/ERD_v1_1_FINAL_BaaS_QITech.md` e `database/database.sql`: tabelas, tipos, FK, campos, constraints, índices.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md`: arquitetura e padrões do desafio.
5. Estado **real** da branch atual: R02/R03 (eventos CLIENT), R04 (ACCOUNT/events/locks) e R05 (GET/DTO), padrões de auth/erro/testes; **inspecionar**, não presumir APIs internas.
6. Este plano: ordem dos trabalhos, TDD, cenários, critérios de aceite e evidências.

**GATE 0:** caso código, documentação ou semântica financeira estejam divergentes, descrever precisamente a divergência e resolvê-la **conforme a fonte de maior autoridade**, sem mudar contrato congelado. Parar apenas por contradição material que impossibilite implementação segura.

### 0.3 Preparação da branch e ambiente

- Branch esperada: `feature/r06-account-patch`; `main` deve incluir R05 e o PR de correção R04.
- Estado esperado antes do Codex: `git status` sem alterações alheias, planejamento R06 adicionado como arquivo local ainda não commitado.
- Ambiente conhecido: FastAPI `127.0.0.1:3000`, PostgreSQL principal `bootcamp` host `5432`, testes de schema `bootcamp_test` host `5433`, MockServer `127.0.0.1:1080`.
- Endpoints de testes podem escrever **somente registros criados/controlados para os próprios testes** na base principal conforme fixtures existentes. Nunca apagar/resetar/truncar tabelas do `bootcamp`. Operações destrutivas de schema apenas no banco de testes e com guardas de ambiente.
- Confirmar `TEST_DATABASE_URL`, `SERVER_LOCALHOST`, `MOCKSERVER_URL` e compose/test isolation seguindo convenção local. Confirmar real ambiente antes de chamar `pytest`.
- Se `uvicorn --reload` ficar preso ao alternar branch, diagnosticar via `docker compose logs`/healthcheck, não atribuir automaticamente falhas à lógica R06.
- Contagem `175` é referência histórica, não inventar que é resultado novo.

---

## 1. Contrato HTTP congelado (Rotas v1.1 §11)

### 1.1 Request

```http
PATCH /account/{account_key}
INTERNAL-TOKEN: <token interno>
Content-Type: application/json

{"status": "INACTIVE", "reason": "Solicitação operacional"}
```

| Campo | Tipo | Validação obrigatória |
|---|---|---|
| `account_key` no path | UUID | Identificador público válido da ACCOUNT; não confundir com `client_key` nem `id` |
| `status` no body | string | **Obrigatório**, um de `ACTIVE`, `INACTIVE`, `CLOSED`; usar caixa definida no contrato |
| `reason` no body | string | **Obrigatório**, aplicar `trim`, não vazio após trim, no máximo **500 caracteres** depois de normalizar |

Somente `status` e `reason` são campos de negócio aceitos. Rejeitar propriedades extras e tipos incompatíveis (objeto, array, número, booleano, `null`) segundo o padrão de contrato HTTP do projeto. Body faltante/inválido/JSON malformado deve cumprir `400 QIT000001` em vez de resposta `422` automática do FastAPI quando contrariar o contrato. Sem mudança de status por query string. Reutilizar autenticação central: **403 tem precedência** sobre erro de UUID/body/lookup se token não autenticou.

Não interpretar PATCH como atualização genérica de colunas: proibidos `balance_cents`, `client_key`, `account_key`, IDs internos, timestamps, ator, eventos enviados pelo cliente ou payload que escolhe CLIENT.

### 1.2 Response (sucesso 200)

```json
{
  "account_key": "550e8400-e29b-41d4-a716-446655440000",
  "status": "INACTIVE"
}
```

**Exatamente duas chaves:** `account_key` (UUID público da conta afetada) e `status` (estado efetivo após commit). Não retornar `reason`, objeto CLIENT, saldo, IDs internos ou timestamps. Reusar DTO/schema público simples para response, se útil, mas **não** reutilizar sem critério o DTO de seis campos do GET R05.

### 1.3 Erros e envelope

| Situação | HTTP | Código |
|---|---:|---|
| UUID/path, body, `status` ou `reason` inválidos | 400 | `QIT000001` |
| `INTERNAL-TOKEN` ausente/incorreto | 403 | `QIT000002` |
| ACCOUNT não encontrada | 404 | `ACC0001` |
| Transição inválida, mesmo estado ou CLOSED terminal | 409 | `ACC0003` |
| Saldo diferente de zero impede CLOSED | 409 | `ACC0004` |
| CLIENT/ACCOUNT em estados incompatíveis | 409 | `CLI0002` |
| Erro inesperado/estrutura incongruente | 500 | `QIT000500` |

Envelope oficial de erro com **exatamente** `title`, `description`, `translation`, `code` (valores e mensagens seguindo convenções existentes). Não vazar SQL, IDs privados, tokens, stack traces nem outros dados internos.

**Observação sobre prioridade de conflitos:** o contrato não fixa ordem absoluta entre diversos conflitos simultâneos. Escolher uma ordem determinística justificada após ler os fluxos (ex.: estado incoerente → 409 CLI0002; transição inválida → 409 ACC0003; fechamento com saldo → 409 ACC0004) e testá-la, sem exigir codificação arbitrária em cenário contraditório. Jamais efetuar escrita antes das revalidações.

### 1.4 Idempotência

`PATCH` da R06 **não é idempotente** pelo contrato: repetir uma transição bem-sucedida chega ao **mesmo estado** e retorna `409 ACC0003`, sem adicionar novos eventos, sem atualizar `updated_at` e sem novo commit de estado. Não implementar replay de resposta 200, `request_control_key`, armazenamento de requests ou outra regra de idempotência da R07.

---

## 2. Máquina de estados e efeitos persistidos

### 2.1 Tabela de transições válidas

| Estado ACCOUNT anterior | Estado CLIENT anterior | Destino ACCOUNT | Requisito extra | Atualizações | Eventos esperados |
|---|---|---|---|---|---|
| ACTIVE | ACTIVE | INACTIVE | reason válido | ACCOUNT → INACTIVE; CLIENT → INACTIVE | ACCOUNT ACTIVE→INACTIVE + CLIENT ACTIVE→INACTIVE |
| INACTIVE | INACTIVE | ACTIVE | reason válido | CLIENT → ACTIVE; ACCOUNT → ACTIVE | CLIENT INACTIVE→ACTIVE + ACCOUNT INACTIVE→ACTIVE |
| ACTIVE | ACTIVE | CLOSED | saldo = 0 | ACCOUNT → CLOSED; CLIENT → INACTIVE | ACCOUNT ACTIVE→CLOSED + CLIENT ACTIVE→INACTIVE |
| INACTIVE | INACTIVE | CLOSED | saldo = 0 | ACCOUNT → CLOSED; CLIENT permanece INACTIVE | **somente** ACCOUNT INACTIVE→CLOSED |

**Invariantes em qualquer sucesso:** ACCOUNT permanece vinculada ao mesmo CLIENT; saldo inalterado; `account.created_at` e `client.created_at` não mudam; `updated_at` das entidades **efetivamente alteradas** segue padrão atual do repo em UTC; status/events coerentes; `actor_type=INTERNAL`; `reason` normalizada replicada nos eventos necessários; `from_status_id`/`to_status_id` reais, **não NULL** nem iguais nos eventos de transição; `created_at` dos eventos UTC; histórico append-only.

### 2.2 Transições proibidas

- ACTIVE→ACTIVE e INACTIVE→INACTIVE: `409 ACC0003`, sem evento; repetição do fechamento CLOSED→CLOSED idem.
- CLOSED→ACTIVE/INACTIVE/CLOSED: `409 ACC0003`; **CLOSED é terminal**.
- ACTIVE→CLOSED e INACTIVE→CLOSED com `balance_cents != 0`: `409 ACC0004`, não zerar saldo automaticamente.
- Pares incoerentes `ACCOUNT ACTIVE / CLIENT INACTIVE` ou `ACCOUNT INACTIVE / CLIENT ACTIVE`: `409 CLI0002`; **nunca reconciliar silenciosamente**. Pares estruturalmente inválidos devem seguir `500` conforme a distinção no fluxo.
- Nunca criar `CLIENT_STATUS_EVENT` `INACTIVE→INACTIVE` ao fechar uma conta já inativa.
- Nunca mudar `CLIENT` isoladamente para simular R09; a R06 coordena os dois recursos.

### 2.3 Exigências de histórico

Tabelas: `ACCOUNT_STATUS_EVENT` e `CLIENT_STATUS_EVENT` (append-only). Ao atualizar status, produzir registro com dono real, `from_status_id`, `to_status_id`, `actor_type=INTERNAL`, `reason` trim, `created_at` coerente. No evento inicial da R04, `from_status_id=NULL` e `actor_type=SYSTEM`; **não copiar essa convenção de criação inicial** para a R06.

Após cada cenário conferir no PostgreSQL **quantidade de eventos, transições, motivo, ator e vínculo por FK**. Não aceitar somente HTTP 200 como prova da mutação. Eventos e status devem ser gravados atomicamente: falha em qualquer escrita → rollback de todas, inclusive timestamps observáveis.

---

## 3. Sequência transacional e estratégia de locks

### 3.1 Fluxo de referência — ordem obrigatória

```text
1. Middleware valida INTERNAL-TOKEN (403 antes de qualquer outra validação).
2. Validar UUID do path e DTO/schema body (400 para dados inválidos).
3. Abrir contexto transacional existente; obter owner (client_id) via account_key
   SEM bloquear primeiro a ACCOUNT; se não encontrada: 404 ACC0001.
4. SELECT CLIENT ... FOR UPDATE          <-- lock PRIMEIRO
5. SELECT ACCOUNT ... FOR UPDATE         <-- lock DEPOIS
   (por account_key e client_id consistente; evitar JOIN com OF implícito)
6. Recarregar/revalidar CLIENT/ACCOUNT status, existência, owner e balance_cents
   após os dois locks; não confiar em leituras feitas antes do bloqueio.
7. Aplicar matriz de transições ou lançar erro de domínio, sem escrita parcial.
8. Atualizar ACCOUNT e, quando preciso, CLIENT.
9. Criar 1 ACCOUNT_STATUS_EVENT e, quando preciso, 1 CLIENT_STATUS_EVENT.
10. Um commit para TODOS os efeitos.
11. Resposta 200 somente depois do commit.
12. Exceção em qualquer ponto -> rollback; liberar locks; propagar handler adequado.
```

**Motivação:** `ACCOUNT` pode ter sido fechada, inativada ou ter recebido saldo por outra operação enquanto nossa requisição aguardava um lock. O estado atual deve ser lido **depois** dos locks. SQLAlchemy `Session` possui identity map; cuidado com objetos já carregados e atributos em cache: efetuar refresh/requery apropriado após `FOR UPDATE` para não usar valores antigos.

**Evitar deadlocks:** quando envolver CLIENT+ACCOUNT, respeitar **CLIENT→ACCOUNT** em todos os caminhos, inclusive falhas e fixtures. Consultas a outros relacionamentos não devem, sem querer, aplicar `FOR UPDATE` em ambas as tabelas fora da ordem; explicitar `OF` quando necessário e suportado. Não usar um lock por `account_key` em ACCOUNT **antes** de bloquear CLIENT.

### 3.2 Convivência com R04, R07 e R09

- **R04** já usa lock do CLIENT ao criar ACCOUNT; a R06 deve ser coerente com o padrão e evitar race na resolução por `account_key`.
- **R07** pode bloquear ACCOUNT para realizar movimentações. Ao obter o lock da conta, a R06 revalida `balance_cents` e estado. Se depósito/transferência confirmou antes, CLOSED com saldo positivo retorna `ACC0004`. Se CLOSED confirmou antes, R07 deve impedir nova movimentação ao reler estado após lock. **Não alterar código da R07**, apenas documentar o acordo.
- **R09** é responsável por CLIENT ACTIVE↔INACTIVE sem ACCOUNT; uma vez existente ACCOUNT, lifecycle coordenado é responsabilidade da R06. A R06 deve lockar CLIENT antes da conta; não adicionar lógica de R09.
- **R08** continua leitura, inclusive contas INACTIVE/CLOSED. R06 não altera contratos de leitura.
- A coordenação de locks para **duas ACCOUNT** em transferências é da R07: ordem crescente por `ACCOUNT.id`; não implementar aqui.

### 3.3 Concurrency testável, não somente alegada

Criar cenários determinísticos com barriers/eventos e transação detentora de lock controlada; simular duas PATCH simultâneas contra mesma conta, transições conflitantes, e preferência real da linha após espera. A primeira conclui; a segunda revalida e responde com conflito ou executa transição permitida **somente se refletir o novo estado real**. Verificar número de eventos e ausência de estado impossível.

Quando observar espera PostgreSQL, seguir a lição da correção R04: **não usar `LIKE '%FOR UPDATE ...%'` em `pg_stat_activity`**. Se necessário, identificar o PID bloqueador real por `pg_backend_pid()`, descartar snapshot com `pg_stat_clear_snapshot()` e correlacionar via `pg_blocking_pids()`, com timeout, cleanup e confirmação de sessão relevante. Não considerar um timeout mais longo como correção de sincronização. Evitar testes que dependam de `sleep` como único sinal de sincronismo.

### 3.4 Rollback e falhas provocadas

Provar que falha após atualização do ACCOUNT mas antes de evento/CLIENT commit **não deixa mutação parcial**. Preferir mecanismo de fault injection em nível de método/session com escopo claro, ou fixture transacional controlada, sem tocar schema do banco principal. Se for inevitável trigger temporário, **somente** com avaliação explícita de risco, limpeza em `finally`, testes serializados e sem interferência na execução de outros devs; não executar DDL destrutivo no banco `bootcamp` compartilhado. Além de erro em ACCOUNT_STATUS_EVENT, cobrir erro em CLIENT_STATUS_EVENT, se factível sem manipular banco compartilhado. Nunca apagar dados de outro desenvolvedor.

---

## 4. Arquitetura e arquivos candidatos (confirmar na inspeção)

| Camada | Padrão esperado | Responsabilidade |
|---|---|---|
| `src/app.py` | registro de rota R06 | `PATCH /account/{account_key}` |
| `src/resources/account.py` | método `on_patch_...` | request/body, controller, HTTP 200 com JSON codificável |
| `src/dtos/` | DTO/schema de **entrada** para `status`/`reason`; DTO de resposta se útil | validar allowlist, trim, tamanho, tipos e projeção pública |
| `src/controllers/account_controller.py` | método de lifecycle | orquestrar transação, validações de negócio, estados e eventos |
| `src/repositories/account_repository.py` | buscas e locks | owner lookup sem lock de ACCOUNT antecipado; lock do CLIENT, depois ACCOUNT; updates/ eventos quando adequado |
| `src/repositories/client_repository.py` | reutilizar/adicionar apenas se necessário | leitura/lock e persistência de CLIENT, eventos sob mesma Session |
| `src/models/` | modelos existentes | não criar tabela/coluna sem divergência demonstrada |
| `src/errors/account_errors.py`, `src/errors/client_errors.py`, `src/errors/__init__.py` | exceções de domínio | ACC0003, ACC0004, CLI0002, reutilizar ACC0001 e erros QIT |
| `tests/integration/client/test_r06_patch_account.py` | suíte TDD | HTTP, banco, rollback, concorrência, status/eventos, Auth |
| `docs/R06_Plano_Completo_Testes_e_Implementacao.md` | este arquivo | status por bloco, decisões e logs/resultados reais |

**Ponto arquitetural crítico:** compartilhar **uma única Session/transaction** entre atualizações de ACCOUNT/CLIENT e inserções dos dois tipos de evento. Não deixar repositórios separados darem `commit` por conta própria; não instanciar outra Session no meio da operação. Respeitar gerenciamento atual de Session em `BaseController`, Request middleware ou `Context` conforme inspecionado. Evitar `session.close()` prematuro.

**DTOs:** R05 já introduziu `AccountDTO` para o GET com 6 campos; **não** usá-lo como DTO de PATCH, pois o body é somente `status` + `reason` e a resposta PATCH é só `account_key` + `status`. Usar padrão mais simples compatível com FastAPI/Pydantic ou os DTOs já existentes; evitar dependência nova, e 422 automático por validação FastAPI se houver contrato 400.

---

## 5. Matriz mínima de TDD — testes auditáveis

**Regras para todos:** cada teste deve criar seu próprio CLIENT+ACCOUNT via endpoints/fixtures existentes, com CPFs/CNPJs/emails/UUIDs únicos; realizar setup controlado dos estados e saldo; garantir que a manipulação de fixture não falsifique o efeito do PATCH. Confirmar SQL e HTTP. Proibir limpeza global, reset de schema ou dados compartilhados. Testes não podem depender de ordem de execução.

### 5.1 Caminhos felizes (T01–T08)

| ID | Cenário e checagens |
|---|---|
| T01 | PF, ACTIVE/ACTIVE → INACTIVE/INACTIVE: HTTP 200 exato 2 campos; 2 eventos INTERNAL reais, reason trim, statuses e timestamps corretos |
| T02 | PJ, INACTIVE/INACTIVE → ACTIVE/ACTIVE: HTTP 200 exato; 2 eventos reais; não altera propriedade nem saldo |
| T03 | ACTIVE/ACTIVE saldo 0 → CLOSED/INACTIVE: HTTP 200; 1 evento ACCOUNT + 1 CLIENT; CLOSED terminal |
| T04 | INACTIVE/INACTIVE saldo 0 → CLOSED/INACTIVE: HTTP 200; 1 evento ACCOUNT e **0** evento CLIENT adicional; `updated_at` CLIENT preservado |
| T05 | Reason com espaços externos é salvo normalizado e retornos não expõem reason/eventos |
| T06 | Limite reason com exatamente 500 caracteres **após trim** é aceito |
| T07 | Confirma dados do mesmo owner/ACCOUNT por key e FKs, preservando `balance_cents`, created_at e históricos anteriores |
| T08 | R05 consulta status após R06 (quando disponível), sem retroceder a contrato GET; CLOSED ainda legível |

### 5.2 Erros de entrada/autenticação (T09–T21)

| ID | Cenário e checagens |
|---|---|
| T09 | `account_key` malformada → 400 QIT000001, nenhum efeito |
| T10 | UUID válido sem ACCOUNT → 404 ACC0001, nenhum efeito |
| T11 | `INTERNAL-TOKEN` ausente → 403 QIT000002, nenhum efeito |
| T12 | `INTERNAL-TOKEN` incorreto → 403 QIT000002, nenhum efeito |
| T13 | Token inválido + UUID malformada + body inválido → **403 prioritário** |
| T14 | Body ausente, JSON malformado, tipo array/null → 400 QIT000001 |
| T15 | `status` ausente / null / número / objeto / inválido ou minúsculo → 400 |
| T16 | `reason` ausente / null / número / objeto / array → 400 |
| T17 | `reason` vazio, espaços apenas ou >500 caracteres após trim → 400 |
| T18 | Campos adicionais (`balance_cents`, `client_key`, `actor_type`, `updated_at`, etc.) → 400; não permitir mass assignment |
| T19 | Respostas de erro com **envelope exato** de 4 chaves, sem `422` acidental |
| T20 | Entrada `status=ACTIVE` não altera status antes de validar `reason` (schema precede writes) |
| T21 | UUID válido de CLIENT usado no path de ACCOUNT não resolve conta → 404; não confundir IDs |

### 5.3 Transições proibidas e integridade (T22–T32)

| ID | Cenário e checagens |
|---|---|
| T22 | ACTIVE→ACTIVE: 409 ACC0003, nenhum evento e timestamps intactos |
| T23 | INACTIVE→INACTIVE: 409 ACC0003, nenhum evento |
| T24 | CLOSED→ACTIVE: 409 ACC0003, CLOSED permanece CLOSED |
| T25 | CLOSED→INACTIVE: 409 ACC0003 |
| T26 | CLOSED→CLOSED: 409 ACC0003, sem replay 200 |
| T27 | ACTIVE saldo positivo → CLOSED: 409 ACC0004, saldo intacto e nenhum efeito |
| T28 | INACTIVE saldo positivo → CLOSED: 409 ACC0004, sem update/evento |
| T29 | ACCOUNT ACTIVE + CLIENT INACTIVE incoerentes → 409 CLI0002, sem reparação |
| T30 | ACCOUNT INACTIVE + CLIENT ACTIVE incoerentes → 409 CLI0002 |
| T31 | Dados estruturalmente inconsistentes: exceção interna 500 QIT000500 conforme contrato, se houver modo seguro de injeção |
| T32 | Nenhuma transição toca FINANCIAL_TRANSACTION, TRANSACTION_ENTRY ou histórico pré-existente |

### 5.4 Atomicidade, race, recuperação (T33–T41)

| ID | Cenário e checagens |
|---|---|
| T33 | Falha forçada e escopada ao inserir ACCOUNT_STATUS_EVENT → rollback ACCOUNT/CLIENT/events |
| T34 | Falha ao inserir CLIENT_STATUS_EVENT → rollback ACCOUNT/CLIENT/events; sem partial commit |
| T35 | Duas PATCH simultâneas para mesma ACCOUNT não produzem duplo evento para mesmo estado; estado final coerente |
| T36 | Lock CLIENT mantido externamente: requisição realmente aguarda, depois revalida estado; watchdog/cleanup seguros |
| T37 | Lock ACCOUNT mantido externamente após lock CLIENT: requisição aguarda, depois revalida estado e saldo; sem inversão de ordem |
| T38 | Estado muda enquanto concorrente aguarda: nova validação → 409 adequado, não usa estado cacheado |
| T39 | Saldo muda antes do lock ACCOUNT: CLOSED com saldo positivo → 409 ACC0004, sem zerar saldo |
| T40 | Repetição pós-200: `409 ACC0003` e contagem de eventos/timestamps inalterada |
| T41 | Corrida com operação financeira simulada de forma segura: sem CLOSED com saldo positivo e sem escrita financeira pelo PATCH; integração R07 real somente quando R07 estiver disponível, não criar/alterar código R07 |

**Matriz é mínima de comportamento**, não exigência de 41 funções individuais. Parametrize de modo inteligente sem esconder casos nem criar 500 linhas artificiais de código. Testes concorrentes/injeção mais arriscados devem ser determinísticos, limitados por timeout, com locks/eventos limpos em `finally`, sem DDL perigoso. Não sacrificar integridade de banco compartilhado para perseguir cobertura.

---

## 6. Plano de execução autônoma por blocos (0 + A–F)

### Bloco 0 — Reconhecimento e riscos [inspeção, sem escrita funcional]

1. Confirmar branch/main+R05, alterações preexistentes, `git status`, `docker compose ps`, bases separadas e baseline 175 com `pytest -q`, se infraestrutura estiver operacional.
2. Ler **integralmente** fontes oficiais acima e o arquivo deste plano; inspecionar R04, R05, testes e fixture de CLIENT events.
3. Mapear `BaseController`/`Context`, repositórios, tipos de erro, `AccountDTO`, modelos event e seed statuses; verificar que UPDATE e eventos podem compartilhar Session.
4. Determinar solução de DTO de entrada que assegure 400 nos erros de schema e não quebre autenticação 403 prioritária.
5. Desenhar a sequência real de locks explícitos e confirmar que não há lock de ACCOUNT antes de CLIENT.
6. Registrar decisões e possíveis bloqueadores neste arquivo. **Sem implementar R07/R08/R09.**

**Aceite:** contrato e dependências checados, branch correta, baseline registrado ou impedimento diagnosticado.

### Bloco A — TDD RED, contrato e validação

1. Criar testes de integração R06 para T01–T04, erros HTTP principais e `reason`/auth, antes de adicionar endpoint.
2. Rodar somente R06; guardar resultado **RED real**, distinguindo falha esperada por endpoint ausente e problemas de ambiente.
3. Testes devem usar dados isolados, comparar envelope e JSON exatos, snapshot persistido dos dois recursos.
4. Não enfraquecer testes para torná-los verdes.

**Aceite:** falhas RED reproduzíveis e documentadas.

### Bloco B — GREEN, transições atômicas

1. Implementar registro PATCH, validação DTO/schema, resource, controller, consultas/lock repository, erros e projeção exata de resposta.
2. Obter owner sem travar ACCOUNT antes; bloquear CLIENT, depois ACCOUNT, revalidar tudo sob lock.
3. Implementar matriz 4 transições, CLOSED terminal, saldo zero, tratamento dos estados incompatíveis e repetição 409.
4. Persistir transições e eventos reais `actor_type=INTERNAL`/reason; **um único commit**, rollback garantido em exceções e conflitos.
5. Fazer GREEN da suíte R06 inicial, registrar as evidências.

**Aceite:** contrato básico e operações coordenadas passam sem side effects.

### Bloco C — Banco real, regras negativas e histórico

1. Cobrir T05–T32; comparar entidades e eventos diretamente no PostgreSQL, não apenas status HTTP.
2. Confirmar todos os casos de status, trim, 500 chars, body inválido, JSON extra, erros exatos e AUTH prioritária.
3. Verificar `updated_at` CLIENT somente quando mudou, ACCOUNT quando mudou, timestamps UTC e ausência de eventos de mesmo status.
4. Conferir que saldo nunca muda e CLOSED sempre exige zero; nenhum financial_transaction/entry criado.

**Aceite:** histórico append-only e integridade de estado preservados em todos os casos.

### Bloco D — Corridas, locks e rollback (obrigatório por risco)

1. Implementar T33–T41 quando executáveis com segurança, com concorrência determinística (barriers/latches/transactions) e cleanup em `finally`.
2. Demonstrar lock CLIENT→ACCOUNT e a revalidação **depois** de obter ambos; sem depender de timing frágil.
3. Garantir que uma falha ao criar qualquer evento não produza updates parciais; teste de rollback seguro.
4. Exercitar fechamento concorrendo com mudança de saldo em dados de fixture controlados, respeitando arquitetura R07 futura.
5. Repetir cenários concorrentes críticos por múltiplas execuções (sugestão **5**) e registrar resultado. Não inventar que o teste passou se não rodou.
6. Se uma injeção segura não for possível, explicar limite, oferecer prova complementar e classificar ressalva. **Não alterar privilégios nem tabelas do banco principal para fabricar falhas.**

**Aceite:** provas confiáveis de atomicidade, lock order, estados/coerência sob concorrência e cleanup seguro.

### Bloco E — REFACTOR, revisão de segurança e qualidade

1. Revisar responsabilidades entre resource/controller/repository/DTO; preservar simplicidade e imports existentes.
2. Garantir que nenhum commit é feito por repository isolado; Session única, transação curta, response pós-commit.
3. Identificar N+1, consultas redundantes, SQL parametrizado, exceptions engolidas, caso de psycopg2 e retorno indevido de 422.
4. Verificar que R05 GET continua refletindo os novos estados; nenhuma rota R01–R05 muda de contrato.
5. Rodar `git diff --check` e analisar escopo do diff. Não alterar schema/migrations por conveniência.

**Aceite:** implementação concisa e auditada, sem problemas CRITICAL/MAJOR pendentes.

### Bloco F — Regressão integral, evidências e handoff

1. Executar `tests/integration/client/test_r06_patch_account.py` isoladamente e a suíte inteira `python -m pytest -q` (baseline **175** + novos casos, não assumir número exato).
2. Verificar novamente teste da R04 lock/concurrency e R05 GET; confirmar que nenhuma regressão apareceu.
3. Rodar `git status`, `git diff --check`, `git diff --stat` e inventário de untracked (`git ls-files --others --exclude-standard`). Atenção: `git diff --stat` sozinho **não inclui arquivos não rastreados**.
4. Atualizar tabela de execução e registrar resultados realmente observados, timestamps/duração, comandos relevantes, falhas corrigidas, ressalvas e segurança dos bancos.
5. Entregar relatório final no mesmo modelo da R05 (seções A–H) com veredito técnico e classificação de findings.
6. **Não fazer commit, push, PR ou merge** sem decisão do usuário.

**Aceite:** baseline preservada, novos testes passando, documentação completa, Git revisável e entrega pronta para auditoria humana.

---

## 7. Definition of Done — checklist executivo

- [x] Código foi escrito na branch `feature/r06-account-patch`, baseada na `main` com R05.
- [x] Arquivo oficial de rotas §11 e F02 foram consultados; contrato sem suposições conflitantes.
- [x] Request usa `account_key` UUID, `status`+`reason`, validação 400, auth prioritária 403.
- [x] Sucesso 200 devolve **exatamente** `account_key`+`status`.
- [x] Todas as 4 transições corretas; CLOSED terminal; mesmo status 409.
- [x] Fechamento exige `balance_cents == 0`; R06 nunca altera saldo.
- [x] Inconsistência CLIENT/ACCOUNT retorna CLI0002 e não é autocorrigida.
- [x] Lock global **CLIENT→ACCOUNT**, revalidação sob locks.
- [x] Eventos reais com `actor_type=INTERNAL`, `reason` normalizada, `from/to` e FKs coerentes.
- [x] Somente ACCOUNT event na transição INACTIVE→CLOSED.
- [x] **Todos os updates/eventos num único COMMIT**, rollback integral testado com segurança.
- [x] DTO/schema de entrada sem mass assignment, respeitando erro 400 em vez de 422.
- [x] Erros 400/403/404/409/500 aderentes ao envelope, sem vazamento.
- [x] Testes de concorrência confiáveis, com timeout e cleanup, executados e documentados.
- [x] Sem mutações financeiras, sem alteração de schema, sem implementação R07/R08/R09.
- [x] R01–R05 continuam aprovadas e regressão total executada.
- [x] `git diff --check` limpo, diff escopo avaliado e arquivos novos inventariados.
- [x] Blocos 0 e A–F com evidências reais, sem marcar etapas não executadas como PASS.
- [x] Nenhum commit/push/PR automático.

---

## 8. Registro de execução — preencher pelo Codex, não antecipar

| Marco | Status | Evidência da execução e duração |
|---|---|---|
| Bloco 0 — inspeção, baseline | PASS | Branch `feature/r06-account-patch`; PostgreSQL da API (`bootcamp:5432`) e descartável (`bootcamp_test:5433`) tiveram nomes, portas e `system_identifier` distintos confirmados; baseline `175 passed in 21.45s`. |
| Bloco A — RED | PASS | Dois primeiros testes executados antes da rota: `2 failed in 22.41s`, ambos por HTTP 405, confirmando RED funcional. |
| Bloco B — GREEN | PASS | Endpoint, schema/DTO, controller, repository, locks e eventos implementados; ciclo inicial `2 passed in 6.91s`. |
| Bloco C — integridade/eventos/erros | PASS | Quatro transições, validações, precedência de autenticação, conflitos, timestamps, saldo, eventos e ausência de escritas financeiras verificados por HTTP e SQL real. |
| Bloco D — concorrência/rollback | PASS | Rollback injetado nos dois tipos de evento; concorrência e ordem CLIENT→ACCOUNT comprovadas. Um RED concorrente real (`500`) revelou carregamento de status inconsistente após espera; corrigido com resolução de status em instruções posteriores aos locks. |
| Bloco E — refactor/auditoria | PASS | Responsabilidades preservadas, uma Session/um commit, repositories sem commit, schema sem mass assignment e sem alterações em R07/R08/R09. |
| Bloco F — regressão/documentação | PASS | R06 `39 passed in 4.90s`; R04 concorrência `1 passed`; R05 `11 passed`; suíte completa `214 passed in 26.62s`; Git revisado. |

**Contratos/decisões técnicas verificadas:** autenticação permanece no middleware; validação estrutural usa JSON Schema e normalização de `reason` usa `AccountPatchDTO`; o owner é resolvido sem lock e as decisões de domínio usam somente valores recarregados após locks CLIENT→ACCOUNT; CLOSED não altera saldo nem cria movimentação financeira.

**Testes R06 (comando, resultado, duração):** `.\.venv\Scripts\python.exe -m pytest -q tests/integration/client/test_r06_patch_account.py` → `39 passed in 4.90s`.

**Teste(s) de concorrência repetidos (quantidade, resultados):** os dois testes críticos foram executados em cinco processos pytest independentes; todas as 10 execuções passaram (rodadas de 2.12s, 1.73s, 1.95s, 2.10s e 1.99s).

**Regressão total (pass/fail/skip, duração):** `214 passed in 26.62s`, zero falhas, zero erros e zero skips reportados.

**Falhas injetadas e salvaguardas da base:** triggers/functions com nomes UUID, condição limitada à ACCOUNT/CLIENT do teste e remoção obrigatória em `finally`; as duas falhas produziram QIT000500 e snapshot físico integralmente inalterado. Fixtures confirmam bancos distintos e consultas de inspeção usam transações read-only; nenhum DROP/TRUNCATE/reset foi executado.

**Arquivos novos e alterados:** alterados `src/app.py`, `src/controllers/account_controller.py`, `src/dtos/__init__.py`, `src/errors/account_errors.py`, `src/repositories/account_repository.py`, `src/resources/account.py`; novos `src/dtos/account_patch_dto.py`, `src/schemas/patch_account.json`, `tests/integration/client/test_r06_patch_account.py` e este plano.

**Verificações Git:** `git diff --check` sem erros; alterações restritas à R06 e ao documento-mestre; nenhum commit, push ou PR realizado.

**Riscos conhecidos e findings (CRITICAL/MAJOR/MEDIUM/LOW):** nenhum CRITICAL/MAJOR/MEDIUM. LOW operacional: os testes de rollback instalam objetos temporários no banco local da API e persistem dados isolados de teste; cleanup dos objetos é obrigatório e coberto por `finally`.

**Veredito e condição para commit:** R06 funcionalmente completa e pronta para auditoria humana final; commit somente após revisão do diff e das ressalvas operacionais acima.

---

## 9. Integração e comandos orientativos (para operador humano)

```powershell
git switch main
git pull --ff-only origin main
git status
git switch -c feature/r06-account-patch
```

Salvar este arquivo diretamente em `docs/R06_Plano_Completo_Testes_e_Implementacao.md`, seguindo o padrão de R02/R04/R05. Configurar ambiente local com os valores efetivos aprovados no repositório antes dos testes; não colar segredo real em documentação. Após completar Bloco F, **pedir auditoria final com o diff completo** antes de commit/push/PR.
