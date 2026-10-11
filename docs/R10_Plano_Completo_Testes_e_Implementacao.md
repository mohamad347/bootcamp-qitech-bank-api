# R10 — Plano Completo de Auditoria, Testes e Implementação Condicional
## `GET /health_check` | BaaS Simplificado — Bootcamp QI Tech 2026

**Projeto:** `bootcamp-qitech-bank-api`
**Documento canônico no repositório:** `docs/R10_Plano_Completo_Testes_e_Implementacao.md`
**Branch esperada:** `feature/r10-healthcheck-audit` a partir da `main` pós-merge da R09
**Baseline histórica reportada:** **265 passed in 27.68s** na `main` após R09; repetir e registrar o resultado real
**Estado inicial:** PLANEJADO / NÃO EXECUTADO; a implementação da R10 preexiste e deve ser auditada antes de alterada
**Método:** Bloco 0 — inspeção; A — RED somente se houver defeito; B — correção mínima somente se necessária; C — contrato e segurança; D — independência de infraestrutura; E — auditoria e refactor mínimo; F — regressão e relatório.

> **Princípio da R10: audit-first, change-only-if-needed.** Ao contrário das rotas PATCH, esta rota já existe. Se estiver conforme, **não criar commit artificial de produção**, não alterar a rota, middleware, banco ou API para satisfazer metas de quantidade de código. Adicionar testes e documentação apenas onde houver cobertura útil. Não inventar RED quando o comportamento já é GREEN.

---

## 0. Fontes de verdade, inventário e gates

### 0.1 Fontes obrigatórias

1. `docs/Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md` — **§15: R10**, **§4.2: autenticação** e **§20: idempotência**; prevalece no contrato HTTP.
2. `docs/RFC_v1_BaaS_Simplificado_QITech.md` — papel da liveness.
3. `docs/Fluxos_v1_1_FINAL_BaaS_QITech.md` — esclarece que R10 não tem fluxo principal de domínio.
4. Implementação REAL da branch: `src/app.py`, `src/resources/health_check.py`, `src/constants.py`, `src/middlewares/internal_token.py`, `src/middlewares/session_manager.py`, `src/database.py`, `src/middlewares/request_context.py`, `src/middlewares/request_logger.py` e `tests/integration/test_healthcheck.py`.
5. `docker-compose.yml` — healthcheck do container e dependências de inicialização. Não alterar este arquivo sem defeito comprovado.

### 0.2 Gate do Git e infraestrutura

- Confirmar `feature/r10-healthcheck-audit`; **não trabalhar na main**.
- `git status`, `git branch --show-current`, `git log -1 --oneline`; preservar alterações preexistentes e mudanças do Moha.
- Confirmar `main` contém R09 e que a regressão histórica é de **265 testes**, sem assumir que será a contagem final.
- API HTTP usual: `127.0.0.1:3000`; PostgreSQL principal `bootcamp` (5432); instância separada de teste `bootcamp_test` (5433); MockServer: 1080.
- **Não derrubar, parar, reiniciar ou desconectar o PostgreSQL compartilhado** para simular falha da R10. A implementação da R07/R08 pode estar em andamento em outra máquina/processo; evitar interferência.
- Não executar migrações, DDL, DROP, TRUNCATE, reset de volume ou limpeza de dados.
- Confirmar que o middleware de sessão abre a Session apenas sob demanda. Avaliar se inicialização do processo depende das variáveis `DATABASE_URL`/`INTERNAL_TOKEN`: **configuração presente no startup não implica conexão efetiva ao banco**. Não misturar *startup* com *liveness* do processo já iniciado.

### 0.3 Hipótese inicial fundada no snapshot do repositório (rever na branch real)

- `HealthCheckResource.on_get_health_check()` retorna `fastapi.Response(status_code=204)` sem body.
- `src/app.py` registra `GET /health_check` e middleware global.
- `BYPASS_ENDPOINTS` inclui `/health_check` e o middleware não exige token nessa rota.
- Middleware `session_manager` cria contexto vazio, só instancia Session se alguma camada solicitar; resource de health não constrói controller de domínio.
- Já existem testes de HTTP 204 e PUT `/health_check` → 405, mas não parecem cobrir corpo vazio, header inválido e independência de SQL. **Reinspecionar código atual; snapshot pode estar desatualizado.**

