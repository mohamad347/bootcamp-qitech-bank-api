# R01–R04 — Plano completo de auditoria e padronização de DTOs

**Projeto:** `bootcamp-qitech-bank-api`
**Tipo:** refatoração interna orientada a contrato, sem feature pública nova
**Branch prevista:** `refactor/r01-r04-dto-standardization`
**Baseline confirmada após R10 na `main`:** 271 testes aprovados, 1 warning não bloqueante
**Paralelismo:** R07 em desenvolvimento por outro integrante; R08 em sequência
**Estado deste documento:** EXECUTADO / APROVADO

---

## 1. Objetivo, limites e princípio de decisão

O objetivo NÃO é adicionar uma classe DTO para cada rota a qualquer custo. O objetivo é **auditar o fluxo de entrada e saída de R01–R04** e, quando houver ganho concreto em clareza, segurança, consistência ou separação de responsabilidades, **mover a projeção/normalização de dados para DTOs simples e coerentes com os padrões já presentes** nas R05 (`AccountDTO`), R06 (`AccountPatchDTO`) e R09 (`ClientPatchDTO`).

**Invariante principal:** a refatoração não altera absolutamente nenhum efeito observável da API: método/caminho, status HTTP, corpo JSON (campos, tipos, valores, nullability, timestamps e formato), autenticação, erros, precedência de validações e efeitos persistidos no PostgreSQL.

A decisão da R04 em seu plano original é explícita: **a resposta tem apenas três campos e um `dict` simples pode ser suficiente**. Isso é arquiteturalmente aceitável. Não transformar DTO em burocracia nem duplicar a mesma lógica em várias camadas.

### Fora do escopo, salvo necessidade demonstrada e autorizada

- Alterar regras de negócio de R01–R04 ou contratos v1.1.
- Modificar R05, R06, R07, R08, R09 ou R10; R07/R08 pertencem a outro integrante.
- Alterar saldos, transferências, idempotência, tarifas ou regras de transação financeira.
- Mudar tabelas, migrations, `database/database.sql`, models, constraints ou índices.
- Mudar locks, commits, rollbacks, gerenciamento de sessão, ordem de aquisição de locks ou histórico de eventos.
- Trocar autenticação, mudar `SchemaHandler` ou envelopes/códigos de erro por motivos cosméticos.
- Trocar bibliotecas de serialização ou adicionar Pydantic/dataclasses como dependência obrigatória sem justificativa.
- Refatorar modules de uso compartilhado pela R07 para atender somente a um estilo de código.

### Critérios para introduzir um DTO

Introduza DTO **apenas se** for útil em um ou mais aspectos, e prove com testes: (a) delimitar campos públicos de entidade ORM; (b) centralizar transformação repetida de datas/tipos/status; (c) reduzir montagem de dicionários misturada com decisões de domínio; (d) diferenciar PF/PJ com clareza; (e) padronizar projeções já semelhantes no repositório.

Mantenha um `dict` local quando a projeção for trivial, única e clara e a extração não trouxer benefício. Não mova cálculos de domínio para DTOs. Não coloque SQL, Session, consultas, commit ou efeitos colaterais em DTOs.

**Saídas do bloco 0:** decisão justificada **DTO necessário / DTO opcional / DTO desnecessário** para cada rota e para entrada vs saída, com exemplos de código real e referências aos testes existentes. Não presuma a conclusão antes da inspeção.

---

## 2. Fontes de verdade e contexto do repositório

Leia e use, nessa ordem de prioridade:

1. Implementação atual da `main` e testes executáveis (comportamento real); diferenças contratuais devem ser auditadas, não mascaradas.
2. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md`: §§4–5 e §§6–9 (R01–R04).
3. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md`: F01 e passos de R03/R04; regras transversais de atomicidade.
4. `docs/RFC_v1_BaaS_Simplificado_QITech.md` e `docs/ERD_v1_1_FINAL_BaaS_QITech.md`.
5. `docs/R02_Plano_Completo_Testes_e_Implementacao.md`, `tests/integration/client/r03/`, `docs/R04_Plano_Completo_Testes_e_Implementacao.md`.
6. `docs/R05_Plano_Completo_Testes_e_Implementacao.md`, `docs/R06_Plano_Completo_Testes_e_Implementacao.md`, `docs/R09_Plano_Completo_Testes_e_Implementacao.md` para padrões DTO recentes.
7. `README.md` atualizado — status do projeto, instruções de testes e escopo do trabalho paralelo.

