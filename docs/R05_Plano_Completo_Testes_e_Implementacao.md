# R05 — Plano Completo de Testes e Implementação
## `GET /account/{account_key}` | BaaS Simplificado — Bootcamp QI Tech 2026

**Projeto:** `bootcamp-qitech-bank-api`
**Rota:** R05 — `GET /account/{account_key}`
**Branch prevista:** `feature/r05-account-get` (criada a partir de `main` atualizada)
**Referência de regressão:** 164 testes aprovados localmente após a R04 e a correção do observador de locks no PR #26.
**Status inicial:** PLANEJADO — implementação e testes ainda não executados.
**Arquivo canônico no repositório:** `docs/R05_Plano_Completo_Testes_e_Implementacao.md` (mesmo padrão dos planos R02 e R04).

> **Natureza e autoridade.** Este é o documento-mestre de planejamento e execução da R05, **não** uma alteração do contrato. Foi elaborado com base em `Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` (§10 R05 e §4 convenções), `ERD_v1_1_FINAL_BaaS_QITech.md`, `Fluxos_v1_1_FINAL_BaaS_QITech.md` e nos planos R02/R04. O Codex deve lê-lo integralmente antes de implementar, executar os blocos 0 e A–F e registrar evidências reais no próprio documento; sem criar um `00.md` alternativo.

---

## 0. Objetivo, limites e fontes da verdade

Implementar consulta autenticada do **snapshot atual de uma ACCOUNT**, identificada pela chave pública `account_key`, sem qualquer escrita no banco. Entregar o contrato do GET exatamente como definido no documento oficial de rotas v1.1, com TDD RED → GREEN → REFACTOR e regressão de R01–R04 preservada.

