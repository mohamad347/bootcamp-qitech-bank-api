# QA-001 + QA-002 + QA-003 — Plano e evidências de modularização, fixtures e ambiente

**Projeto:** `bootcamp-qitech-bank-api`
**Tipo:** refatoração exclusivamente de testes e documentação
**Branch sugerida:** `refactor/qa001-qa002-test-organization`
**Baseline histórica pré-R07:** `271 passed, 1 warning` após `12847c9`. **Baseline desta refatoração:** 356 casos antes/depois. **Regressão final reexecutada:** `356 passed in 51.25s` (12/10/2026).
**Status:** EXECUTADO — QA-001, QA-002 e QA-003 implementados e verificados. Evidências e ressalvas nas seções 9.1–9.6.

## 1. Objetivo, justificativa e limites

Concluir três itens de qualidade:

- **QA-001:** organizar testes de integração por rota e comportamento, especialmente módulos monolíticos extensos; facilitar navegação, revisão, manutenção e investigação de falhas.
- **QA-002:** revisar fixtures, builders/factories e helpers usados pelos testes, eliminando duplicações **somente quando existir ganho verificável**, sem gerar fixtures compartilhadas excessivas, dependências ocultas ou acoplamento entre rotas.
- **QA-003:** configurar imports e valores-padrão de ambiente antes da coleta pytest, respeitando as variáveis explicitamente fornecidas. Atenção: parte dos testes HTTP usa a base de desenvolvimento; executar somente em ambiente local controlado.

O inventário inicial encontrou módulos com centenas ou mais de mil linhas. A divisão priorizou responsabilidades e comportamentos; na varredura final foi adotado também o critério verificável de nenhum arquivo Python em `tests/` ultrapassar 400 linhas. A R03 já tinha organização adequada e foi preservada. Testes pequenos, como `test_healthcheck.py`, permaneceram onde estavam.

**Regra inegociável:** refatorar **a organização dos testes**, não a API. Nenhuma mudança em `src/`, `database/`, contrato HTTP, models, DTOs, repositories, locks, sessions, middleware, eventos, Docker/Compose, dependências ou implementação da R07/R08. O README e este plano refletem os caminhos reais. Os testes de segurança da R07 foram reorganizados, sem alteração das regras financeiras.

A R07 já foi integrada à `main` no PR #32 (`6eaf2e6`). A R08 permanece pendente nesta baseline. Não importar código de branches financeiras em andamento nem incluir os arquivos locais `docs/r07_updated.md` e `docs/BACKLOG_QUALIDADE_BAAS.md` no commit desta refatoração.

## 2. Inventário antes da execução — obrigatório

Antes de mover qualquer teste, coletar e registrar **o estado real da árvore**; nomes ilustrativos não devem ser considerados existentes. Inspecionar:

- `tests/integration/client/` — R01, R02, R03, R04, R05, R06 e R09, conforme paths reais.
- `tests/integration/test_healthcheck.py` — R10, avaliar se já está bem dimensionado.
- `tests/integration/database/` — preservar a suíte de schema; só tocar caso exista duplicação explicitamente relevante e comprovadamente segura, preferencialmente deixar intacta.
- `tests/conftest.py`, `tests/integration/conftest.py`, `tests/utils/` e todos os `conftest.py` e utilitários efetivamente existentes.
- Os testes da R07 já integrada à `main`, inclusive segurança financeira, foram auditados. O módulo de segurança foi reorganizado em `r07_safety/`. A R08 não estava integrada nesta baseline; não criar estruturas artificiais para ela.

Registrar antes/depois: número de arquivos, localização, quantidade de testes coletados, IDs/nome das funções de teste, parâmetros, marcações, fixtures locais/globais, helpers e arquivos com muitas linhas. Capturar o `pytest --collect-only` em local temporário **fora do repositório** ou descartável não versionado.

Inventário mínimo por módulo: `caminho original`, `quantidade de linhas`, `testes parametrizados`, `dependências/fixtures`, `destino proposto`, `justificativa`, `status da migração`.