Inspecione efetivamente `src/app.py`, `src/resources/`, `src/controllers/`, `src/repositories/`, `src/models/`, `src/dtos/`, `src/schemas/`, `src/errors/`, `src/middlewares/`, `tests/integration/client/` e utilitários de teste. O ZIP/snapshot histórico não substitui a branch atual.

---

## 3. Inventário da fronteira HTTP por rota (contrato que NÃO pode mudar)

### R01 — `POST /client`

- Autenticação `INTERNAL-TOKEN`; sucesso HTTP **201**.
- Entrada PF `INDIVIDUAL` ou PJ `COMPANY`, com validação estrutural já definida pelos schemas existentes.
- Resposta pública com exatamente `client_key`, `client_type`, `status` (`PENDING`).
- Cria CLIENT + especialização PF/PJ + CLIENT_STATUS_EVENT no mesmo commit.
- Normalização de CPF/CNPJ, e-mail, timezone, datas e dados cadastrais continua idêntica; não mover regras de validação de domínio para DTO sem necessidade.
- Evitar que DTO realize acesso a atributos ORM expirados depois de `commit`; se a projeção hoje ocorre antes do commit, preservar ou obter dados de forma segura, sem consultas adicionais desnecessárias.
- Cobrir duplicidade de CPF/CNPJ/e-mail, menoridade, timezone inválido, auth e corpo inválido. Preservar erros e status precisos da implementação.

**Decisão a registrar:** DTO de resposta por três campos traz benefício concreto? DTO de entrada é útil ou duplicaria o JSON Schema e o controller?

### R02 — `GET /client/{client_key}`

- Autenticação `INTERNAL-TOKEN`; resposta HTTP **200** para PF e PJ em todos os status legíveis.
- Snapshot público: `client_key`, `client_type`, `email`, `timezone`, `status`, campos específicos PF/PJ e `created_at`/`updated_at` em ISO UTC com `Z`, preservando o formato real.
- PF: `cpf`, `full_name`, `birth_date`.
- PJ: `cnpj`, `legal_name`, `trade_name` (incluindo `null` quando ausente).
- Sem IDs internos, ACCOUNT ou histórico de eventos; sem escritas ou efeitos colaterais.
- Preservar inclusões/omissões: **não transformar uma chave ausente em `null` ou vice-versa**.
- Preservar perfis de carregamento ORM e número de consultas quando pertinente; evitar N+1 ou consultas ocultas em DTO.

**Decisão a registrar:** candidato mais provável para DTO de resposta por exigir mapeamento de PF/PJ, datas, enums e lista de campos públicos. Verificar se já há mapper/DTO reutilizável antes de criar um novo.

### R03 — `POST /client/{client_key}/analysis`

- Autenticação `INTERNAL-TOKEN`; decisão `APPROVE`/`REJECT`, `reason` conforme contrato e schema já implementados.
- Resposta HTTP **200** com exatamente `client_key` e `status` resultante.
- Chamadas ao Analysis Provider/MockServer, timeout, tratamento de erros, payload do provider, revalidação sob CLIENT FOR UPDATE, transições e eventos **não devem mudar**.
- A representação da requisição do **provider externo** é uma fronteira distinta do DTO público: não unificar automaticamente.
- Preservar prioridade de erro e política de concorrência, especialmente a ausência de lock durante HTTP externo.

**Decisão a registrar:** evitar DTO público de dois campos se adicioná-lo significar complexidade sem ganho; se já existir projeção repetida, avaliar mapper compartilhado com cautela.

### R04 — `POST /client/{client_key}/account`

