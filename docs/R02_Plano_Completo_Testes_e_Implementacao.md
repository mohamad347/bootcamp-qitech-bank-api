# R02 — Plano Completo de Testes e Implementação
## `GET /client/{client_key}` | BaaS Simplificado — Bootcamp QI Tech 2026

**Status:** PLANEJADO — execução por blocos TDD, com revisão humana antes de commit/push
**Rota:** R02 — `GET /client/{client_key}`
**Issue:** Issue 03, conforme identificação de trabalho informada pelo time (confirmar ID numérico no GitHub, se necessário)
**Branch:** `feature/r02-client-get` — **já criada, publicada e sincronizada**
**Branch-base:** `feature/r01-client-create`, pois a R01 ainda não foi integrada à `main`
**Commit de base conhecido:** `e3ef46a` — `test(r01): complete GHI coverage and persistence validation`
**Baseline:** 114 testes aprovados na suíte completa; 43 testes funcionais e 7 de persistência da R01
**Método:** TDD (RED → GREEN → REFACTOR), um comportamento novo por vez; testes existentes não devem regredir.

> **Natureza do documento.** Este é o plano de trabalho da R02, não um contrato novo. Em caso de divergência, prevalecem os contratos finais/congelados do repositório. Os nomes dos arquivos e métodos ainda não criados são *propostas*, não uma exigência de estrutura. A execução deve comparar as propostas com o código **atual** antes de decidir.

---

## 1. Objetivo e escopo

Implementar uma consulta **somente leitura** do snapshot cadastral atual de um `CLIENT`, identificado por seu `client_key` público (UUID), retornando o contrato apropriado para `INDIVIDUAL` ou `COMPANY`. A consulta não cria, altera ou encerra CLIENT, não movimenta dinheiro, não embute ACCOUNT e não percorre o histórico de status.

```text
R01  POST /client                 → cria CLIENT / INDIVIDUAL ou COMPANY / evento inicial
       │
       └── fornece client_key (UUID público)
                   │
                   ▼
R02  GET /client/{client_key}     → lê CLIENT e somente a especialização pertinente
                   │
           ┌───────┴───────┐
           ▼               ▼
      INDIVIDUAL         COMPANY
        → 200             → 200
```

**Fora do escopo:** R03 (análise), R09 (atualização/lifecycle), criação de account, eventos embutidos, paginação, endpoints auxiliares para testes, alterações do ERD e mudanças de contrato da R01.