## 3. Estratégia de organização

Sugestão **apenas ilustrativa** para a R04; adaptar à estrutura real e aos critérios de legibilidade:

```text
tests/integration/client/
  r03/                    # manter estrutura existente se já adequada
  r04/
    __init__.py           # somente se necessário para importabilidade
    conftest.py           # apenas fixtures com escopo estritamente r04
    helpers.py            # opcional; builders/leituras do banco específicas
    test_success.py
    test_validation.py
    test_business_rules.py
    test_concurrency.py
    test_rollback.py
  r05/                    # somente se divisão trouxer vantagem
  r06/
  r09/
tests/integration/test_healthcheck.py  # manter simples se adequado
```

Princípios:

1. Agrupar por **comportamento observável**, não por número fixo de linhas.
2. Nomear `test_*.py` para manter coleta pytest padrão.
3. Manter fixtures locais onde são usadas. Mover para `conftest.py` somente se compartilhadas por testes daquele diretório.
4. Evitar fixtures autouse novas, estado compartilhado, mutações globais e importações circulares.
5. Distinguir factories que criam CLIENT/ACCOUNT reais via API das que apenas constroem payloads. Não converter automaticamente uma na outra.
6. Preservar parametrizações, marcas, códigos de erros esperados, asserts negativos, timestamps, status, entidades e eventos.
7. Preservar mecanismos de sincronização, locks, `threading`, `pg_blocking_pids`, timeout e limpeza `finally` dos testes concorrentes.
8. Preservar fault injection com triggers/functions de rollback, isolamento por registro e limpeza em `finally`.
9. Não mover utilitários de teste para `src/` nem usar APIs privadas frágeis sem justificativa.
10. Minimizar churn: testes pequenos ou já bem organizados permanecem onde estão.

## 4. Invariantes de segurança e infraestrutura

O ambiente usa uma API local com PostgreSQL principal `bootcamp` (5432) e PostgreSQL de testes `bootcamp_test` (porta configurável, historicamente 5433; confirmar configuração atual), além de MockServer.

- **NÃO executar** `DROP`, `TRUNCATE`, reset de schemas, volumes ou dados da base principal `bootcamp`.
- Testes destrutivos de schema somente no banco de teste previamente validado e isolado.
- Não parar/reiniciar containers compartilhados apenas para reorganizar testes.
- Testes da API que criam registros persistentes devem continuar usando chaves exclusivas e nunca limpar dados de terceiros.
- Testes críticos de concorrência devem ser executados sem competição simultânea com outro desenvolvedor no mesmo banco, quando viável.
- Preservar exatamente as proteções atuais de isolamento e cleanup.

## 5. Critérios quantitativos e qualitativos de paridade

Antes da refatoração:

1. Executar `python -m pytest --collect-only -q` e salvar evidência.
2. Executar `python -m pytest -q` para obter baseline **real**. A referência histórica pré-R07 era 271 casos (com `MovedIn20Warning`); após a integração da R07, a coleta da refatoração passou a 356 casos.
3. Identificar explicitamente todos os testes de concorrência e rollback e a sua semântica.

Depois:

1. Executar novamente coleta e suíte completa; **não perder casos nem variantes parametrizadas**. Caminhos/IDs de nós pytest mudarão com a movimentação: verificar equivalência por nome e comportamento, não por string exata de node ID.
2. Preservar os 356 casos coletados no início desta refatoração, salvo adição justificada. Não alterar a quantidade de casos apenas para mascarar problemas.
3. Garantir que funções realmente sejam coletadas; detecção de testes ignorados é mais importante do que um simples `pytest -q` verde.
4. Preservar asserts, parametrizações e semântica dos fixtures; para cada origem, mapear destino(s).
5. Repetir testes concorrentes críticos R04/R06/R09 em processos pytest independentes quando houver alteração em seus arquivos/fixtures. Reportar quantidade real, falhas e tempos.
6. Executar `git diff --check`; fornecer `git status`, `git diff --stat` e inventário de removidos/adicionados/untracked.
7. Validar que não houve alteração em `src/`, contratos HTTP ou implementação de R07/R08. A reorganização de testes da R07 faz parte deste escopo.