- Autenticação `INTERNAL-TOKEN`; body ausente conforme contrato; HTTP **201**.
- Resposta exata: `account_key`, `status` (`ACTIVE`), `balance_cents` (`0`).
- CLIENT precisa estar ACTIVE e nunca ter tido ACCOUNT, inclusive CLOSED.
- Exclusividade CLIENT→ACCOUNT preservada pela trava CLIENT FOR UPDATE e constraint UNIQUE.
- ACCOUNT_STATUS_EVENT inicial em mesma transação e ausência de segundo commit.
- Atenção ao DTO criado pela R05 (`AccountDTO`): ele representa **GET** com seis campos e não pode ser reutilizado diretamente na R04 se incluir campos extras.

**Decisão a registrar:** o plano original da R04 aprovou `dict` simples; manter, salvo ganho claro e testes demonstrando que a projeção de três campos merece extração.

---

## 4. Padrão arquitetural alvo — mínimo e consistente

```text
Request
  -> middleware de autenticação/contexto
  -> Resource + SchemaHandler (validação estrutural)
  -> Controller (validação de domínio, orquestração, transação)
  -> Repository + models (persistência / consultas / locks)
  -> DTO ou mapper puro, se justificado (projeção pública)
  -> jsonable_encoder + JSONResponse (status e envelope originais)
```

Regras de implementação:

- Preferir APIs DTO compatíveis com o padrão atual (`obj_to_response`, `obj_to_dict` etc.) conforme inspeção real. Não renomear globalmente interfaces em outras rotas.
- Exportar símbolos novos em `src/dtos/__init__.py` **de forma aditiva**, preservando imports existentes da R05/R06/R09 e os que possam ser criados pela R07.
- DTO recebe entidades/dados já carregados; nunca abre Session, não faz query, não recebe `Context` e não faz commit.
- Não serializar objetos ORM arbitrariamente; usar allowlist explícita de campos públicos.
- Não remover validações do JSON Schema nem converter erros de domínio em `422` automático.
- Se houver normalização de entrada, validar que ordem e regras ficam iguais (por exemplo trim, CPF/CNPJ, timestamps). Não transportar regra de negócio para DTO sem necessidade.
- Não modificar função compartilhada para encaixar novo DTO se puder isolar a extração na rota interessada.
- Revisar perfis PF/PJ, `None`, timezone `Z`, `Decimal`, `UUID`, enum e `datetime` contra os contratos atuais.
- Evitar import circular entre resources/controllers/dtos/models e preserve testabilidade.
- Se uma melhoria exigir mudança funcional, registrar como sugestão para PR separado e **não implementá-la** nesta tarefa.

---

## 5. Estratégia de testes — antes e depois

### Baseline e comparação contratual

1. Confirmar branch, `main` de origem, diferenças com remoto e `git status` antes das mudanças.
2. Garantir API e infra saudáveis; identificar PostgreSQL principal (porta 5432) e descartável (porta 5433 ou valor de `TEST_DB_PORT`).
3. Executar **suíte completa antes** da refatoração, observando baseline histórica de **271 passed, 1 warning**. Se a baseline atual for diferente, investigar e registrar em vez de forçar 271.
4. Criar testes de caracterização **antes** das extrações, sempre que houver lacuna relevante. Se os testes já existirem e forem suficientes, registrar GREEN inicial em vez de fabricar RED.
5. Fixar a forma da resposta via asserts de `set(response.keys())`, tipos, serializações, valores `null`, status HTTP e códigos de erro. UUIDs e timestamps dinâmicos devem ser validados estruturalmente e comparados por fixture controlada, não por valor imprevisível.
6. Validar no PostgreSQL que inserts/updates/events/locks da R01, R03 e R04 não sofreram alterações. R02 permanece somente leitura.
7. Repetir após cada grupo de alterações e no final; comparar testes e efeitos observáveis antes/depois.

### Matriz mínima de regressão por rota

| Caso | R01 | R02 | R03 | R04 |
| --- | :---: | :---: | :---: | :---: |
| Success HTTP e conjunto exato de chaves públicas | ✓ | ✓ | ✓ | ✓ |
| Tipos/formatos de UUID/status/datas/saldo | ✓ | ✓ | ✓ | ✓ |
| PF e PJ | ✓ | ✓ | ✓ | ✓ |
| Campos opcionais/nulos | ✓ | ✓ | conforme entrada | — |
| Auth antes de validações | ✓ | ✓ | ✓ | ✓ |
| UUID/body inválido e erros oficiais | conforme rota | ✓ | ✓ | ✓ |
| Não exposição de IDs/relationships internos | ✓ | ✓ | ✓ | ✓ |
| Eventos corretos, atomicidade e rollback | ✓ | somente leitura | ✓ | ✓ |
| Lock order, concorrência e estados incompatíveis | verificar baseline | somente leitura | ✓ | ✓ |
| Regressão R05, R06, R09, R10 | \- | ✓ | ✓ | ✓ |