### 1.1 Fontes de verdade e precedência

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` — **Seção 7: R02**, mais convenções transversais.
2. `docs/ERD_v1_1_FINAL_BaaS_QITech.md` e `database/database.sql` — entidades, status, especializações, timestamps e constraints.
3. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md` — invariantes gerais F01/F02. **A R02 não possui fluxo principal próprio:** é leitura simples, especificada nas Rotas.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md` — decisões arquiteturais e trade-offs.
5. `README.md`, `docs/como-o-projeto-e-organizado.md`, documentação de TDD e código atual.
6. Esta proposta e a issue — instrumentos de planejamento/cobertura, não substitutos de contrato.

**Regra:** não resolver silenciosamente contradições entre fontes de alta prioridade. Antes de implementar, reportar o trecho divergente.

---

## 2. Contrato HTTP R02 (congelado)

```http
GET /client/{client_key}
INTERNAL-TOKEN: <token interno>
```

**Sucesso:** `200 OK`. **Idempotente:** sim. **Locks de escrita:** nenhum. **Mutações/commit:** nenhum.

### 2.1 Resposta para `INDIVIDUAL`

```json
{
  "client_key": "UUID-público",
  "client_type": "INDIVIDUAL",
  "email": "pessoa@example.com",
  "timezone": "America/Sao_Paulo",
  "status": "PENDING",
  "cpf": "52998224725",
  "full_name": "Pessoa de Teste",
  "birth_date": "2000-01-01",
  "created_at": "2026-10-11T12:34:56Z",
  "updated_at": "2026-10-11T12:34:56Z"
}
```

**Conjunto exato de chaves PF:** `client_key`, `client_type`, `email`, `timezone`, `status`, `cpf`, `full_name`, `birth_date`, `created_at`, `updated_at` (10 campos). Valores acima são **exemplos ilustrativos**, não seeds fixos.

### 2.2 Resposta para `COMPANY`

```json
{
  "client_key": "UUID-público",
  "client_type": "COMPANY",
  "email": "empresa@example.com",
  "timezone": "America/Manaus",
  "status": "PENDING",
  "cnpj": "12345678000199",
  "legal_name": "Empresa de Teste Ltda.",
  "trade_name": null,
  "created_at": "2026-10-11T12:34:56Z",
  "updated_at": "2026-10-11T12:34:56Z"
}
```

**Conjunto exato de chaves PJ:** `client_key`, `client_type`, `email`, `timezone`, `status`, `cnpj`, `legal_name`, `trade_name`, `created_at`, `updated_at` (10 campos). O CNPJ do exemplo não substitui um CNPJ válido gerado para os testes.

**Ponto crítico:** `trade_name` **faz parte da resposta**, mesmo quando não existe; nesse caso o JSON deve conter `"trade_name": null`, não omitir a chave.

### 2.3 Timestamps

- A persistência existente usa `TIMESTAMPTZ` e `datetime` aware.
- Na resposta: `created_at` e `updated_at` em **UTC**, formato ISO 8601/RFC3339 e com sufixo literal **`Z`**.
- Não basta `isoformat()` com `+00:00` se o contrato exige `Z`.
- Não converter para `CLIENT.timezone` na R02; timezone cadastral é outro campo.
- Testes devem verificar parsing como instante UTC e, quando fizer sentido, comparar o instante com o banco sem depender de formatação de microssegundos não congelada.

### 2.4 Estados consultáveis

`PENDING`, `ACTIVE`, `REJECTED` e `INACTIVE`. A rota retorna o **status atual** do CLIENT, não a sequência de eventos que o levou até ali. CLIENT rejeitado/inativo continua consultável, não vira `404` por seu estado.

### 2.5 Erros e precedência

| Condição | HTTP | Código |
|---|---:|---|
| `client_key` malformado | `400` | `QIT000001` |
| `INTERNAL-TOKEN` ausente/inválido | `403` | `QIT000002` |
| UUID válido sem CLIENT correspondente | `404` | `CLI0001` |
| Falha interna ou inconsis­tência de especialização | `500` | `QIT000500` |

Corpo padrão de erro:

```json
{
  "title": "string",
  "description": "string",
  "translation": "string",
  "code": "string"
}
```

**Autenticação antes do resource lookup e da validação funcional da chave.** Exemplo: token inválido + UUID inexistente/malformado deve ser **403**, sem revelar se o recurso existe. Não deixar o FastAPI devolver automaticamente `422` no lugar do `400` contratado para UUID inválido.

### 2.6 Campos proibidos e integridade

- Não devolver `id`, `status_id`, `client_id` nem IDs internos das especializações.
- Não incluir ACCOUNT, ACCOUNT_STATUS_EVENT nem CLIENT_STATUS_EVENT.
- Não incluir campos PF em uma resposta COMPANY ou vice-versa.
- Se o CLIENT disser `INDIVIDUAL` mas faltar sua especialização, **não** inventar perfil nem devolver resposta parcial; encaminhar pela infraestrutura de erro interno do projeto.
- A R02 não executa `FOR UPDATE`, não atualiza `updated_at`, não cria evento nem chama `commit()`.

---

## 3. Arquitetura e regras de implementação

```text
FastAPI app.py / registro GET
  ↓
middlewares existentes (auth, session manager etc.)
  ↓
ClientResource.on_get_by_key(...)       [HTTP 200 + serialização, sem regra de domínio]
  ↓
ClientController.get_by_key(...)        [validação/decisão + projeção pública]
  ↓
ClientRepository.get_by_key(...)        [SELECT por UUID / leitura de especialização]
  ↓
Client, ClientStatus, IndividualClient/CompanyClient (ORM)
  ↓