### 0.1 Ordem de precedência

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` — **§10 R05**, **§4** convenções gerais (contrato principal).
2. `docs/ERD_v1_1_FINAL_BaaS_QITech.md` + `database/database.sql` — tabela `ACCOUNT`, relacionamento com `CLIENT`, status, timestamps.
3. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md` — invariantes; R05 é somente leitura, sem fluxo mutável específico.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md` — regras gerais da API.
5. Implementações de R02 (GET de cliente), R04 (abertura e persistência da conta) e testes atuais; usar a arquitetura comprovada.
6. Este plano — instrumento de execução e rastreabilidade, nunca substituto do contrato oficial.

**Escopo:** validação/autenticação, GET, DTO/schema de **resposta**, leitura de ACCOUNT e seu status e `CLIENT.client_key`, serialização UTC, casos negativos e ausência de efeitos colaterais.

**Fora do escopo:** R06 PATCH, R07/R08, movimentação/recalcular saldo, alteração de conta/cliente/status, migrações sem necessidade, refatorar DTOs de R01–R04, mudanças em regras já integradas, novas tabelas.

### 0.2 Ponto de partida e componentes a inspecionar

- Branch: `feature/r05-account-get`, criada de `main` já integrada com PRs #25 e #26; conferir `git status` antes.
- Baseline histórica de regressão: **164 testes** após a R04, medida na execução local anterior; reconfirmar após mudança.
- HTTP: `src/app.py`, `src/resources/account.py` e autenticação/middleware atual.
- Orquestração: `src/controllers/account_controller.py` e `src/controllers/base_controller.py`.
- Persistência: `src/repositories/account_repository.py`, `src/models/account.py`, `src/models/client.py`, `src/models/account_status.py`.
- DTO/schema: procurar convenções reais (`src/dtos/`, schemas, Pydantic, `resources`, `utils/schema_handler.py`); não introduzir dependência nova por capricho.
- Erros: `src/errors/account_errors.py`, catálogo genérico e tradução de erro.
- Testes: `tests/integration/client/test_r02_get_client.py` e `test_r04_create_account.py`, mais fixtures compartilhadas.

---

## 1. Contrato HTTP confirmado — R05 (Rotas v1.1, §10)

### 1.1 Requisição

```http
GET /account/{account_key}
INTERNAL-TOKEN: <token interno>
```

- `account_key`: UUID público da ACCOUNT (não `client_key`, não BIGINT `id`).
- Sem body de negócio, sem parâmetros de paginação.
- A autenticação deve ocorrer antes do resource lookup; token inválido sempre resulta em `403`, inclusive com UUID malformado.
- **Todos os estados da ACCOUNT são legíveis:** `ACTIVE`, `INACTIVE`, `CLOSED`. A R05 não condiciona leitura ao estado do CLIENT.

### 1.2 Resposta de sucesso — HTTP 200

```json
{
  "account_key": "<UUID da ACCOUNT>",
  "client_key": "<UUID do CLIENT proprietário>",
  "status": "ACTIVE",
  "balance_cents": 125000,
  "created_at": "<timestamp UTC com Z>",
  "updated_at": "<timestamp UTC com Z>"
}
```

**Contrato estrito:** seis campos, com estes nomes e tipos: `account_key: str UUID`, `client_key: str UUID`, `status: str` entre `ACTIVE | INACTIVE | CLOSED`, `balance_cents: int` (centavos BRL), `created_at: str`, `updated_at: str` (UTC com sufixo `Z`). Datas devem vir dos timestamps `TIMESTAMPTZ` persistidos e ser normalizadas para UTC, sem perder precisão indevidamente. O exemplo de `125000` **não** é constante da rota.

**Não embutir:** objeto CLIENT completo; ACCOUNT_STATUS_EVENT; FINANCIAL_TRANSACTION; TRANSACTION_ENTRY; `id`, `client_id`, `status_id`, informações técnicas internas ou dados pessoais.

**Saldo:** `balance_cents` representa o valor persistido em `ACCOUNT.balance_cents`, não deve ser recalculado a partir de lançamentos ou alterado. GET é idempotente, sem lock de escrita.

### 1.3 Erros oficiais

| Cenário | HTTP | Código oficial | Regra |
|---|---:|---|---|
| `account_key` UUID malformada | 400 | `QIT000001` | Falha no parâmetro de rota |
| `INTERNAL-TOKEN` ausente/incorreto | 403 | `QIT000002` | Middleware antes do lookup/validação de UUID |
| UUID válido sem ACCOUNT correspondente | 404 | `ACC0001` | ACCOUNT inexistente |
| Falha interna ou inconsistência estrutural | 500 | `QIT000500` | Não expor SQL, detalhes internos ou stack trace |

Envelope de erro oficial (§4.3):

```json
{
  "title": "string",
  "description": "string",
  "translation": "string",
  "code": "string"
}
```

Conferir textos de mensagem e tradução já estabelecidos no código/catálogo de erros, preservando o padrão do projeto. Não criar código novo nem devolver o erro de CLIENT inexistente em lugar de `ACC0001`.

### 1.4 DTO de resposta — obrigatório no desenho, simples na implementação

Criar ou reutilizar um schema/DTO **explícito** de saída que represente exclusivamente os seis campos oficiais. Preferir a ferramenta/padrão já instalada e utilizada; se não houver, implementar uma projeção tipada simples sem nova dependência injustificada. O controller/repository não deve retornar diretamente objetos ORM ou dicionários de coluna indiscriminados ao consumidor HTTP.

Não criar DTO de request para GET. Não iniciar refatoração geral das DTOs antigas nesta branch.

### 1.5 Regras de integridade observáveis

- Consultar por `ACCOUNT.account_key` e relacionar somente o `CLIENT.client_key` dono real da ACCOUNT.
- Ler `ACCOUNT_STATUS.enumerator` persistido, não usar IDs fixos ou inferir `ACTIVE` pelo status do CLIENT.
- Respeitar `created_at` e `updated_at` atuais, com UTC `Z` no JSON.
- Não executar `commit`, `flush`, `UPDATE`, `INSERT`, criar evento ou bloquear linha com `FOR UPDATE` para ler.
- R05 deve refletir eventual mudança de estado/saldo por rotas futuras sem carregar regras de mutação em sua camada de leitura.

---

## 2. Fluxo da requisição e responsabilidades

```text
Cliente HTTP
   │ GET /account/{account_key} + INTERNAL-TOKEN
   ▼