A tabela não substitui os testes existentes. **Não criar casos redundantes sem valor**; a matriz é cobertura de comportamento, não meta artificial de contagem.

### Testes unitários de DTO quando realmente úteis

- Projeção a partir de objetos fictícios ou entidades ORM materializadas sem banco.
- Entradas `UUID`, datas e status, atributos nulos, PF/PJ, máscara allowlist.
- DTO não executa query, nem tem dependência de `Context` ou `Session`.
- Não comparar `dict` não ordenado por serialização textual; comparar payload JSON por conteúdo com formato verificado.
- Testar preservação do contrato em integração real, não substituir testes HTTP por testes unitários.

### Convivência com R07 em desenvolvimento

- O integrante responsável por R07 é dono da feature financeira; não tocar em arquivos de R07/R08.
- `src/dtos/__init__.py` e, se necessário, imports de controllers/resources podem ser pontos de conflito textual. Revisar diff antes do PR.
- Não criar `TransactionDTO`, não usar imports de DTO financeiro ainda não integrado, não assumir branch do Moha como baseline.
- Se R07/R08 chegarem à `main` antes da integração desta PR, atualizar a branch com a `main` e executar regressão ampliada; revisar importações e resolução de conflitos.
- Comunicação mínima útil à equipe: “Refatoração R01–R04 exclusivamente em DTO/projeção pública; não altera contrato ou domínio; possíveis conflitos em `src/dtos/__init__.py`.”

---

## 6. Execução TDD em blocos 0 e A–F

### BLOCO 0 — Inspeção e matriz de decisão

**Ações:** verificar branch e status, ler fontes oficiais, abrir controllers/resources/repositories/testes das quatro rotas, listar mapeamentos existentes, DTOs reutilizáveis e dependências R07. Executar a baseline e registrar os resultados reais.

**Entregável:** tabela com oito decisões (entrada/saída de R01, R02, R03, R04), cada uma com `EXISTENTE`, `INTRODUZIR`, `MANTER DICT` ou `NÃO APLICÁVEL`, justificativa técnica e arquivos envolvidos. Caso nenhuma mudança seja justificada, a tarefa pode ser concluída como **auditoria sem alteração de produção**.

**Gate:** não iniciar implementação enquanto não estiver claro o contrato pré-refatoração e a fronteira entre DTO e regras de domínio.

### BLOCO A — Caracterização do comportamento atual

**Ações:** revisar cobertura existente, acrescentar somente testes de contrato necessários, executar testes direcionados para estabelecer GREEN inicial ou RED apenas se um defeito real for revelado. Registrar respostas reais sem dados sensíveis.

**Entregável:** evidência de cobertura R01–R04; relatório de lacunas existentes e testes novos justificados.

**Gate:** não alterar o contrato para satisfazer testes; testes devem codificar o comportamento oficial já aprovado.

### BLOCO B — Extrações mínimas e justificadas

**Ações:** extrair projeção de resposta ou normalização para DTOs puros somente onde houver benefício; adaptar controller/resource com diffs mínimos. Se R02 tiver projeções PF/PJ, manter campos separados e formatos atuais. Preservar R03/provider e R04/lock. Evitar criar DTO de request quando SchemaHandler já resolve entrada de forma clara.

**Entregável:** código legível, sem queries em DTO; testes direcionados continuam GREEN.

**Gate:** payloads e persistência idênticos; proibir changes de models/banco/contratos.

### BLOCO C — Cobertura de contrato e integridade

**Ações:** testar todos os status e especializações relevantes; validar tipos, datas, nulls, erro, auth precedence e inexistência de efeitos colaterais. Para R01, R03 e R04, confrontar eventos, status e cardinalidade antes/depois.

