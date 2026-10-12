# R09 — Plano Completo de Testes e Implementação
## PATCH /client/{client_key} — BaaS Simplificado / QI Tech

**Projeto:** `bootcamp-qitech-bank-api`
**Branch prevista:** `feature/r09-client-patch`
**Baseline validada pelo time:** `214 passed` após merge da R06 (revalidar no começo do trabalho)
**Estado do documento:** PLANEJAMENTO — o Codex deve registrar os resultados reais em cada bloco.
**Responsabilidade:** R09; não implementar R07/R08 nem refatorar outras rotas.

---

## Bloco 0 — Fonte de verdade e inspeção (obrigatório)

### 0.1 Fontes a ler integralmente/trechos pertinentes

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md`, sobretudo §§4, 5, 14, 16, 19, 20.
2. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md`, sobretudo F02 §§2.1–2.6 e §§2.15–2.16; F01 para efeitos da R03/R04.
3. `docs/ERD_v1_1_FINAL_BaaS_QITech.md`, CLIENT/CLIENT_STATUS/CLIENT_STATUS_EVENT/ACCOUNT.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md` e convenções de schema, middleware e erros.
5. Implementações atuais de R01, R02, R03, R04 e R06: `app.py`, resources/controllers/repositories, models, schemas, DTOs, exceptions, tests.
6. `database/database.sql` / schema físico do projeto. Não modificar o banco para adaptar a rota.

A síntese `r07_updated.md` do outro desenvolvedor corresponde à **R07** e não muda as regras de lifecycle da R09. Ela altera decisões financeiras da R07 (tarifas PF/PJ e idempotência via header); não incorporar nada disso à R09 nem modificar R07/R08.

### 0.2 Verificações prévias

- Confirmar branch `feature/r09-client-patch`, a partir de `main` atualizada após R06.
- `git status` limpo antes de começar; preservar alterações preexistentes se houver.
- Baseline de testes e infraestrutura; host 5432 `bootcamp`, host 5433 `bootcamp_test`, instâncias distintas.
- Localizar middleware `INTERNAL-TOKEN` e sua precedência; identificar convenção de validação JSON: 400 (não 422 automático).
- Identificar padrão de gestão da Session, rollback e carregamento SQLAlchemy após `FOR UPDATE`.
- Identificar métodos reutilizáveis para eventos de CLIENT da R03/R06 e consulta de existência de ACCOUNT.
- Conferir códigos de erro oficiais e não inventar códigos, payloads ou transições.

**Critério de saída:** mapa de arquivos e riscos, fonte de verdade confirmada, baseline real documentada. Se contrato estiver contraditório de modo essencial, reportar; não adivinhar.

---

## 1. Contrato HTTP congelado

```http
PATCH /client/{client_key}
INTERNAL-TOKEN: <token>
Content-Type: application/json
```

Exemplo de entrada:

```json
{
  "status": "PENDING",
  "reason": "Solicitação de nova análise cadastral"
}
```

Campos permitidos: **somente** `status` e `reason`, ambos obrigatórios.

- `status` é uma das metas permitidas pela R09 conforme a transição de origem: `PENDING`, `ACTIVE`, `INACTIVE`. `REJECTED` não é destino da R09; `CLOSED` não é status de CLIENT.
- `reason`: string obrigatória, `strip()`/trim, não vazia depois da normalização, no máximo **500 caracteres** após trim. Persistir o motivo normalizado no evento.
- Sem alteração de timezone, documento, e-mail, identificação ou quaisquer outros atributos por esta rota.
- Propriedades extras e tipos incorretos são rejeitados. Convenção do projeto: erro HTTP **400**, não 422 do FastAPI.
- `INTERNAL-TOKEN` inválido/ausente: HTTP **403 antes** de consultar CLIENT ou validar UUID/body.

Resposta HTTP **200** com **exatamente**:

```json
{
  "client_key": "UUID",
  "status": "PENDING"
}
```

Erros do contrato:

| HTTP | Código | Condição |
|---|---|---|
| 400 | `QIT000001` | UUID/body/status/reason inválidos |
| 403 | `QIT000002` | Token ausente/inválido; precedência sobre path e body |
| 404 | `CLI0001` | CLIENT não encontrado |
| 409 | `CLI0002` | Transição incompatível, status igual, origem indevida |
| 409 | `CLI0009` | CLIENT possui qualquer ACCOUNT e quer lifecycle ACTIVE ↔ INACTIVE via R09 |
| 500 | `QIT000500` | Falha interna inesperada; rollback |

Preservar envelope `title`, `description`, `translation`, `code` e textos oficiais, usando convenções atuais. Ausência de idempotência: repetir status já aplicado não dá replay de sucesso; dá conflito 409.

---

## 2. Regras de domínio / máquina de estados

| Estado atual CLIENT | Estado solicitado | Resultado | Precondição |
|---|---|---|---|
| `REJECTED` | `PENDING` | **Permitido** | Nova análise cadastral; sem limite de tentativas |
| `ACTIVE` | `INACTIVE` | **Permitido** | **Nenhuma** ACCOUNT existente |
| `INACTIVE` | `ACTIVE` | **Permitido** | **Nenhuma** ACCOUNT existente |
| Qualquer estado | Mesmo estado | **409 `CLI0002`** | Sem alteração e sem evento |
| `PENDING` | `ACTIVE`/`REJECTED` | **Proibido** | Responsabilidade da R03 |
| `REJECTED` | `ACTIVE`/`INACTIVE` | **Proibido** | Deve passar por R03 após reanálise |
| `ACTIVE`/`INACTIVE` | `PENDING` | **Proibido** | Reanálise é somente `REJECTED → PENDING` |
| `ACTIVE` ↔ `INACTIVE` | Com ACCOUNT `ACTIVE`/`INACTIVE`/**`CLOSED`** | **409 `CLI0009`** | Lifecycle deve ocorrer na R06 |

**Regra crítica:** qualquer ACCOUNT existente bloqueia a troca `ACTIVE ↔ INACTIVE` pela R09, inclusive CLOSED; não filtrar apenas contas abertas. Não apagar/recriar conta para contornar regra.

Não inventar limite de reanálises nem coluna `reanalysis_count`.

**Evento em transição bem-sucedida:** exatamente um `CLIENT_STATUS_EVENT` (`from_status_id`, `to_status_id`, `actor_type=INTERNAL`, `reason` com trim, data consistente). Atualizar `CLIENT.status_id` e `CLIENT.updated_at`; um único commit. Nenhum `ACCOUNT_STATUS_EVENT` ou mutação de ACCOUNT/financeiro.

---

## 3. Arquitetura e responsabilidades

- **`app.py`**: registra `PATCH /client/{client_key}` conforme padrão atual.
- **`resources/client.py`**: valida payload via schema existente e delega ao controller; retorna HTTP 200 e projeção exata.
- **`schemas/patch_client.json`** (se convenção): estrutura estrita com `status` e `reason`, sem extras; validações de domínio complementares no controller/DTO.
- **`dtos/client_patch_dto.py`** (se estilo atual): normaliza `reason`, define resposta pública, sem acesso a banco; evitar abstrações grandes.
- **`controllers/client_controller.py`**: valida UUID, busca CLIENT, adquire lock, revalida estado/ACCOUNT, aplica regras, adiciona evento, um único commit, rollback no erro.
- **`repositories/client_repository.py`**: busca/lock do CLIENT, lookup de status, verificação de ACCOUNT, inserts/updates. **Nunca commit dentro do repository.** Reaproveitar infraestrutura da R03/R06.
- **`errors/client_errors.py`**: erros `CLI0002`, `CLI0009` se ainda não houver classes equivalentes; manter envelope e linguagem coerentes.
- **`tests/integration/client/test_r09_patch_client.py`**: HTTP real + asserts de persistência e concorrência.
- **Este plano**: atualizar resultados reais, não só checklist fictício.

Não copiar responsabilidades financeiras de R07/R08; evitar alterações no modelo físico, nas migrações e em arquivos de outros desenvolvedores.

---

## 4. Concorrência, snapshots e atomicidade

**Ordem de locks global quando relevante:** CLIENT antes de ACCOUNT (R06). A R09 **bloqueia apenas CLIENT**, não precisa adquirir lock de ACCOUNT para executar lifecycle sem conta.

Fluxo recomendado:

```text
AUTH
→ validação de UUID + body
→ BEGIN (Session existente)
→ SELECT CLIENT FOR UPDATE
→ refresh/consulta de estado válida após lock
→ validar transição solicitada
→ para ACTIVE ↔ INACTIVE: consultar qualquer ACCOUNT do mesmo client_id, sem depender de status da ACCOUNT
→ se possui ACCOUNT: 409 CLI0009
→ atualizar CLIENT.status_id e updated_at
→ inserir 1 CLIENT_STATUS_EVENT (INTERNAL, reason normalizada)
→ COMMIT ÚNICO
→ resposta 200 com client_key e status
```

- Revalidar *depois* do lock, não antes; cuidado com identity map e JOIN carregando status antigo durante esperas.
- R09 vs R09: apenas uma requisição vence; a segunda observa novo estado e responde 409.
- R09 vs R04: ambos seguram CLIENT, garantindo que mudança de status e abertura de ACCOUNT não violem a regra (conforme F02 §2.6).
- R09 vs R03: serializar sobre CLIENT; a R03 faz `PENDING → ACTIVE/REJECTED`, a R09 só `REJECTED → PENDING` para reanálise.
- R09 vs R06: mesma linha CLIENT; não pode contornar coordenação quando há ACCOUNT.
- `commit` único incluindo a atualização e o evento; erro em inserção do evento implica rollback de tudo.
- Em erro esperado 409/404/400, não criar evento, alterar timestamps ou persistir alteração.

Para testes de locks em `pg_stat_activity`, preferir PID bloqueador e `pg_blocking_pids()` + `pg_stat_clear_snapshot()`; evitar texto SQL exato. Testes devem ter timeout, isolamento e cleanup robusto.

---

## 5. Matriz mínima de testes (orientativa, não quantidade artificial)

### Contrato e autenticação

- [ ] PF e PJ: resposta 200 com exatas duas chaves e UUID pública correta.
- [ ] Reason normalizada e persistida; bordas de 1/500 caracteres, vazia e >500.
- [ ] Body ausente, não-JSON quando pertinente, campos extras, tipos `number`/`bool`/`null`, status ausente, reason ausente.
- [ ] UUID malformado 400; UUID bem formado inexistente 404.
- [ ] Token ausente/inválido 403 com UUID válido, inválido e body inválido (precedência).
- [ ] Envelope e códigos oficiais exatos; status iguais 409, nada persistido.
- [ ] Status inválidos: `REJECTED`, `CLOSED`, lowercase, tipos incorretos.

### Transições e integridade

- [ ] `REJECTED → PENDING` cria evento único; mais de um ciclo de reanálise é permitido se entre eles ocorrer novo REJECT da R03.
- [ ] `ACTIVE → INACTIVE` sem ACCOUNT cria um evento.
- [ ] `INACTIVE → ACTIVE` sem ACCOUNT cria um evento.
- [ ] `PENDING → ACTIVE` e `PENDING → REJECTED` proibidas pela R09.
- [ ] `ACTIVE/INACTIVE → PENDING` proibidas.
- [ ] `REJECTED → ACTIVE/INACTIVE` proibidas.
- [ ] `ACTIVE ↔ INACTIVE` com qualquer ACCOUNT (`ACTIVE`, `INACTIVE`, `CLOSED`) = 409 `CLI0009` e nenhuma escrita.
- [ ] Após PATCH bem-sucedido, GET R02 retorna status atualizado; R03/R04/R06 não sofrem regressão.
- [ ] No-op e erros preservam `CLIENT.updated_at`, status, eventos, ACCOUNT/status events e linhas financeiras.
- [ ] Não muda timezone, e-mail, tipo de CLIENT ou data de criação.

### Concorrência e falhas

- [ ] Duas requisições R09 simultâneas para mesmo CLIENT não criam eventos redundantes.
- [ ] R09 disputando lock do CLIENT com R04: cenários de vitória de cada uma, sem ACCOUNT inapropriada.
- [ ] R09 disputando com R03/atualização de status: revalidação após lock, sem estado inválido.
- [ ] R09 ao existir ACCOUNT permanece proibida mesmo se ACCOUNT estiver CLOSED.
- [ ] Falha ao inserir CLIENT_STATUS_EVENT aciona 500 handler global e rollback de status/updated_at/evento.
- [ ] Testes críticos concorrentes repetidos em processos separados, com resultados e durações registrados.
- [ ] Asserções reais no PostgreSQL, não só HTTP. Isolamento por clientes gerados nos testes.

Se fault injection requer DDL/trigger, limitar a dados do próprio teste, implementar `finally` e não deixar resíduos; não usar DDL destrutiva na base principal. Alternativa segura equivalente é aceitável, com ressalva explícita.

---

## 6. Execução TDD por blocos — Rodada única do Codex

### BLOCO 0 — Inspeção e baseline

- Ler fontes e mapear camadas/convenções, branch e bancos.
- Rodar baseline; documentar resultado de verdade.
- Examinar os acoplamentos com R03/R04/R06; confirmar que R07/R08 estão em branches externas e não aparecem na base atual.
- **Saída:** escopo aprovado tecnicamente e plano de implementação, sem criar outra documentação concorrente.

### BLOCO A — RED: contrato essencial

- Escrever primeiro testes HTTP das três transições e das respostas/erros essenciais.
- Executar subset e registrar RED esperado (405/ausência da implementação).
- Não aceitar GREEN prévio sem explicar; não modificar assertions para fabricar RED.

### BLOCO B — GREEN: rota funcional

- Implementar schema, DTO, resource, controller, repository e erros mínimos para satisfazer os primeiros testes.
- Um `CLIENT FOR UPDATE`, sem locks redundantes em ACCOUNT.
- Persistir evento e estado em um commit; rollback integral.
- Executar os testes até GREEN.

### BLOCO C — Domínio e integridade

- Cobrir toda a matriz de transições, body, auth, PF/PJ, eventos, reason e timestamps.
- Verificar existência de ACCOUNT inclusive CLOSED.
- Assegurar consulta R02 refletindo estado; nenhuma mutação de outra entidade.
- Repetir testes até todos os cenários de domínio passarem.

### BLOCO D — Concorrência e rollback

- Exercitar R09 vs R09, R09 vs R04, concorrência/revalidação contra R03 ou equivalente seguro.
- Validar atomicidade com falha do evento, sem side effects; cleanup garantido.
- Repetir cenários concorrentes; não aumentar timeout simplesmente para passar.
- Atenção a `pg_stat_activity` e snapshots de transação.

### BLOCO E — Refactor e auditoria

- Verificar código simples, reutilização de funções reais existentes, Session lifecycle, lock order e erros.
- Controller faz domínio e commit; Repository não faz commit; DTO sem SQL; Schema strict.
- Auditar riscos CRITICAL/MAJOR/MEDIUM/LOW. Evitar refatorações globais e alterações fora do escopo.

### BLOCO F — Regressão e entrega

- Rodar suite R09 e `python -m pytest -q` em toda a base; registrar contagens/tempo.
- Verificar `git diff --check`, `git status`, `git diff --stat`, untracked e documentação.
- Atualizar este arquivo com RED/GREEN, decisões, resultados e pendências.
- Entregar relatório A–H; **não** commitar, enviar push ou abrir PR automaticamente.

**Meta:** preservar no mínimo os **214 testes existentes** (a quantidade final será determinada pelos testes novos executados), sem falhas, além de cobrir riscos centrais da R09.

---

## 7. Segurança do ambiente e integração com Moha

- API localhost:3000; db principal 5432; db_test 5433; MockServer 1080.
- Nunca usar DROP/TRUNCATE/reset volume no banco principal; schema destrutivo apenas no `bootcamp_test`.
- Testes HTTP da API podem criar novos CLIENTs isolados, mantendo o padrão aditivo existente.
- Não alterar R07 nem R08. O arquivo `r07_updated.md` define o escopo do Moha; não absorver regras financeiras na R09.
- Pequenos conflitos futuros em `app.py` ou exports serão resolvidos ao atualizar `main`; verificar testes de ambas as rotas depois dos merges.
- Não alterar a estratégia financeira de locks para 'ajudar' R07. A R09 adquire CLIENT; R07 adquire ACCOUNT(s), e R06 possui ordem CLIENT → ACCOUNT. O time deve manter consistência global na integração.
- Preservar decisões canônicas da R09; alterações de fee/idempotência de R07 precisam ser documentadas pelo responsável antes da integração geral.

---

## 8. Definition of Done da R09

- [x] Endpoint PATCH registrado e autenticado.
- [x] Body validado (somente `status`, `reason`) e resposta exata 200.
- [x] Três transições e todos os erros oficiais.
- [x] `REJECTED → PENDING` sem limite de tentativas.
- [x] ACTIVE ↔ INACTIVE somente sem ACCOUNT de qualquer status.
- [x] `CLIENT FOR UPDATE`, revalidação após lock e ordem compatível com R03/R04/R06.
- [x] Atualização de status + `CLIENT_STATUS_EVENT INTERNAL` em commit único.
- [x] Rollback sem mudanças parciais.
- [x] Ausência de escrita em ACCOUNT/financeiro.
- [x] Concorrência R09/R04, R09/R09 e R09/R03 examinada com testes seguros.
- [x] Testes R01–R06 preservados; regressão completa verde.
- [x] Planejamento atualizado, `git diff --check` sem erros, Git pronto para auditoria humana.

---

## 9. Evidências de execução — preencher pelo Codex

- **Branch e commit base:** `feature/r09-client-patch`, base `1e1accf` (`Merge pull request #28 ... feature/r06-account-patch`). A única mudança inicial era este plano não rastreado, preservado e atualizado.
- **Baseline existente:** `.\.venv\Scripts\python.exe -m pytest -q` → `214 passed in 31.37s`.
- **RED e motivo:** suíte essencial R09 antes da rota → `4 failed in 3.12s`; todos os casos receberam HTTP 405 por ausência do PATCH.
- **GREEN inicial:** após schema/DTO/resource/controller/repository/erro → `4 passed in 2.57s`.
- **R09 testes finais:** `51 passed in 5.26s`; as parametrizações cobrem contrato, três transições, negativos, ACCOUNT em três estados, histórico, limites de reason, rollback e concorrência.
- **Concorrência (casos, repetições):** R09×R09, R09×R04 com cada operação vencendo e R03→R09 foram repetidos em cinco processos pytest independentes; todas as 20 execuções passaram (`2.47s`, `2.05s`, `2.22s`, `1.95s`, `2.68s`). Locks foram observados por PID com `pg_stat_clear_snapshot()` e `pg_blocking_pids()`.
- **Rollback:** trigger/function com nomes UUID e filtro pelo `client_id` exclusivo provocou falha no `CLIENT_STATUS_EVENT`; resposta `500 QIT000500`, snapshot físico integralmente inalterado e cleanup em `finally`.
- **Regressão final:** R03 `19 passed in 8.98s`; R04 `17 passed in 3.06s`; R06 `39 passed in 5.67s`; suíte completa `265 passed in 27.73s`, sem falhas/erros/skips reportados.
- **`git diff --check`:** sem erros ao final da implementação.
- **Arquivos alterados:** `src/app.py`, `src/resources/client.py`, `src/controllers/client_controller.py`, `src/repositories/client_repository.py`, `src/errors/client_errors.py`, `src/dtos/__init__.py`; novos `src/dtos/client_patch_dto.py`, `src/schemas/patch_client.json`, `tests/integration/client/test_r09_patch_client.py` e atualização deste plano.
- **Achados CRITICAL/MAJOR/MEDIUM/LOW:** nenhum CRITICAL/MAJOR/MEDIUM. LOW operacional: testes HTTP persistem dados isolados no banco local e o teste de rollback instala objetos temporários sempre removidos em `finally`. LOW de desenvolvimento: o cache de JSON Schema exigiu reinício somente da API após alteração exclusiva do `.json`; bancos e volumes não foram reiniciados.
- **Conclusão:** R09 funcionalmente completa e pronta para auditoria humana final antes de commit/push/PR.