Middleware de autenticação existente
   │ 403 conforme contrato em caso de falha
   ▼
Route / Resource
   │ valida formato do parâmetro e aplica DTO de saída
   ▼
AccountController (leitura)
   │ orquestra a busca e traduz ausência para erro público existente
   ▼
AccountRepository
   │ SELECT usando account_key, sem escritas
   ▼
PostgreSQL: account (+ status se necessário)
   │ entidade / projeção explícita
   ▼
DTO de saída → HTTP 200
```

### Limites de cada camada

- **Route/resource:** contrato HTTP, autenticação herdada, parâmetros, status e serialização; sem regras SQL.
- **Controller:** caso de uso, delegação da consulta e tradução de erros; sem manipular estado.
- **Repository:** consulta parametrizada por chave pública; sem commit, flush de escrita nem lock exclusivo no GET.
- **DTO/schema:** definição restrita do JSON externo e conversão dos tipos apropriados; evitar circularidade e abstração gratuita.
- **Model:** reuse da persistência existente; nenhuma migração se o esquema atual atender.

**Critério de simplicidade:** um DTO/projeção pública de seis campos é necessário; não multiplicar classes ou introduzir frameworks adicionais sem necessidade. Seguir a arquitetura existente.

---

## 3. Estratégia TDD — matriz mínima de integração

Identificar primeiro as fixtures e helpers já disponíveis na R04 e R02. Preferir testar a API em execução + conferir banco real, sem substituir integração por mocks. Asserções devem usar o **contrato oficial** definido no Bloco A.

| ID | Cenário | Resultado esperado | Observação |
|---|---|---|---|
| 05-T01 | Buscar ACCOUNT criada para INDIVIDUAL ACTIVE | 200; JSON de seis campos exatos | Criar CLIENT/ACCOUNT com helpers existentes |
| 05-T02 | Buscar ACCOUNT criada para COMPANY ACTIVE | 200; JSON de seis campos exatos | Exercitar mesmo contrato público |
| 05-T03 | Verificar resposta contra dados persistidos | Campos idênticos ao banco | account_key, client_key proprietário, saldo, status e timestamps |
| 05-T04 | `account_key` inexistente mas UUID válido | 404 ACC0001; envelope exato | Código oficial confirmado em Rotas §10 |
| 05-T05 | `account_key` malformada | 400 QIT000001 | Testar URL com UUID inválida |
| 05-T06 | Sem `INTERNAL-TOKEN` | 403; envelope exato | Sem vazamento de dados |
| 05-T07 | `INTERNAL-TOKEN` inválido | 403; envelope exato | Sem vazamento de dados |
| 05-T08 | Token inválido + UUID malformado | Precedência de autenticação conforme R02/R04 | Verificar comportamento HTTP real |
| 05-T09 | Token inválido + chave desconhecida | Precedência de autenticação conforme R02/R04 | Não efetuar lookup exposto |
| 05-T10 | Ler ACCOUNT INACTIVE e CLOSED | 200 em ambos, estado correto | R05 permite todos os três status |
| 05-T11 | GET repetido | Mesma representação se banco não mudar | Sem efeitos de escrita |
| 05-T12 | Integridade: antes/depois | ACCOUNT, CLIENT, eventos e saldo inalterados | Verificar timestamps e contagens relevantes |
| 05-T13 | Campos permitidos / tipos de resposta | Exatamente seis campos públicos | Verificar UUIDs, status, int centavos, UTC Z |
| 05-T14 | Compatibilidade com R04 | GET encontra exatamente a conta recém-criada | Teste ponta a ponta POST→GET |
| 05-T15 | Falha inesperada de leitura | 500 QIT000500 sem dados internos | Injeção localizada, com limpeza segura |
| 05-T16 | Timestamps e saldo após mudança controlada | `created_at`/`updated_at` em UTC `Z` e saldo persistido | Não recalcular pelo extrato; sem escrita pelo GET |
| 05-T17 | Alterar indevidamente CLIENT de origem/chave | GET não mistura proprietários | Chave pública da conta não se confunde com a do cliente |

**Não tratar os 17 cenários como quantidade obrigatória de testes:** parametrização é permitida; cada comportamento relevante deve ficar coberto. Registrar o número real de testes adicionados.

### Validação de imutabilidade

Antes e depois de GET repetido, comparar dados persistentes pertinentes: `account` (status, saldo, `updated_at`, se existir), `account_status_event`, `client`, `client_status_event` e registros financeiros relacionados quando houver. Não manipular colunas de maneira incompatível com o ERD. Usar helpers de consulta que não escrevam.

### Integração segura com DB

- Banco principal de integração/API: `bootcamp` na porta do host **5432**.
- Banco separado para testes destrutivos de schema: `bootcamp_test` na porta do host **5433**.
- API em `127.0.0.1:3000`; MockServer em `127.0.0.1:1080`.
- Integrações com DB principal podem criar apenas registros isolados de teste com chaves únicas, conforme prática da suíte existente.
- Nunca executar `DROP`, `TRUNCATE`, apagar volumes ou resetar o banco principal.
- Inspecionar/configurar variáveis no próprio shell da execução, sem presumir persistência entre terminais.

Variáveis de referência no **PowerShell**:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
$env:SERVER_LOCALHOST="127.0.0.1"
$env:MOCKSERVER_URL="http://127.0.0.1:1080"
```