**Entregável:** matriz de compatibilidade preenchida com evidências concretas.

### BLOCO D — Concorrência, regressão e efeitos persistidos

**Ações:** executar regressões dirigidas R03×R04, testes de concorrência R04 e R06/R09 que compartilham CLIENT/ACCOUNT. Não criar novos testes de race se código de locking não foi alterado e cobertura existente é adequada; registrar execução dos testes existentes. Repetir casos críticos se mudanças puderem afetar carga/flush/lazy load.

**Entregável:** ausência comprovada de alteração em locks, commit, eventos, saldo e status; exceções sempre fazem rollback como antes.

### BLOCO E — Refatoração, segurança e análise de diff

**Ações:** revisar imports/export em `dtos/__init__.py`, tipagem, duplicação, campos internos, N+1, timezone `Z`, nullability, padrão dos DTOs R05/R06/R09. Verificar `git diff` para detectar escopo indevido. Reverter qualquer refatoração que não justifique o custo.

**Entregável:** quadro de decisões adotadas e rejeitadas, riscos e limites.

### BLOCO F — Regressão integral, README e entrega

**Ações:** executar testes R01–R04, regressões R05/R06/R09/R10, suíte completa, `git diff --check`, `git diff --stat`, `git status` e inventário de untracked; atualizar este documento com tempos e contagens reais.

**README:** incorporar o `README.md` atualizado que acompanha este plano, **sem alterar o status de R07/R08**. Ajustar somente a frase da auditoria de DTOs para refletir o que de fato foi feito (DTOs criados onde necessários, ou todos mantidos após inspeção). Caso existam merges novos, atualizar as informações apenas conforme evidência no Git.

**Entregável:** código e documentação prontos para auditoria independente, **sem commit/push/PR automático**.

---

## 7. Cuidados com infraestrutura e Git

- Branch prevista: `refactor/r01-r04-dto-standardization`, criada a partir da `main` após R10.
- **O banco principal da API é `bootcamp` em 5432**; o schema de testes roda em `bootcamp_test` em 5433 (ou porta configurada).
- `TEST_DATABASE_URL` deve apontar exclusivamente para a instância descartável. NUNCA executar reset de `public`, DROP/TRUNCATE, apagar volumes ou testes destrutivos na base principal.
- Testes HTTP podem gerar CLIENTs e ACCOUNTs únicos no banco principal conforme padrão existente; não limpar dados de outras pessoas.
- Não desligar serviços compartilhados que estejam atendendo à R07 do outro integrante.
- Manter mudanças locais sem commit/push; revisar diff, conflito e regressão antes de integrar.
- Para reproduzir testes: `python -m pytest -q`; registrar contagens e durações reais. O baseline **271** é histórico, não um alvo obrigatório.
- Se surgirem bloqueios documentais, inconsistências de contrato ou necessidade de modificar locks/schemas físicos, **interromper a mudança funcional** e relatar a decisão necessária.

---

## 8. Definition of Done — critérios de aceite

- [x] Bloco 0 concluído com inventário real e decisão justificada por rota (entrada/saída).
- [x] Nenhum DTO novo desnecessário; decisão de manter `dict` é aceita quando justificada.
- [x] Campos, status HTTP, códigos de erro, formato de data/null e precedência de auth iguais.
- [x] R01 PF/PJ, R02 PF/PJ, R03 APPROVE/REJECT, R04 OPEN equivalentes à baseline.
- [x] Histórico de status, commits, locks, eventos e invariantes financeiros inalterados.
- [x] Nenhuma consulta/commit/banco em DTOs novos.
- [x] Sem alteração nas rotas R05–R10 ou no trabalho paralelo de R07/R08.
- [x] Testes direcionados e regressão integral executados com resultados reais.
- [x] README atualizado com status verdadeiro e plano marcado conforme execução.
- [x] `git diff --check` limpo (inclusive whitespace dos novos `.md`).
- [x] Arquivos novos e já rastreados inventariados; sem commits/push/PR.
- [x] Auditoria final A–H entregue, com findings CRITICAL/MAJOR/MEDIUM/LOW.

---