PostgreSQL
```

**Nomes acima são sugestões.** Verificar os métodos de GET já adotados para `SampleEntity` no repositório-base e manter consistência sem copiar histórico de status ou regras específicas daquele exemplo.

### 3.1 Resource

- Receber o identificador de path e delegar ao controller.
- Gerar resposta HTTP 200 com `JSONResponse`/serialização coerente com a R01 e recursos atuais.
- Não acessar banco, normalizar dados ou decidir o tipo PF/PJ aqui.

### 3.2 Controller

- Garantir `QIT000001` para UUID malformado (no lugar arquitetural mais coerente com o projeto).
- Distinguir UUID válido inexistente (`CLI0001`).
- Decidir qual especialização compõe o snapshot e tratar inconsistência sem fingir sucesso.
- Aplicar a representação pública exata e timestamps UTC com `Z`.
- Não fazer commit nem carregar histórico.

### 3.3 Repository

- Consulta parametrizada/ORM por `client_key` público.
- Consultar status e uma especialização correta, com uso cuidadoso de relacionamentos/joins já existentes.
- Não usar `FOR UPDATE`, `.with_for_update()`, `UPDATE`, `INSERT`, `DELETE`, `flush()` ou `commit()` no caminho GET.
- **Não consultar especializações desnecessárias só para montar o response**; avaliar plano de consulta simples e legível, sem otimização especulativa.

### 3.4 Models e banco

- Reusar `Client`, `ClientStatus`, `IndividualClient` e `CompanyClient` que a R01 já introduziu.
- Não alterar `database.sql`/ERD por conveniência da leitura.
- Não adicionar relações ORM genéricas ou novos índices sem necessidade demonstrada.

### 3.5 Erros e DTO

- Usar `QIException` e handlers existentes; a ausência de CLIENT deve mapear `CLI0001`.
- Não expor mensagem SQL/stack trace em respostas 500.
- **DTO é checkpoint de decisão, não implementação automática.** A R01 manteve um `dict` por ser uma projeção mínima e única. A R02 tem duas projeções públicas mais ricas; avaliar após A/B se um DTO pequeno oferece ganho real em organização, sem criar hierarquia ou abstração genérica.

---

## 4. TDD e organização dos testes

O teste funcional exercita **a API HTTP real** pelo helper de requisição existente; não importa resource, controller, repository ou models de produção. Use dados únicos e o `POST /client` da R01 para criar um caso PENDING real. O banco da API e o `bootcamp_test` usado nos testes de schema são **separados**.

Sugestões de arquivos (confirmar convenções do projeto):

```text
tests/integration/client/test_r02_get_client.py      # HTTP caixa-preta
# opcional, apenas quando necessário:
tests/integration/client/<fixtures_de_estado>.py    # preparação controlada de estados
```

**Não usar fixture de schema que dá reset em `public` para preparar o banco real da API.** O banco `bootcamp_test` só pode ser resetado pela própria suíte de schema. A R02 deve ler o CLIENT efetivamente criado na instância da API, não um registro criado em banco separado que ela não enxerga.

### 4.1 Como testar ACTIVE, REJECTED e INACTIVE antes de R03/R09

As rotas que mudam status ainda não foram implementadas. Para testar a capacidade de leitura da R02 sem antecipá-las:

1. Criar **um novo CLIENT de teste**, com email/CPF/CNPJ exclusivos, pelo `POST /client` existente; confirmar seu `client_key`.
2. Preparar seu estado desejado por **fixture de integração explicitamente identificada**, usando transação SQL contra **o banco da API** apenas para esse CLIENT de teste. Respeitar as transições do F02: `PENDING → ACTIVE` ou `PENDING → REJECTED`; para `INACTIVE`, passar primeiro por `PENDING → ACTIVE → INACTIVE` (sem ACCOUNT). Inserir eventos coerentes `CLIENT_STATUS_EVENT` com `actor_type` correto e `from_status_id/to_status_id` apropriados, dentro da mesma transação de preparação. Não construir lifecycle artificial proibido apenas para obter um status.
3. Consultar a R02 por HTTP; validar snapshot atual e campos exatos.
4. A fixture deve ser segura, parametrizada, evitar modificar outros clientes e documentar o efeito persistente. Não confundir rollback de conexão de teste com rollback dos commits da API.

**Importante:** a preferência é validar cada estado com fixture controlada sem criar APIs artificiais. A fixture não é implementação de R03 ou R09 e não deve virar código de produção. Se alguma transição requerida parecer incompatível com os Fluxos/ERD, revisar o contrato antes de montar a fixture.

### 4.2 Dados e repetibilidade

- `client_key` vindo da resposta R01, não um `id` de banco.
- CPF/CNPJ matematicamente válidos, emails exclusivos (`uuid4`).
- Não depender de ordem de testes, sequências ou IDs fixos.
- Considerar que testes HTTP inserem registros reais e eles continuam no banco após o teste. **Sem limpeza destrutiva**.
- Para UUID inexistente: gerar `uuid4()` e, se necessário, confirmar ausência antes do teste; não assumir valor fixo.
- Não forçar centenas de casos paramétricos quando 1–2 cenários representativos protegem o mecanismo.

### 4.3 Estratégia RED → GREEN → REFACTOR

```text
escolher comportamento contratado
       ↓
criar menor teste observável
       ↓
executar isolado e registrar RED (se ainda não existe)
       ↓