---

## 4. Plano de execução em blocos (autônomo, com checkpoints)

### Bloco 0 — Inspeção do contrato oficial já especificado

**Objetivo:** conferir fontes de verdade, ponto de partida Git e fluxo da R02/R04.

Ações: verificar branch e working tree; examinar documentos da API; conferir §10 do documento Rotas v1.1; inspecionar modelos, resources, erros e testes; verificar correspondência dos seis campos e envelopes com os contratos atuais; fazer inventário das alterações necessárias.

**Saída:** confirmação do contrato já publicado (§10 R05) e mapa de arquivos; nenhuma alteração no código de produção antes disso.

**Gate:** divergência entre RFC, ERD e código existente deve ser registrada e resolvida antes de implantar contrato público.

### Bloco A — RED: testes HTTP e esquema de resposta

**Objetivo:** escrever primeiros testes de integração refletindo o contrato fechado.

Ações: criar arquivo dedicado da R05, preferencialmente `tests/integration/client/test_r05_get_account.py` se essa for a convenção atual; criar fixtures enxutas reaproveitando R04; cobrir sucesso PF/PJ, seis campos, `ACC0001`, UUID inválida, token, timestamps UTC `Z` e contrato estrito; rodar só esses testes.

**Saída:** falhas esperadas atribuíveis à ausência da R05; registrar evidências RED sem adulterar os testes.

### Bloco B — GREEN: implementação mínima

**Objetivo:** fazer passar os testes iniciais com mudança mínima.

Ações: adicionar método de consulta ao repository existente; controller de leitura; route/resource GET; DTO/schema explícito de saída com seis campos, aderente ao padrão atual; implementar/reutilizar erro `ACC0001` para ACCOUNT inexistente, conforme catálogo oficial.

**Saída:** testes iniciais GREEN. Não mexer em R01–R04 além de adições estritamente necessárias em módulos compartilhados.

### Bloco C — Persistência, status e ausência de efeitos colaterais

**Objetivo:** demonstrar leitura correta de dados reais e nenhuma mutação.