## 6. Fluxo autônomo — Bloco 0 e blocos A–F

### Bloco 0 — Inspeção, baseline e mapa de riscos

- Confirmar branch `refactor/qa001-qa002-test-organization`, `git status`, `git log -1` e estado de arquivos untracked.
- Levantar todos os módulos, tamanho, testes, fixtures e imports.
- Capturar coleta e suíte (baseline). Registrar warning existente.
- Identificar diretórios que **não** devem ser alterados e arquivos compartilhados com R07/R08.
- Produzir mapa `origem → destino` antes de iniciar migrações.

### Bloco A — Plano fino e teste de caracterização

- Selecionar módulos com benefício real, priorizando os mais extensos (R04, R06, R09 etc. se confirmados).
- Definir categorias por comportamento com base nos testes existentes.
- Preservar a estrutura organizada da R03 se já satisfatória.
- Confirmar que fixtures/helper compartilhados não dependem de ordem de testes.
- **Não fabricar fase RED**: é reorganização. Caracterizar coleta e comportamento antes da mudança.

### Bloco B — Modularização QA-001

- Migrar testes para novos módulos com mudanças mínimas de conteúdo.
- Verificar `pytest --collect-only` após cada migração, evitando perder testes.
- Ajustar imports e caminhos, mantendo nomes de testes e seus parâmetros sempre que possível.
- Nenhum código de produção pode ser modificado.

### Bloco C — Fixtures/helpers QA-002

- Inspecionar duplicação concreta e refatorar apenas código auxiliar onde melhora entendimento.
- Preferir helpers por rota e factories explícitas. Criar helpers comuns só se houver benefício comprovado entre múltiplas rotas.
- Evitar autouse/global singleton, compartilhar Session ou banco entre testes ou ampliar escopos de fixture sem razão.
- Documentar o que foi centralizado e por quê, e o que deliberadamente permaneceu local.

### Bloco D — Testes especiais

- Validar status, eventos, contagens e snapshots físicos dos testes migrados.
- Repetir concorrência R04/R06/R09 e rollback com limpeza intacta.
- Não enfraquecer asserts nem reduzir os cenários de falha.
- Verificar que R03 e R10 continuam corretos.

### Bloco E — Auditoria e limpeza

- Revisar toda mudança de teste e import, marcação, fixture, helper e monkeypatch.
- Verificar a equivalência de cada origem para seus destinos.
- Remover imports inutilizados e duplicação introduzida, sem refatoração cosmética massiva.
- Verificar README apenas onde os caminhos de testes descritos mudaram.

### Bloco F — Regressão, documentação e entrega

- Executar coleta final, testes dirigidos, concorrência repetida e `python -m pytest -q` completo.
- Preencher este Markdown com resultados **reais** e mapping origem→destino.
- Executar `git diff --check`, `git status`, `git diff --stat` e inventário de arquivos untracked.
- Classificar achados CRITICAL/MAJOR/MEDIUM/LOW.
- Não fazer commit, push, PR ou merge.

## 7. Critérios de aceitação (Definition of Done)

- [x] Branch correta a partir de `main` atualizada e escopo sem alterações externas.
- [x] Baseline coletada, com contagem e duração reais.
- [x] Inventário e matriz origem→destino completos.
- [x] Testes movidos apenas onde existe benefício; R03 preservada quando adequada.
- [x] Nenhum teste ou cenário parametrizado perdido.
- [ ] Fixtures sem acoplamentos, efeitos globais ou dependências de ordem introduzidos.
- [ ] Concorrência/rollback R04/R06/R09 preservados e repetidos conforme necessidade.
- [x] Nenhuma modificação em código de produção ou implementação da R07/R08; testes de segurança R07 reorganizados.
- [x] Suíte completa GREEN, `git diff --check` limpo.
- [x] README e documentação coerentes; relatório final A–H entregue.
- [ ] Alterações locais prontas para auditoria independente; sem commit/push/PR.