## 9. Registro de execução (preencher pelo Codex; não inventar)

| Marco | Resultado/tempo | Evidência/observações |
| --- | --- | --- |
| Branch / HEAD inicial | `refactor/r01-r04-dto-standardization` / `87e153e` | Árvore continha `README.md` modificado e este plano não rastreado; ambos eram insumos esperados e foram preservados. |
| Baseline da suíte completa | `271 passed, 1 warning in 125.95s` | Warning conhecido: `MovedIn20Warning` de `declarative_base()`. |
| Inventário DTOs existentes | `AccountDTO`, `AccountPatchDTO`, `ClientAnalysisDTO`, `ClientPatchDTO`, `SampleEntityDTO` | R02 não tinha DTO de snapshot; R01/R04 usavam `dict` mínimo. |
| R01 input/output | Schema existente / manter `dict` | JSON Schema já cobre formato; a resposta tem três campos e é capturada antes do commit para evitar atributos ORM expirados. |
| R02 input/output | Path sem DTO / `ClientDTO` introduzido | DTO puro separa snapshots PF/PJ, allowlist pública e serialização UTC `Z`; controller preserva busca e inconsistências. |
| R03 input/output/provider | Sem body / `ClientAnalysisDTO` existente | Mantido; DTO já separa dados do provider da resposta pública e nenhuma chamada externa ou lock foi alterado. |
| R04 input/output | Não aplicável / manter `dict` | Sem body; resposta de três campos continua explícita no controller, conforme decisão original. |
| Caracterização e GREEN inicial/RED real | GREEN inicial | Os testes HTTP existentes já fixavam contratos relevantes; nenhum RED artificial foi fabricado. |
| Alterações implementadas (se justificadas) | `ClientDTO`, export e uso somente no snapshot R02 | Nenhum DTO de request novo; nenhum model, schema físico, repository ou resource foi alterado. |
| Regressões de R01–R04 | `199 passed, 1 warning in 34.39s` | Inclui R01, R03, R04 e regressões R05/R06/R09/R10; R02 direcionada: `14 passed in 6.50s`. |
| Regressões R05/R06/R09/R10 | Incluídas no comando de 199 testes | Nenhuma regressão observada. |
| Suíte final completa | `271 passed, 1 warning in 48.28s` | Sem falhas ou skips. |
| `git diff --check`, status, untracked | Sem erros; plano e `ClientDTO` permanecem não rastreados até revisão | Alterados: README, controller e export DTO; sem commit/push/PR. |
| Riscos de integração com R07/R08 | Baixo | Possível conflito textual apenas em `src/dtos/__init__.py`; nenhuma rota financeira foi tocada. |
| Decisão final / PR-ready | APROVADO | Pronto para auditoria humana antes de commit. |

---

## 10. Relatório final obrigatório ao usuário — A–H

**A. Resultado geral:** APROVADO / APROVADO COM RESSALVAS / REPROVADO; informar se houve alterações ou apenas auditoria.

**B. Blocos 0–F:** objetivo, ações, evidência e resultado por bloco.

**C. Matriz de DTOs R01–R04:** oito decisões input/output, mapeamentos efetivamente criados ou mantidos, justificativas e aderência ao contrato público.

**D. Inventário completo de arquivos:** alterados/novos/revertidos, com justificativa; confirmar ausência de mudança fora do escopo.

**E. Testes:** baseline, caracterização, casos novos, regressões específicas, integração, suíte completa; números e tempos reais, warnings e skips.

**F. Auditoria técnica:** compatibilidade de contrato, segurança, ORM/lazy loads, pureza de DTO, locks/eventos/persistência, findings CRITICAL/MAJOR/MEDIUM/LOW.

**G. Convivência com R07/R08:** conflitos possíveis, arquivos compartilhados, decisões que exigem coordenação; nenhuma modificação de rota financeira.

**H. Git e entrega:** branch/HEAD, `git status`, diff, untracked, README, riscos, indicação objetiva `PRONTO PARA AUDITORIA FINAL E COMMIT` ou `NÃO PRONTO`.

**Regra final:** a qualidade da arquitetura depende de remover responsabilidades indevidas, não de maximizar a quantidade de arquivos DTO.