Ações: ampliar cobertura com T03, T10–T14 conforme aplicabilidade; confirmar retorno por `account_key` e não por `client_key`/id; testar `ACTIVE`, `INACTIVE` e `CLOSED` retornando sempre 200; ler campos persistidos diretamente; verificar ausência de eventos e alterações não solicitadas.

**Saída:** integração e integridade aprovadas, com evidência SQL/teste.

### Bloco D — Negativos, segurança e consistência

**Objetivo:** garantir precedência e comportamento de falha.

Ações: verificar contratos exatos 400/403/404/500, imutabilidade, nulabilidade/tipos, serialização restrita; revisar reutilização do middleware e exposição de dados.

**Saída:** matriz de testes coberta, sem fragilidade em payloads nem dependência de valores mágicos.

### Bloco E — REFACTOR e auditoria

**Objetivo:** reduzir duplicações e dívida técnica local à R05.

Ações: revisar consultas, tipagem, DTO, legibilidade, isolamento de teste, métodos de repository, tratamento de erros, SQL parametrizado; atualizar documentação. Não refatorar DTOs legados fora do escopo.

**Saída:** diff focado, `git diff --check` sem saída.

### Bloco F — Regressão completa e preparação do PR

**Objetivo:** terminar a rota com evidências objetivas.

Ações: rodar teste isolado R05, regressão total (baseline: 164 anteriores + novos testes coletados), verificar `docker compose ps`, diff/status do Git; registrar sucessos, falhas e ressalvas; consolidar relatório e checklist.

**Saída:** alterações prontas para revisão humana e futuro commit, sem commit/push/PR automático.

---

## 5. Critérios de aceite (Definition of Done)

- [ ] Contrato oficial localizado, referências e decisões documentadas.
- [ ] Método `GET /account/{account_key}` registrado e autenticado.
- [ ] HTTP 200 com os **seis campos** obrigatórios, com `client_key` real e timestamps UTC `Z`.
- [ ] Erros e precedência equivalentes ao padrão do projeto, inclusive 404.
- [ ] Sucesso com ACCOUNT de cliente INDIVIDUAL e COMPANY.
- [ ] Leitura por `account_key`, sem expor colunas técnicas.
- [ ] Sem alteração de ACCOUNT, CLIENT, eventos, saldo ou lançamentos.
- [ ] Cobertura de `ACTIVE`, `INACTIVE` e `CLOSED` com HTTP 200.
- [ ] TDD RED comprovado; GREEN comprovado; refatoração revisada.
- [ ] Execução de todos os testes novos e da regressão total; resultados reais registrados.
- [ ] Nenhuma alteração desnecessária no esquema físico ou rotas R01–R04.
- [ ] `git diff --check` limpo e escopo de arquivos conferido.
- [ ] Branch limpa de alterações externas, pronta para decisão de commit/PR.

**Não confundir:** `164 passed` é a linha de base histórica, **não** o resultado de uma futura execução da R05. Escrever contagem e duração reais ao final.

---

## 6. Relatório de execução — preencher com evidências reais

| Marco | Estado inicial | Evidência/resultado real |
|---|---|---|
| Bloco 0 — contrato | CONCLUÍDO | Branch `feature/r05-account-get`, baseline de 164 testes GREEN; contrato §10, SQL e R02/R04 conferidos sem divergência. |
| Bloco A — RED | CONCLUÍDO | `tests/integration/client/test_r05_get_account.py`: 7 falhas reais por rota GET ausente; 3 testes de autenticação nasceram GREEN pelo middleware existente. |
| Bloco B — GREEN | CONCLUÍDO | GET registrado, consulta somente leitura por `account_key`, `AccountNotFound` ACC0001 e `AccountDTO` de seis campos; 10 testes R05 GREEN. |
| Bloco C — integridade | CONCLUÍDO | Consultas PostgreSQL confirmam ACCOUNT/CLIENT/status/saldo/timestamps; ACTIVE, INACTIVE e CLOSED retornam 200; GET repetido não altera conta, cliente, eventos ou movimentações. |
| Bloco D — erros e segurança | CONCLUÍDO | 400 QIT000001, 403 QIT000002 e precedência de autenticação, 404 ACC0001 e envelopes exatos cobertos por HTTP. Falha interna permanece atendida pelo handler central QIT000500 e pelo caminho de inconsistência não tratada. |
| Bloco E — refactor | CONCLUÍDO | DTO explícito localizado e sem abstrações adicionais; repository não usa lock, flush ou commit no GET. |
| Bloco F — regressão | CONCLUÍDO | R05: 11 passed em 3.05s; suite completa: 175 passed em 21.76s. |