## 8. Relatório final obrigatório — A–H

**A. Resultado geral:** APROVADO / APROVADO COM RESSALVAS / REPROVADO, com escopo exato.
**B. Execução blocos 0–F:** ações, mudanças, resultados e problemas encontrados.
**C. Mapa origem→destino:** tabela por rota, incluindo arquivos mantidos sem divisão e justificativa.
**D. Arquivos:** novos, movidos, removidos, modificados, fixtures e README; verificar produção intacta.
**E. Testes:** coleta antes/depois, baseline, testes dirigidos, concorrência repetida, regressão completa, tempos, warnings e falhas reais.
**F. Auditoria:** cobertura, coleta pytest, isolamento, cleanup, flakiness, fixtures, segurança e findings.
**G. Integração:** risco de conflitos com Moha/R07/R08 e estratégia de merge posterior.
**H. Git e decisão:** branch, status, diff, untracked, revisão pendente; declaração PRONTO PARA AUDITORIA FINAL E COMMIT ou NÃO PRONTO.

## 9. Considerações de integração

Esta refatoração é independente das regras financeiras. A R07 já está integrada e seus testes de segurança foram reorganizados sem mudança de comportamento. Após a integração da R08, realizar auditoria integrada e avaliar sua organização de testes. O QA final end-to-end do BaaS permanece tarefa posterior e distinta.

**Registro de evidências:** preencher abaixo ao concluir os blocos, sem apagar este planejamento.

### 9.1 Resultado do Bloco 0

**Executado em 12/10/2026.** Branch confirmada: `refactor/qa001-qa002-test-organization`, com `6eaf2e6` no HEAD e os documentos locais `docs/BACKLOG_QUALIDADE_BAAS.md`, `docs/r07_updated.md` e este plano preservados como untracked. A coleta inicial encontrou **356 testes** em 4.25s; a referência histórica de 271 precedia a integração da R07.

O inventário inicial identificou módulos extensos em R01, R02, R04, R05, R06, R07 e R09. A primeira etapa tratou R04/R06/R09; a varredura definitiva posterior ampliou o escopo para toda a árvore e também dividiu R01, R02, R05, o suporte da R04 e a segurança transacional da R07. R03, R10, unitários e schema foram preservados quando já coesos e abaixo do limite.

Foi encontrada uma lacuna de QA-003: processos pytest novos dependiam de `TEST_DATABASE_URL` previamente exportada. A primeira regressão sem essa variável produziu 123 erros de fixture, sem indicar defeito da API. O `tests/conftest.py` passou a definir, apenas quando ausente, o URL seguro do banco descartável `bootcamp_test` em `127.0.0.1:5433`; variáveis explícitas continuam tendo precedência.

### 9.2 Resultado dos Blocos A–F

**A–C executados.** A caracterização não exigiu RED artificial: esta é uma refatoração de organização. Os 22 testes unitários de hash/tarifa passaram em processo novo com `APP_ENV=test` e sem variáveis de aplicação exportadas. Foram removidas as inserções locais de `sys.path` desses módulos, pois o `tests/conftest.py` agora disponibiliza `src/` antes da coleta.

**B (QA-001):** R01, R02, R04, R05, R06, R09 e a segurança transacional R07 foram efetivamente modularizadas; R03, R10 e módulos já coesos foram preservados. Os suportes de R04, R06 e R09 foram divididos em pacotes `support/`. A coleta após a divisão permaneceu em 356 casos; a execução intermediária dirigida de R04/R06/R09 passou com **107 testes em 11.71s**.