implementar mínimo necessário nas camadas corretas
       ↓
GREEN do teste isolado
       ↓
R02 inteira + R01 relevante
       ↓
full suite ao fechar o bloco
       ↓
revisão humana → commit/push do bloco autorizado
```

Para comportamento já coberto pela infraestrutura e que nasce GREEN, registrar isso e não forçar mudança artificial.

---

## 5. Plano de blocos A–E

### BLOCO A — Primeiro vertical slice INDIVIDUAL

**Objetivo:** `POST /client` de PF válida → usa UUID retornado → `GET /client/{client_key}` retorna `200` com **todo o snapshot PF**.

**Teste A1 (único cenário feliz completo):**

- Criar PF por POST real com CPF e email únicos, token válido; conferir `201`.
- Usar o `client_key` recebido para GET com token válido.
- Confirmar `200`, corpo JSON objeto e **exatamente 10 chaves PF**.
- Conferir `client_key`, `client_type=INDIVIDUAL`, email canônico, timezone, `status=PENDING`, CPF sem máscara, `full_name` e `birth_date` canônicos.
- Confirmar `created_at` e `updated_at` parseáveis e emitidos como UTC com `Z`, não retornados como timezone local nem `+00:00`.
- Excluir `id`, `status_id`, ACCOUNT, evento e campos PJ pela igualdade exata de chaves.

**Primeiro RED esperado:** `404` (rota ainda não registrada) ou outro comportamento incorreto real. Não inventar o resultado; registrar o observado.

**Implementação mínima provável:** registro de rota GET, `ClientResource`, método de consulta em controller/repository, erro `CLI0001` se necessário, projeção PF. **Não** criar lógica PJ ou fixtures dos quatro status nesse bloco.

**Exit criteria A:** teste A1 GREEN, arquivo R02 GREEN, R01 intacta, full suite GREEN, Git limpo quanto a whitespace, relatório detalhado; **parar para revisão humana sem commit/push**.

### BLOCO B — Snapshot COMPANY

**Objetivo:** ler PJ via R01 → R02 com projeção distinta e exata.

- **B1:** COMPANY válido com `trade_name` preenchido → `200`, 10 chaves PJ, email/CNPJ/nomes canônicos, timezone, status, timestamps UTC `Z`, sem campos PF.
- **B2:** COMPANY com `trade_name` omitido ou whitespace na criação → `"trade_name": null` **presente** no JSON.
- Confirmar que lógica comum de CLIENT/status/timestamps não é duplicada sem necessidade.
- Decidir se projeção deve continuar em funções/dicts pequenos ou DTO, **sem refactor por estética**.

**Exit B:** B1/B2 GREEN, regressão A + R01 + full suite GREEN; checkpoint para revisão antes de commit.

### BLOCO C — Leitura de todos os status

**Objetivo:** ler o status **atual** de CLIENT, independentemente do estado cadastral.

- **C1:** `PENDING` (normalmente já coberto pelo Bloco A).
- **C2:** `ACTIVE` → `200` e `status=ACTIVE`.
- **C3:** `REJECTED` → `200` e `status=REJECTED`.
- **C4:** `INACTIVE` → `200` e `status=INACTIVE`.
- Fixture controlada conforme §4.1; verificar que a R02 não filtrou indevidamente status.
- Pode parametrizar C2–C4 se a montagem for homogênea. Não multiplicar PF × PJ × todos os status sem risco real de branch.

**Exit C:** quatro estados legíveis, sem introduzir rotas de mutação, full suite GREEN.

### BLOCO D — Erros, precedência e segurança

- **D1:** `client_key` malformado → `400 QIT000001` e corpo padrão.
- **D2:** UUID válido inexistente → `404 CLI0001` e corpo padrão.
- **D3:** token ausente → `403 QIT000002`.
- **D4:** token inválido → `403 QIT000002`.
- **D5:** token inválido + UUID válido inexistente → `403`, sem resource lookup (se ainda não protegido suficientemente).
- **D6:** UUID malformado + token inválido → `403`, para proteger precedência middleware antes da validação no resource (se risco real).
- **D7:** inconsistência física de especialização deve virar erro interno, não `200`; preferir revisão estática/integração isolada cuidadosamente controlada. Não corromper banco principal nem criar fixture destrutiva por esse teste.

**Exit D:** mapeamentos HTTP exatos protegidos, sem `422` automático para UUID, full suite GREEN.

### BLOCO E — Revisão final / Definition of Done

Não é licença para refactor amplo. Auditar:

- Respostas PF/PJ e contrato exato de campos.
- UTC `Z` em `created_at` e `updated_at`.
- Leitura sem locks de escrita; ausência de `.with_for_update()`/`FOR UPDATE`.
- Ausência de INSERT/UPDATE/DELETE, `flush()`, `commit()` e criação de evento na execução GET.
- Zero vazamento de IDs internos, ACCOUNT ou histórico.
- GET repetido para mesmo recurso estável retorna snapshot equivalente e não modifica `updated_at`; observar que consultas feitas após mutações legítimas poderiam naturalmente mudar a resposta.
- Testes independentes, fixtures seguras e somente dados próprios.
- Avaliação DTO fundamentada: manter dict vs DTO(s) de saída; sem obrigatoriedade de DTO apenas porque a resposta é maior.
- Documentação operacional alinhada, se necessário.
- Contrato R01 preservado.

**Exit E:** auditoria, diff revisado, R02 + R01 + full suite GREEN, recomendação DTO explícita, sem pendências contratuais relevantes.

---

## 6. Matriz planejada de cobertura

| Caso | Contrato | Prova ideal | Bloco | Primeiro resultado esperado |
|---|---|---|---|---|
| A1 | PF existente → 200 + todos campos + UTC Z | POST R01 + GET R02 real | A | RED de rota ausente |
| B1 | PJ existente → 200 + campos específicos | POST R01 + GET R02 real | B | RED se PJ ainda não implementada |
| B2 | `trade_name=null` explícito | POST sem `trade_name` + GET | B | RED/GREEN |
| C1 | PENDING consultável | A1/B1 | A/B | GREEN após A |
| C2 | ACTIVE consultável | Fixture de estado + GET | C | GREEN esperado após leitura genérica |
| C3 | REJECTED consultável | Fixture de estado + GET | C | GREEN esperado após leitura genérica |
| C4 | INACTIVE consultável | Fixture de estado + GET | C | GREEN esperado após leitura genérica |
| D1 | UUID inválido → 400 QIT000001 | GET HTTP | D | RED/GREEN |
| D2 | UUID válido inexistente → 404 CLI0001 | GET HTTP | D | RED/GREEN |
| D3/D4 | Sem token/token inválido → 403 | GET HTTP | D | GREEN infraestrutura |
| D5/D6 | 403 antes do lookup/UUID | GET HTTP | D | GREEN infraestrutura |
| D7 | Especialização ausente → 500 | Revisão estática ou ambiente controlado | D/E | Avaliar sem corromper DB |
| E1 | Sem `FOR UPDATE`, sem mutação | Leitura de código + repetição de GET | E | GREEN |
| E2 | Sem ACCOUNT/evento/IDs internos | Conjunto exato de chaves A1/B1 | A/B/E | GREEN |
| E3 | DTO justificado ou dispensado | Revisão arquitetural | E | Não é teste |

**Evitar duplicação:** status PENDING é naturalmente coberto em A/B; não criar um teste por atributo da resposta, por mil variantes UUID ou por todos os quatro status em ambos os tipos sem risco concreto.

---

## 7. Critérios de correção e riscos específicos

### 7.1 Auth antes do lookup

O middleware existente deve impedir qualquer descoberta sobre um CLIENT sem token. Não efetuar query antes de conferir autenticação.

### 7.2 UUID path e FastAPI

Um type annotation `UUID` no path pode gerar `422` automaticamente, divergindo do contrato (`400 QIT000001`). Inspecionar a convenção de erros e controlar a validação para obter **exatamente** o contrato, sem introduzir handler global invasivo para toda API.

### 7.3 Timestamps UTC

A sessão SQLAlchemy pode devolver `TIMESTAMPTZ` com timezone da conexão. Converter explicitamente para `timezone.utc` antes de serializar e emitir `Z` é o comportamento exigido pela R02. Não confundir `client.timezone` com o timezone do timestamp da resposta.

### 7.4 Snapshot versus história

O repository/controller devem consultar o estado atual, não reconstruí-lo da última linha de histórico nem devolver uma lista de eventos. `CLIENT_STATUS_EVENT` é append-only, mas **não é parte da resposta da R02**.

### 7.5 Consistência PF/PJ

Se `client_type` aponta para especialização que não existe, a consulta não pode devolver sucesso incompleto. A cobertura dessa falha deve ser projetada sem corromper o banco compartilhado usado pelo desenvolvedor.

### 7.6 Performance sem antecipação

A rota faz uma consulta pontual por UUID; a prioridade é correção, legibilidade e ausência de locks, não micro-otimização nem relacionamento ORM desnecessário.

### 7.7 Ambiente e isolamento

```powershell
# Docker da aplicação e PostgreSQL separado para schema
# Executar dentro do PowerShell com .venv ativada
$env:TEST_DATABASE_URL="postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
$env:SERVER_LOCALHOST="127.0.0.1"