**Saída do Bloco 0:** rastrear fluxo HTTP → middleware → resource → Response; identificar possíveis dependências acidentais de DB/connector; medir baseline real; listar cenários já cobertos e lacunas concretas.

---

## 1. Contrato oficial congelado da R10

```http
GET /health_check HTTP/1.1
# INTERNAL-TOKEN não é necessário
```

| Atributo | Contrato |
|---|---|
| Finalidade | **Liveness** — comprovar que o processo HTTP responde |
| Método/path | `GET /health_check` |
| Autenticação | **Nenhuma**, inclusive token ausente ou inválido |
| Sucesso | **HTTP 204 No Content** |
| Corpo da resposta | **Nenhum; exatamente 0 bytes**, sem JSON, string, objeto, `null` ou mensagens |
| Path/query/body de entrada | Nenhum exigido pelo contrato |
| Idempotência | Sim; chamadas repetidas observam o mesmo comportamento, sem efeitos de escrita |
| Banco | Sem leitura, query, Session de domínio, lock ou escrita |
| Conectores | Sem chamadas externas |
| Recursos de domínio | Nenhum CLIENT/ACCOUNT/TRANSACTION/ENTRY |
| Erros de domínio | Não aplicáveis (`400/403/404/409/422` não são respostas de domínio da rota GET válida) |
| Falha inesperada | `500` possível por erro interno real; **não** inventar fault injection disruptivo só para forçar 500 |
| Processo morto | Pode não haver resposta HTTP; não reinterpretar como status 500 |

### 1.1 O que não é R10

- **Não é readiness:** não verificar PostgreSQL, MockServer, carteiras, tabelas, lock de banco, migrations nem conectividade financeira.
- **Não é relatório:** não criar response JSON com status, service/version/timestamp, PID, latência, uptime, secret, contagem de registros ou métricas.
- **Não é rota protegida:** `INTERNAL-TOKEN` ausente, vazio, incorreto e até token arbitrário não devem provocar 403.
- **Não é acesso à camada de domínio:** não construir `ClientController`, `AccountController`, repositories ou utilizar `get_context().get_or_create_session()`.
- **Não é licença para alterar outras rotas** ou middleware global quando não há defeito concreto.

### 1.2 Delimitação importante do contrato

- A especificação declara que não há query params/body previstos, mas **não define um status de erro especial se algum for enviado**. Não impor automaticamente 400/422 para parâmetros ignoráveis sem fonte oficial.
- O contrato é especificamente GET; HTTP 405 para `PUT /health_check` é comportamento já testado no repo, útil como regressão, mas não exige criar handlers personalizados nem limitar OPTIONS/HEAD além do framework.
- Não tratar a ausência do header `Content-Length` como erro: para corpo vazio, cabeçalho ausente ou comprimento zero são aceitáveis conforme stack HTTP. Não exigir headers exatos não contratados.
- Não exigir que a API *suba* sem a variável `DATABASE_URL`: o requisito de R10 diz **processo HTTP vivo enquanto PostgreSQL está indisponível**, não exige ignorar todas as configurações de startup.

---

## 2. Arquitetura: auditoria de caminho de execução

Desenho esperado:

```text
GET /health_check
    ↓
request context / logger (observabilidade normal, sem SQL)
    ↓
internal_token middleware: bypass do path /health_check
    ↓
session_manager: cria contexto vazio, sem Session/checkout SQL
    ↓
HealthCheckResource.on_get_health_check()
    ↓
Response(status_code=204) + body b""
    ↓
request logger / context cleanup
```

Examinar a ordem real de middlewares; o último middleware registrado pode executar primeiro em FastAPI. Documentar se há import, dependency, `startup`/`lifespan`, interceptor, logger ou exception handler que introduza chamada ao banco no fluxo. **Distinguir criar o objeto SQLAlchemy Engine sem conectar vs abrir conexão real (checkout/query)**. Se a implementação for correta, não refatorar por preferência pessoal.

---

## 3. Matriz de testes (mínimos obrigatórios e opcionais seguros)