**C (QA-002):** não foi criada fixture global de banco ou factory genérica. Fixtures, builders e cleanup específicos permaneceram locais às rotas; os suportes de R04/R06/R09 foram separados por responsabilidade. A centralização de coleta/ambiente em `tests/conftest.py` (QA-003) não compartilha sessões nem estado entre testes.

**D–F (etapa intermediária):** healthcheck **12 testes em 4.24s** sem variáveis exportadas; concorrência crítica R04 em três processos independentes (2.31s, 1.67s e 1.73s); regressão intermediária **356 testes em 38.47s**. Após a modularização definitiva, houve regressões adicionais; ver 9.4 e 9.6.

### 9.3 Matriz origem→destino executada

| Origem | Destino | Decisão |
| --- | --- | --- |
| `tests/integration/client/test_r01_create_client.py` | `r01/test_success.py`, `test_authentication.py`, `test_documents.py`, `test_domain_rules.py`, `test_payload_validation.py`, `test_uniqueness_and_normalization.py`, `support.py` | 40 funções de teste separadas por contrato; fixture/payload local preservado. |
| `tests/integration/client/test_r01_persistence.py` | `r01/test_persistence.py` | Conteúdo preservado e agrupado com a rota. |
| `tests/integration/client/test_r02_get_client.py` | `r02/support.py`, `test_success.py`, `test_errors.py`, `test_statuses.py` | Snapshot, erros/autenticação e leitura de estados separados. |
| `tests/integration/client/test_r04_create_account.py` | `r04/support/`, `test_success.py`, `test_validation.py`, `test_business_rules.py`, `test_concurrency.py`, `test_atomicity.py` | Criação, contrato, erros, elegibilidade/unicidade, locking e rollback separados. |
| `tests/integration/client/test_r05_get_account.py` | `r05/support.py`, `test_snapshots.py`, `test_read_only.py`, `test_errors.py` | Snapshot, ausência de mutação e erros separados. |
| `tests/integration/client/test_r06_patch_account.py` | `r06/support/`, `test_transitions.py`, `test_validation.py`, `test_business_rules.py`, `test_concurrency.py`, `test_atomicity.py` | Lifecycle de ACCOUNT dividido por transição, validação, regras, locks e rollback. |
| `tests/integration/client/test_r09_patch_client.py` | `r09/support/`, `test_transitions.py`, `test_validation.py`, `test_business_rules.py`, `test_concurrency.py`, `test_atomicity.py` | Lifecycle de CLIENT dividido por transição, validação, integração ACCOUNT, concorrência e rollback. |
| `tests/integration/transaction/test_r07_transaction_safety.py` | `r07_safety/support.py`, `test_atomicity.py`, `test_history.py` | Fault injection/consultas, rollback e histórico separados. |
| `tests/integration/client/r03/` | sem alteração | Já segmentada por comportamento. |
| `tests/integration/transaction/` (demais arquivos) | preservados | Segurança R07 foi dividida em `r07_safety/`; módulos financeiros restantes já estavam segmentados. |
| R10 e schema | sem alteração | Já estavam coesos; R01, R02 e R05 foram modularizadas nesta entrega. |

### 9.4 Testes e conclusão final

Coleta final: **356 testes**. Regressão completa após a modularização integral: **356 passed in 35.85s**; nova regressão executada pelo responsável após correções documentais: **356 passed in 51.25s**. Não houve perda de caso ou variante parametrizada registrada. `git diff --cached --check` executado sem erros; não houve alteração em `src/`, schema, Compose ou R08. Ressalva operacional: testes HTTP continuam gravando dados exclusivos no banco local da API, como já ocorria; executar apenas em ambiente controlado.

### 9.5 Varredura definitiva de toda a suíte

Foram auditados **65 arquivos Python** antes da etapa definitiva e **100 arquivos Python** na estrutura final. Os cinco arquivos acima de 400 linhas foram obrigatoriamente tratados: R01 (880), suporte R04 (727), R02 (560), segurança transacional R07 (423) e R05 (411). R06/R09, embora abaixo de 400 após a primeira divisão, também tiveram seus suportes separados por responsabilidade. O resultado automático final foi **zero arquivos acima de 400 linhas**.