**Arquivos alterados:** `src/app.py`, `src/resources/account.py`, `src/controllers/account_controller.py`, `src/repositories/account_repository.py`, `src/errors/account_errors.py`, `src/dtos/account_dto.py`, `src/dtos/__init__.py`, `tests/integration/client/test_r05_get_account.py` e este plano.
**Comandos e resultados de testes:** baseline `python -m pytest -q`: 164 passed em 23.95s; RED R05: 7 failed, 3 passed; R05 final: 11 passed em 3.05s; suite final: 175 passed em 21.76s.
**Falhas e ações tomadas:** as falhas RED indicaram rota GET, consulta, DTO e erro ACC0001 ausentes. Implementação mínima adicionada sem modificar schema físico ou rotas anteriores.
**Riscos residuais / decisões técnicas:** falha interna de leitura é protegida pelo handler central; não foi simulada por mutação insegura de FK/permissões. R05 retorna todos os status e não antecipa lifecycle da R06.
**`git status` e `git diff --stat`:** apenas arquivos da R05 modificados/criados; `git diff --check` sem saída; sem commit, push ou PR.

---

## 7. Interface com R06 e R07/R08 — levantamento contratual, sem implementar

A R06 é `PATCH /account/{account_key}` e **já está definida em** `Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` (§11) e `Fluxos_v1_1_FINAL_BaaS_QITech.md` (§2.7–2.14). Registrar/confirmar no relatório, mas não implementá-la na R05:

- Entrada `{"status": "INACTIVE", "reason": "..."}`; `reason` obrigatório, `trim`, não vazio, máximo 500 caracteres; somente status e reason.
- Transições permitidas: ACTIVE → INACTIVE, INACTIVE → ACTIVE, ACTIVE → CLOSED e INACTIVE → CLOSED; CLOSED terminal; mesmo estado → 409.
- R06 coordena estado CLIENT e ACCOUNT e grava eventos aplicáveis com um único COMMIT; fechamento exige `balance_cents = 0`.
- Ordem de lock global no R06: **CLIENT → ACCOUNT** (resolver dono antes, revalidar sob locks), importante para concorrer com R07/R08.
- R06: resposta 200 com `account_key` e `status`; erros incluem ACC0001, ACC0003, ACC0004 e CLI0002, conforme contrato; não implementar ou antecipar tais regras no GET.
- R05 deve retornar todos os status sem modificar estado e sem lock de escrita; refletirá atualizações legítimas posteriores do R06/R07.

**Estratégia de implementação:** finalizar R05 isolada em `feature/r05-account-get`, integrar via PR, depois criar `feature/r06-account-patch` a partir de `main` sincronizada, com `docs/R06_Plano_Completo_Testes_e_Implementacao.md` separado. Evitar dois agentes editando controllers/repositories compartilhados em paralelo.

---

## 8. Comandos de preparação (executados pelo humano quando cabível)

```powershell
git switch main
git pull --ff-only origin main
git status
git switch -c feature/r05-account-get
```

Copiar este documento para `docs/R05_Plano_Completo_Testes_e_Implementacao.md` **antes** da execução do Codex. Ao finalizar, o Codex **não** deve commitar, fazer push nem abrir PR sem autorização explícita.