| ID | Verificação | Assert/evidência esperada | Obrig. |
|---|---|---|---|
| R10-01 | GET sem token | `204`, sem 403 | SIM |
| R10-02 | GET com token válido | `204`, corpo vazio | SIM |
| R10-03 | GET com token errado | `204`, não retorna erro de auth | SIM |
| R10-04 | GET com header `INTERNAL-TOKEN: ""` | `204` | SIM |
| R10-05 | Resposta binária | `response.content == b""`, nenhum JSON serializado | SIM |
| R10-06 | Sem Content-Length incorreto | Header ausente ou comprimento zero; sem corpo | SIM |
| R10-07 | Repetição | N GETs independentes resultam em 204, nenhum efeito aparente | SIM |
| R10-08 | PUT `/health_check` | `405` conforme teste existente; evitar duplicação desnecessária | SIM, existente |
| R10-09 | Não alocar Session/realizar SQL na rota | Evidência por instrumentação local ou teste com falha antecipada na aquisição SQL; sem falsos positivos | SIM |
| R10-10 | Ausência de connector externo | Inspeção + instrumentação isolada quando factível | SIM |
| R10-11 | Sem alteração persistida no banco | Por arquitetura e teste não destrutivo, sem snapshot de toda base suscetível a concorrência de outros desenvolvedores | SIM |
| R10-12 | R01–R09 preservadas | Regressão completa sem alterações no domínio | SIM |
| R10-13 | PostgreSQL realmente indisponível e API viva | **Somente** em ambiente isolado, não no `db` compartilhado | CONDICIONAL |
| R10-14 | Docker healthcheck e middleware | Inspecionar se chamada do Docker aceita o 204 e bypass de auth | SIM |
| R10-15 | Compatibilidade de rota com tokens e request logger | Nenhuma exceção/traceback/efeito colateral; validação estável | SIM |

**Recomendação de testes:** ampliar `tests/integration/test_healthcheck.py` ou criar `tests/integration/test_r10_healthcheck.py`, seguindo convenções do repositório. Reutilizar `ClientRequisition` e, onde precisar dos bytes/cabeçalhos crus, acessar `response.response` ou usar `requests` diretamente de maneira legível. Evitar depender de `response_json` no 204, pois não há JSON. Não copiar código/fixture da R09 com banco, locks ou events.

### 3.1 Independência de PostgreSQL: como provar sem risco

**Nível 1 (obrigatório):** análise real do caminho da requisição, incluindo lazy session manager e middleware; confirmar que não existe `.execute()`, `commit()`, `get_or_create_session()`/checkout, consultas a models, nem dependências injetadas de DB.

**Nível 2 (obrigatório quando praticável):** teste isolado no mesmo processo com instrumentação que falha caso qualquer DB Session/connection/checkout seja solicitado; executar GET sem token e com token inválido. Usar monkeypatch/controladores locais ou harness ASGI confiável, sem impactar o servidor HTTP ou monkeypatch global de um serviço usado por outros testes. Instrumentar o ponto de aquisição real no código atual (por exemplo, `Context.get_or_create_session()` ou engine checkout); não confundir o contexto vazio do middleware com uma sessão aberta.

**Nível 3 (opcional, controlado):** levantar uma instância **secundária isolada** da API, em porta livre e ambiente próprio, com URL de banco inválida/inalcançável (mas variável definida), fazer GET 204 e terminar apenas esse processo. Só fazer se barato, reversível, sem afetar a porta principal e sem alterar o banco compartilhado. Não tentar `docker compose stop db`, `docker compose down`, quebrar rede do container principal, trocar a URL da API usada pelo Moha, nem executar comandos invasivos.

O nível 2/3 comprova ausência de dependência de conexão na requisição. Caso alguma instrumentação seja incompatível com o framework atual, explicar objetivamente e usar a melhor evidência segura, sem fingir que o cenário foi testado.

---

## 4. Plano de execução Blocos 0, A–F

### Bloco 0 — Inspeção / baseline

1. Confirmar branch, status e documentação oficial R10.
2. Ler health resource, registro da rota, bypass de autenticação, session manager (incluindo lazy Session), logging e Docker healthcheck.
3. Executar baseline de testes, confirmar ambiente e contagem real; referência anterior **265 testes**.
4. Inventariar cobertura existente; distinguir o que já é GREEN do que falta validar.
5. Identificar quaisquer diferenças atuais por alterações novas na `main` (R07/R08 se integradas).