Decisões por área:

- **R01:** criação dividida em sucesso, autenticação, documentos, domínio, payload e unicidade/normalização; persistência movida para o diretório da rota.
- **R02:** suporte local e módulos de sucesso, erros e estados.
- **R03:** preservada; já organizada por decisões, elegibilidade, provider e segurança transacional.
- **R04:** suporte convertido em pacote com assertions, banco, clientes/estados, concorrência e fault injection.
- **R05:** suporte local e módulos de snapshots, read-only e erros.
- **R06/R09:** testes comportamentais preservados e suportes convertidos em pacotes coesos.
- **R07:** suíte financeira preservada por comportamento; o antigo módulo de segurança foi dividido em atomicidade e histórico com suporte local. O módulo de concorrência financeira permaneceu com 400 linhas por possuir responsabilidade única.
- **R10, unitários e database:** auditados e preservados, pois são coesos e abaixo do limite.

Regressões finais: unitários **22 passed in 3.72s**; client **201 passed in 27.07s**; transaction **63 passed in 6.63s**; concorrência/idempotência/rollback dirigidos **18 passed in 4.39s**; suíte completa **356 passed in 35.85s**.

Vinte maiores arquivos finais:

| Linhas | Arquivo |
| ---: | --- |
| 400 | `tests/integration/transaction/test_r07_financial_concurrency.py` |
| 363 | `tests/integration/transaction/test_r07_transfer_errors.py` |
| 363 | `tests/integration/client/r04/support/clients.py` |
| 344 | `tests/integration/transaction/support.py` |
| 343 | `tests/integration/client/r03/support.py` |
| 301 | `tests/integration/client/r05/support.py` |
| 300 | `tests/integration/client/r02/support.py` |
| 287 | `tests/integration/transaction/test_r07_deposit.py` |
| 282 | `tests/integration/database/test_client_schema.py` |
| 266 | `tests/integration/client/r01/test_persistence.py` |
| 259 | `tests/integration/transaction/test_r07_idempotency_concurrency.py` |
| 234 | `tests/integration/client/r04/test_success.py` |
| 226 | `tests/integration/transaction/test_r07_transfer.py` |
| 217 | `tests/integration/client/r01/test_payload_validation.py` |
| 204 | `tests/integration/transaction/r07_safety/test_atomicity.py` |
| 201 | `tests/integration/database/test_account_schema.py` |
| 197 | `tests/integration/client/r01/test_uniqueness_and_normalization.py` |
| 173 | `tests/integration/test_healthcheck.py` |
| 173 | `tests/integration/client/r01/test_success.py` |
| 173 | `tests/integration/client/r04/test_business_rules.py` |


### 9.6 Verificação independente e status para commit (12/10/2026)

- Patch auditado: **71 arquivos** no staging (README, plano, `tests/conftest.py`, reorganização dos testes e dois módulos unitários); **sem alterações em `src/`**.
- Comparação estrutural independente dos módulos migrados: **107 funções de teste com corpos e parametrizações preservados** no conjunto inspecionado.
- Regressão completa informada pelo terminal após limpeza de whitespace: **356 passed in 51.25s**.
- `git diff --cached --check`: **sem saída**, portanto sem erros de whitespace no staging.
- `docs/BACKLOG_QUALIDADE_BAAS.md` e `docs/r07_updated.md` permanecem **untracked**, fora do commit.
- Ressalvas para melhorias posteriores: alguns suportes usam importações `*`; `tests/conftest.py` fornece URLs locais padrão e parte da suíte de integração opera sobre a base local de desenvolvimento. A futura CI deve impor ambiente de banco explicitamente isolado.
- **Decisão técnica:** pronto para commit/PR da refatoração após revisão final do staging. A aprovação do merge é decisão separada.