python -m pytest -q tests/integration/client/
python -m pytest -q
```

A suíte de schema recria `public` no banco de teste: **nunca** apontar `TEST_DATABASE_URL` para o banco principal usado pela API.

---

## 8. Política de commits, Git e integração

O ponto de partida está estabelecido:

```text
feature/r01-client-create  →  e3ef46a  (R01 concluída)
          │
          └─ feature/r02-client-get → e3ef46a (branch criada e publicada)
```

A R01 **ainda não foi mesclada à `main`**, conforme informado pelo time. A R02 foi criada intencionalmente como **branch empilhada** sobre R01. Portanto:

- **Não** criar novamente a branch R02.
- **Não** trocar para `main` para implementar R02.
- **Não** fazer merge/rebase automático de `main` ou de R01.
- Antes de mudar arquivos, confirmar `git branch --show-current`, `git status`, `git log -1 --oneline` e `git merge-base --is-ancestor e3ef46a HEAD` (exit 0).
- Este arquivo de planejamento poderá ser copiado para `docs/` como **arquivo novo ainda untracked** antes do primeiro teste; isso é intencional e não representa uma alteração suspeita. Preservá-lo, e não interromper apenas por esse arquivo.
- O Codex **não faz** `git add`, `git commit`, `git push` nem merge; a revisão humana autoriza cada commit.
- Quando R01 for integrada à `main`, avaliar a estratégia de PR (inclusive squash merge) antes de atualizar o histórico de R02. Não reescrever automaticamente a branch.

**Observação:** a `main` remota foi atualizada após a criação da R01; isso **não** autoriza incorporar mudanças agora sem revisão.

---

## 9. Checkpoint e relatório esperado após cada bloco

O Codex deve entregar:

```text
Bloco [A|B|C|D|E] — [GREEN|BLOQUEADO]
Branch, commit-base, git status
Contrato e testes exercitados
Primeiro RED observado (quando aplicável) e causa real
Implementação mínima / arquivos alterados
Testes isolados, R02, R01 e full suite (contagem real)
Decisão de arquitetura e possíveis riscos
git diff --check, git diff --stat, untracked
Nenhum commit/push realizado
Pendências concretas e proposta para próximo bloco
```

A revisão humana confere o diff e autoriza a etapa seguinte. **Não saltar automaticamente entre blocos** sem aprovação, nesta estratégia de desenvolvimento.

---

## 10. Definition of Done (R02)

A R02 somente poderá ser declarada encerrada quando:

- [ ] PF/PJ existentes retornam `200` e snapshots completos, com 10 chaves públicas por tipo.
- [ ] PENDING, ACTIVE, REJECTED, INACTIVE são consultáveis.
- [ ] `trade_name` nulo é representado por `null` explícito.
- [ ] `created_at` e `updated_at` são timestamps UTC com `Z`.
- [ ] UUID malformado → `400 QIT000001`.
- [ ] UUID válido inexistente → `404 CLI0001`.
- [ ] Token ausente/inválido → `403 QIT000002`, com autenticação antes de lookup.
- [ ] Nenhum ID interno, ACCOUNT, CLIENT_STATUS_EVENT ou especialização indevida é embutido.
- [ ] GET sem `FOR UPDATE`, operações de escrita ou commit.
- [ ] Falhas internas/inconsistência não retornam sucesso parcial.
- [ ] Testes R02 verdes, R01 sem regressão, full suite verde.
- [ ] `git diff --check` sem erros; diff e documentação revisados.
- [ ] DTO considerado explicitamente, implementado somente se justificado.
- [ ] Revisão humana, commits e PR organizados corretamente em relação à R01 e `main`.

---

## 11. Próxima ação autorizada

**Somente Bloco A da R02:** auditar branch/baseline/contrato, criar um teste HTTP de PF criada pela R01 e consultada pela R02, observar RED, implementar a leitura mínima PF, confirmar GREEN, rodar regressão e entregar relatório. **Parar antes de B**.

O plano A–E serve como referência completa de futuro, mas **não autoriza executar antecipadamente B, C, D ou E**.