**Saída:** relatório curto da arquitetura e lacunas reais.

### Bloco A — Caracterização/RED condicional

1. Escrever testes úteis de R10-01 a R10-15 segundo os critérios acima; reutilizar testes já existentes sem duplicação trivial.
2. Executar os novos testes **antes** de qualquer correção de produção.
3. Se falharem por defeito real, registrar RED, stacktrace, causa e reproduzir; diferenciar defeito de problema de teste/ambiente.
4. Se todos passarem, registrar **GREEN inicial; RED não aplicável porque R10 já existia**. Nunca quebrar código artificialmente para fabricar RED.

**Saída:** evidências reais de caracterização (RED legítimo ou GREEN inicial).

### Bloco B — Correção mínima (SE NECESSÁRIA)

1. **Somente** se falha reproduzida no contrato, corrigir o menor escopo possível, indicando causa e arquivos afetados.
2. Não introduzir controllers/DTOs/repositories para esta rota nem scripts de banco.
3. Não enfraquecer asserções para obter GREEN.
4. Se nenhum defeito existir, registrar **NÃO NECESSÁRIA** e deixar produção intacta.

### Bloco C — Contrato e segurança

1. Confirmar 204 e `b""` para token omitido/correto/inválido/vazio.
2. Confirmar `INTERNAL-TOKEN` bypass sem mudar auth R01–R09.
3. Confirmar repetição e método GET; preservar PUT → 405 já existente.
4. Verificar que não há dados, headers sensíveis ou schema JSON no corpo da resposta.

### Bloco D — Independência de serviços e ausência de efeitos colaterais

1. Auditar lazy Session e observar se conexão SQL é adquirida durante health GET.
2. Preferir instrumentação local não destrutiva para proibir Session/conexão; registrar método e resultado.
3. Inspecionar ausência de calls a connectors e DomainRepository.
4. Se houver teste de API com DB indisponível, fazê-lo apenas em instância isolada.
5. Registrar limite probatório de qualquer teste não executado; não anunciar falha de banco simulado se não foi feito.

### Bloco E — Auditoria e refinamento

1. Revisar cobertura, clareza, estabilidade dos testes, dependências e custo de execução.
2. Manter healthcheck mínimo, sem `/ready`, novas dependências, métricas, commits em banco nem mudanças de middleware fora do escopo.
3. Identificar inconsistências do Docker healthcheck somente se comprovadas; não mudar `depends_on` ou healthcheck por preferência.
4. Garantir que qualquer mock permaneça local e seja restaurado com `monkeypatch`/`finally`.

### Bloco F — Regressão, documentação e entrega

1. Rodar testes específicos da R10; registrar quantidade, falhas e duração.
2. Rodar testes de middleware de autenticação/session onde houver, healthcheck legado e regressões relevantes R01–R09.
3. Executar suíte completa `python -m pytest -q`; baseline histórica 265 antes de novos testes, **não presumir número final**.
4. `git diff --check`, `git diff --stat`, `git status`, `git branch --show-current`; incluir arquivos untracked na listagem, mesmo não aparecendo no `diff --stat`.
5. Atualizar **este** arquivo com evidências verdadeiras e conclusão dos blocos 0–F.
6. Não realizar commit, push, PR nem merge automaticamente.

---

## 5. Definition of Done

- [x] GET `/health_check` retorna exatamente HTTP 204 e body vazio.
- [x] Aceita ausência de token e tokens arbitrários/inválidos.
- [x] Sem query SQL, checkout/Session de domínio, commits, locks nem modificações persistidas.
- [x] Sem dependência de conectores externos.
- [x] Request context/session middleware não quebra rota de liveness sem banco.
- [x] Teste/inspeção Docker healthcheck sem alterar dependências compartilhadas.
- [x] Não confunde liveness com readiness nem exige PostgreSQL saudável.
- [x] Cobertura existente preservada; novos testes úteis sem redundância desnecessária.
- [x] Sem alterações de produção quando o comportamento existente está correto.
- [x] Suíte completa verde, diff sem erros e sem operações destrutivas.
- [x] Documento atualizado, relatório final A–H e pronto para revisão humana.

---

## 6. Evidências de execução — preencher pelo Codex com dados reais

| Evidência | Resultado |
|---|---|
| Branch e commit base | `feature/r10-healthcheck-audit`, HEAD `a591b22` no início da auditoria; árvore limpa exceto este plano inicialmente não rastreado. |
| Baseline real antes da R10 | `265 passed in 29.03s`. |
| Código R10 preexistente | `HealthCheckResource.on_get_health_check()` retorna `Response(status_code=204)` sem controller/repository; `app.py` registra somente GET. |
| Testes existentes antes das alterações | 6 testes em `tests/integration/test_healthcheck.py`; cobriam 204 e PUT 405, mas não bytes, tokens variados, repetição ou sessão. |
| Bloco A RED verdadeiro ou GREEN inicial | GREEN inicial: os novos testes passaram sem alterar produção; os dois primeiros erros foram somente de instrumentação local (`src` ausente do path e `httpx2` indisponível), corrigidos no teste sem mudança funcional. |
| Bloco B correção necessária? | NÃO. Produção preservada. |
| GET sem token/certo/incorreto/vazio | Comprovado por parametrização HTTP real: todos retornaram 204. |
| HTTP 204 sem corpo | Comprovado em HTTP real por `response_content == b""`; `Content-Length` ausente ou `0`. |
| Sem sessão/checkout SQL | Comprovado por chamada ASGI local da aplicação e middlewares reais com `Context.get_or_create_session` **e** `engine.connect` instrumentados para falhar: 204 com token inválido. Não houve aquisição de sessão nem conexão PostgreSQL. |
| PostgreSQL indisponível em instância isolada | NÃO REALIZADO: não foi necessária nem segura uma nova instância; a prova local impede aquisição de sessão. Não se alegou teste de indisponibilidade física. |
| Ausência de connectors e efeitos colaterais | Inspeção estática: resource importa somente `os`, FastAPI e constantes; não instancia controller/repository/connector. O único objeto criado no middleware é `Context` vazio, sem Session. |
| Docker healthcheck e middleware | Inspecionados: Compose usa `urllib.request.urlopen("http://localhost:3000/health_check")`; `BYPASS_ENDPOINTS` contém a rota e o middleware pula autenticação. Serviços locais saudáveis antes da execução. |
| R10 testes finais | `12 passed, 1 warning in 4.11s`; warning de depreciação SQLAlchemy ao importar a aplicação na instrumentação local. |
| Regressão R01–R09 / full suite | `271 passed, 1 warning in 32.01s`. |
| `git diff --check` | Concluído sem saída/erros; o plano é não rastreado e foi também inspecionado diretamente. |
| Arquivos alterados e untracked | Modificado: `tests/integration/test_healthcheck.py`. Não rastreado: este plano R10, já presente no início e atualizado conforme solicitado. |
| Findings CRITICAL/MAJOR/MEDIUM/LOW | Sem CRITICAL/MAJOR/MEDIUM. LOW: não há teste de indisponibilidade física de PostgreSQL; decisão deliberada por segurança, com prova local de não aquisição de sessão. |
| Resultado | APROVADO, sujeito à revisão humana das alterações de testes e do plano. |

---

## 7. Relatório final obrigatório A–H

**A. Resultado geral:** APROVADO / APROVADO COM RESSALVAS / REPROVADO. Dizer se a R10 já estava correta ou foi ajustada.
**B. Blocos 0–F:** o que foi verificado, mudanças, razões para RED verdadeiro ou GREEN inicial e evidências reais.
**C. Contrato HTTP:** auth bypass, 204, body vazio, idempotência e limites do escopo.
**D. Arquivos criados/modificados:** justificativa de cada alteração; explicitar arquivos de produção *não* alterados.
**E. Testes:** comando, duração, números reais e distinção testes na rede vs testes isolados com instrumentation.
**F. Auditoria:** SQL/Session/connector, Docker, side effects, liveness vs readiness, findings por severidade.
**G. Integração:** compatibilidade com R07/R08 e outras rotas; sem implementar mudanças alheias.
**H. Git e conclusão:** branch, status/diff, untracked, recomendações de commit/PR.

Encerrar com **R10 PRONTA PARA AUDITORIA FINAL** ou **R10 NÃO PRONTA**, sem fingir sucesso de testes não executados.
