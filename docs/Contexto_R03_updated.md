# Contexto de Desenvolvimento — R03 com MockServer
## `POST /client/{client_key}/analysis`
### BaaS Simplificado — Bootcamp QI Tech 2026

**Status:** nova decisão arquitetural para implementação com TDD

**Branch:** `feature/r03-client-analysis`

**Issue original:** #04 — `[R03] POST /client/{client_key}/analysis — Análise cadastral`

**Responsável:** João
**Trabalho em paralelo:** Moha está desenvolvendo a R02 (`GET /client/{client_key}`)

---

# 1. Objetivo deste documento

Este documento registra a nova decisão arquitetural da R03.

A decisão anterior previa que o caller enviaria diretamente:

```json
{
  "decision": "APPROVE"
}
```

ou:

```json
{
  "decision": "REJECT",
  "reason": "Motivo"
}
```

Essa decisão foi substituída.

A nova R03 deve representar uma análise cadastral realizada por um **fornecedor externo**, que durante os testes será simulado com **MockServer**.

O objetivo é aplicar de forma coerente os conceitos estudados no Bootcamp:

- TDD;
- testes black-box;
- integração HTTP entre serviços;
- MockServer;
- expectation;
- verify;
- Connector;
- arquitetura em camadas;
- configuração por variável de ambiente;
- PostgreSQL;
- transações;
- atomicidade;
- concorrência;
- `SELECT ... FOR UPDATE`;
- separação entre código de produção e infraestrutura de teste.

A R03 ainda não foi implementada.

Portanto, esta mudança está sendo feita antes da criação do código da feature.

---

# 2. Decisão anterior

O desenho anterior era:

```text
Caller
  ↓
POST /client/{client_key}/analysis
  ↓
caller envia APPROVE ou REJECT
  ↓
API recebe decisão pronta
  ↓
API altera status
```

Exemplo:

```json
{
  "decision": "APPROVE"
}
```

Nesse modelo, a nossa API não realizava análise nem consultava nenhum serviço externo.

Adicionar MockServer mantendo esse contrato seria artificial, porque a decisão já chegaria pronta antes da chamada externa.

---

# 3. Nova decisão

O novo fluxo será:

```text
Caller
  ↓
POST /client/{client_key}/analysis
  ↓
Nossa API
  ↓
ClientAnalysisConnector
  ↓ HTTP
Analysis Provider
  ↓
APPROVE ou REJECT
  ↓
Nossa API
  ↓
aplica a transição de estado
```

Durante os testes:

```text
Analysis Provider = MockServer
```

O caller não escolhe mais se o CLIENT será aprovado ou rejeitado.

Quem fornece essa decisão é o serviço externo.

---

# 4. Conceito principal

A rota passa a significar:

> Analise este cliente agora.

E não:

> Aplique esta decisão que eu já escolhi.

Isso deixa o MockServer com uma função arquitetural real.

---

# 5. Novo contrato público da R03

Endpoint:

```text
POST /client/{client_key}/analysis
```

Autenticação:

```text
INTERNAL-TOKEN
```

A proposta é não receber `decision` no body.

Exemplo:

```http
POST /client/550e8400-e29b-41d4-a716-446655440000/analysis
INTERNAL-TOKEN: ...
```

O CLIENT identificado por `client_key` será enviado para análise através do Analysis Provider.

---

# 6. Body público da R03

A proposta inicial é:

```text
sem body obrigatório
```

Antes da implementação, deve ser conferido como o projeto trata um `POST` sem body e se algum schema vazio é necessário.

Não criar um body artificial apenas para manter o padrão anterior.

---

# 7. Resposta pública proposta

## Caso APPROVE

```json
{
  "client_key": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ACTIVE"
}
```

## Caso REJECT

```json
{
  "client_key": "550e8400-e29b-41d4-a716-446655440000",
  "status": "REJECTED"
}
```

HTTP esperado para análise válida:

```text
200 OK
```

Essa resposta é deliberadamente pequena.

Antes de criar asserts definitivos sobre o body, confirmar se queremos adicionar algum outro campo.

---

# 8. O Analysis Provider

A R03 passa a depender conceitualmente de um serviço externo denominado:

```text
Analysis Provider
```

Esse serviço representa um bureau/KYC/analisador cadastral externo.

Não vamos tentar reproduzir uma API real da Receita, Serasa ou qualquer fornecedor específico.

Será um contrato simples criado para o exercício.

---

# 9. Contrato entre nossa API e o Analysis Provider

Endpoint externo proposto:

```text
POST /v1/client-analysis
```

Nossa API envia dados mínimos suficientes para representar o CLIENT.

---

# 10. Request externo — PF

Exemplo:

```json
{
  "client_key": "550e8400-e29b-41d4-a716-446655440000",
  "client_type": "INDIVIDUAL",
  "document": "52998224725"
}
```

---

# 11. Request externo — PJ

Exemplo:

```json
{
  "client_key": "550e8400-e29b-41d4-a716-446655440000",
  "client_type": "COMPANY",
  "document": "12345678000190"
}
```

---

# 12. Campos enviados ao provider

Contrato mínimo:

```text
client_key
client_type
document
```

O campo:

```text
document
```

é usado tanto para:

```text
CPF
```

quanto para:

```text
CNPJ
```

Isso mantém o contrato externo simples.

A nossa aplicação continua sabendo se aquele documento é CPF ou CNPJ através de:

```text
client_type
```

---

# 13. Resposta do provider — APPROVE

```json
{
  "decision": "APPROVE",
  "reason": null
}
```

---

# 14. Resposta do provider — REJECT

```json
{
  "decision": "REJECT",
  "reason": "Cadastro não aprovado"
}
```

---

# 15. Valores válidos de decision

```text
APPROVE
REJECT
```

Qualquer outro valor retornado pelo fornecedor deve futuramente ser tratado como resposta externa inválida.

Exemplo:

```json
{
  "decision": "MAYBE"
}
```

não é válido.

---

# 16. Regra de reason

Para:

```text
APPROVE
```

`reason` pode ser:

```text
null
```

Para:

```text
REJECT
```

`reason` deve existir.

Regras:

```text
string
trim
não pode ficar vazio depois do trim
máximo de 500 caracteres
```

Exemplo inválido:

```json
{
  "decision": "REJECT",
  "reason": "     "
}
```

---

# 17. Quem decide APPROVE ou REJECT nos testes?

O **teste**.

O MockServer não possuirá uma regra própria de aprovação.

Não haverá:

```text
se CPF termina em 7 -> APPROVE
```

Não haverá:

```text
score aleatório
```

Não haverá:

```text
50% APPROVE
50% REJECT
```

Cada teste configura explicitamente o comportamento esperado.

---

# 18. Cenário de teste APPROVE

O teste configura:

```text
QUANDO:

POST /v1/client-analysis

ENTÃO RESPONDER:

200

{
  "decision": "APPROVE",
  "reason": null
}
```

Depois o teste chama:

```text
POST /client/{client_key}/analysis
```

A nossa API recebe `APPROVE` do provider e executa:

```text
PENDING -> ACTIVE
```

---

# 19. Cenário de teste REJECT

O teste configura:

```text
QUANDO:

POST /v1/client-analysis

ENTÃO RESPONDER:

200

{
  "decision": "REJECT",
  "reason": "Cadastro não aprovado"
}
```

Depois:

```text
POST /client/{client_key}/analysis
```

A nossa API recebe `REJECT` e executa:

```text
PENDING -> REJECTED
```

---

# 20. Testes determinísticos

Isso garante:

```text
Teste de APPROVE
sempre recebe APPROVE
```

e:

```text
Teste de REJECT
sempre recebe REJECT
```

Não existe comportamento aleatório.

Isso é importante para que a suíte seja repetível.

---

# 21. Papel do MockServer

O MockServer será usado como o fornecedor externo durante os testes.

Responsabilidades:

```text
receber expectations
responder chamadas HTTP
permitir verify
permitir reset
```

O MockServer não contém regra de domínio da nossa aplicação.

---

# 22. Fluxo completo do teste

```text
pytest
  │
  ├── cria CLIENT PENDING pela R01
  │
  ├── configura expectation
  │                    ↓
  │                MockServer
  │
  ├── chama:
  │   POST /client/{key}/analysis
  │                    ↓
  │                 Nossa API
  │                    ↓
  │          ClientAnalysisConnector
  │                    ↓
  │        POST /v1/client-analysis
  │                    ↓
  │                MockServer
  │                    ↓
  │              APPROVE/REJECT
  │                    ↓
  │                 Nossa API
  │                    ↓
  │              PostgreSQL
  │
  <── resposta HTTP
  │
  └── verify no MockServer
```

---

# 23. Onde ficará a lógica do MockServer?

Não ficará dentro de:

```text
src/
```

Não criar:

```text
src/mockserver/
```

Também não criar outro serviço Python fake.

Não queremos fazer:

```python
if cpf == "123":
    return "APPROVE"
```

O próprio MockServer é o servidor fake.

Os testes apenas configuram:

```text
quando receber X
responda Y
```

---

# 24. Onde ficará a integração real?

Criar uma camada Connector.

Estrutura proposta:

```text
src/
└── connectors/
    ├── __init__.py
    └── client_analysis_connector.py
```

Essa é parte do código de produção.

---

# 25. Responsabilidade do ClientAnalysisConnector

O Connector deverá:

```text
receber dados necessários
↓
montar payload externo
↓
chamar Analysis Provider por HTTP
↓
receber response
↓
validar formato básico
↓
normalizar decision/reason
↓
retornar resultado ao Controller
```

O Connector não deve atualizar CLIENT.

O Connector não deve criar eventos.

O Connector não deve executar commit.

---

# 26. O Connector não conhece MockServer

Não deve existir isto:

```python
url = "http://mockserver:1080"
```

hardcoded dentro do código.

A aplicação deve usar configuração externa.

---

# 27. Variável de ambiente

Nome proposto:

```text
ANALYSIS_PROVIDER_URL
```

No ambiente Docker:

```text
ANALYSIS_PROVIDER_URL=http://mockserver:1080
```

Em outro ambiente poderia ser:

```text
ANALYSIS_PROVIDER_URL=https://provider-real.example.com
```

Sem alterar o Controller.

---

# 28. Estrutura Docker

Estrutura conceitual:

```text
docker compose
│
├── api
├── postgres
├── postgres_test
└── mockserver
```

Porta normalmente utilizada pelo MockServer:

```text
1080
```

Configuração conceitual:

```yaml
mockserver:
  image: mockserver/mockserver
  ports:
    - "1080:1080"
```

Antes de implementar, inspecionar o Compose real do projeto.

Verificar:

```text
services
networks
environment
depends_on
healthchecks
profiles
ports
```

---

# 29. Arquitetura completa da nova R03

```text
POST /client/{client_key}/analysis
                │
                ▼
        ClientAnalysisResource
                │
                ▼
       ClientAnalysisController
            │             │
            │             │
            │             ▼
            │    ClientAnalysisConnector
            │             │
            │             ▼
            │      Analysis Provider
            │             │
            │             ▼
            │         MockServer
            │        durante testes
            │
            ▼
 ClientAnalysisRepository
            │
            ▼
        PostgreSQL
```

---

# 30. Estrutura de arquivos proposta

```text
src/
├── connectors/
│   ├── __init__.py
│   └── client_analysis_connector.py
│
├── resources/
│   └── client_analysis.py
│
├── controllers/
│   └── client_analysis_controller.py
│
├── repositories/
│   └── client_analysis_repository.py
│
└── schemas/
    └── ...
```

O repository próprio ainda depende de inspeção.

Talvez seja possível reutilizar:

```text
client_repository.py
```

---

# 31. Models reutilizados

A R03 deve reutilizar os models existentes:

```text
Client
ClientStatus
ClientStatusEvent
IndividualClient
CompanyClient
```

Não criar novos models sem necessidade.

---

# 32. Não criar tabela de análise

Não precisamos inicialmente de:

```text
client_analysis
analysis_result
bureau_response
kyc_result
score
```

O resultado necessário para o negócio já pode ser representado por:

```text
CLIENT.status
```

e:

```text
CLIENT_STATUS_EVENT
```

---

# 33. Persistência da resposta do provider

Não precisamos salvar o JSON completo enviado pelo fornecedor.

Fluxo:

```text
provider responde
↓
Connector valida
↓
Controller usa decision/reason
↓
payload externo é descartado
```

Persistimos somente:

```text
CLIENT.status
CLIENT_STATUS_EVENT
```

---

# 34. Estrutura de testes

Proposta:

```text
tests/
├── integration/
│   └── client/
│       └── test_r03_analyze_client.py
│
└── utils/
    └── mockserver.py
```

Mas:

```text
tests/utils/mockserver.py
```

não precisa ser criado antes de existir repetição.

---

# 35. Primeiro teste

No primeiro teste podemos configurar a expectation diretamente dentro do próprio arquivo:

```text
test_r03_analyze_client.py
```

Quando surgir repetição entre APPROVE, REJECT e demais cenários:

```text
refactor
↓
tests/utils/mockserver.py
```

---

# 36. Helper futuro do MockServer

Conceitualmente:

```python
class MockServerHelper:

    def reset(self):
        ...

    def expect_client_analysis_approve(self, ...):
        ...

    def expect_client_analysis_reject(self, ...):
        ...

    def verify_client_analysis_called(self, ...):
        ...
```

Esse helper pertence aos testes.

Nunca ao código de produção.

---

# 37. Reset entre testes

Cada teste deve possuir seu próprio cenário.

Fluxo:

```text
reset MockServer
↓
configurar expectation
↓
executar teste
↓
verify
```

Isso evita:

```text
Teste APPROVE
```

interferir em:

```text
Teste REJECT
```

---

# 38. Fluxo funcional APPROVE

```text
1. Caller chama:
   POST /client/{client_key}/analysis

2. INTERNAL-TOKEN é validado

3. Resource recebe client_key

4. Controller busca CLIENT

5. Se não existe:
   404 CLI0001

6. Controller verifica preliminarmente o status

7. Se não é PENDING:
   409 CLI0002

8. Controller coleta dados necessários

9. Connector chama:
   POST /v1/client-analysis

10. Provider responde:
    {
      "decision": "APPROVE",
      "reason": null
    }

11. A API entra na etapa transacional crítica

12. Busca CLIENT novamente com:
    SELECT ... FOR UPDATE

13. REVALIDA status

14. Se não é mais PENDING:
    409 CLI0002

15. Busca status ACTIVE

16. Atualiza:
    PENDING -> ACTIVE

17. Cria CLIENT_STATUS_EVENT:
    PENDING -> ACTIVE
    actor_type = INTERNAL

18. COMMIT

19. Retorna:
    HTTP 200
```

---

# 39. Fluxo funcional REJECT

O início é igual.

Provider responde:

```json
{
  "decision": "REJECT",
  "reason": "Cadastro não aprovado"
}
```

Então:

```text
PENDING -> REJECTED
```

Criar:

```text
CLIENT_STATUS_EVENT

from_status = PENDING
to_status = REJECTED
actor_type = INTERNAL
reason = "Cadastro não aprovado"
```

Depois:

```text
COMMIT
```

Resposta:

```text
HTTP 200
status = REJECTED
```

---

# 40. Regra crítica sobre lock e HTTP externo

Não devemos fazer:

```text
BEGIN
↓
SELECT FOR UPDATE
↓
segurar lock
↓
chamar serviço externo
↓
esperar rede
↓
esperar...
↓
receber resposta
↓
COMMIT
```

Isso seria ruim porque mantém uma linha bloqueada enquanto esperamos uma dependência externa.

---

# 41. Fluxo correto de concorrência

Fazer:

```text
buscar CLIENT normalmente
↓
validar preliminarmente PENDING
↓
coletar dados
↓
chamar Analysis Provider
↓
receber decisão
↓
SELECT CLIENT FOR UPDATE
↓
REVALIDAR PENDING
↓
aplicar decisão
↓
criar evento
↓
COMMIT
```

A palavra importante é:

```text
REVALIDAR
```

---

# 42. Por que precisamos revalidar?

Porque entre:

```text
primeira leitura
```

e:

```text
resposta do fornecedor
```

outra request pode ter alterado o CLIENT.

---

# 43. Exemplo de concorrência

Duas requests chegam:

```text
Request A
Request B
```

Ambas fazem leitura inicial:

```text
PENDING
```

Ambas consultam provider.

A recebe:

```text
APPROVE
```

B recebe:

```text
REJECT
```

Depois:

```text
A -> SELECT FOR UPDATE
A -> PENDING
A -> ACTIVE
A -> evento
A -> COMMIT
```

B:

```text
B -> SELECT FOR UPDATE
B -> encontra ACTIVE
B -> 409 CLI0002
```

Resultado:

```text
1 mudança válida
1 evento válido
1 conflito
```

---

# 44. Provider pode ser chamado duas vezes?

Em concorrência, sim.

Isso não é necessariamente um problema neste exercício.

A regra crítica é:

> O estado PENDING só pode ser consumido uma vez.

O controle dessa regra pertence ao PostgreSQL/transação, e não ao MockServer.

---

# 45. Atomicidade

Mudança de status e evento precisam ocorrer na mesma transação.

```text
UPDATE CLIENT
+
INSERT CLIENT_STATUS_EVENT
+
COMMIT
```

Nunca:

```text
CLIENT ACTIVE
sem evento
```

Nunca:

```text
evento PENDING -> ACTIVE
sem CLIENT ACTIVE
```

Em qualquer falha:

```text
ROLLBACK
```

---

# 46. Repository não faz commit

Manter o padrão arquitetural da R01.

Repository pode executar:

```text
SELECT
SELECT FOR UPDATE
INSERT
UPDATE
flush
```

Mas não:

```python
session.commit()
```

A camada de orquestração continua controlando a transação.

---

# 47. Responsabilidade do Resource

```text
receber HTTP request
receber client_key
validar entrada estrutural
chamar Controller
serializar resposta
definir HTTP status
```

Não fazer SQL.

Não chamar diretamente MockServer.

---

# 48. Responsabilidade do Controller

```text
regra de negócio
orquestração
pré-validação do CLIENT
chamar Connector
interpretar decisão normalizada
iniciar etapa transacional
revalidar estado após lock
alterar status
criar evento
commit
rollback
```

---

# 49. Responsabilidade do Connector

```text
integração HTTP externa
ANALYSIS_PROVIDER_URL
payload externo
timeout
parsing de response
validação da response externa
```

Não possui regra de lifecycle do CLIENT.

---

# 50. Responsabilidade do Repository

```text
acesso PostgreSQL
queries
FOR UPDATE
update
insert
flush
```

Não decide:

```text
PENDING pode virar ACTIVE?
```

Essa regra pertence ao Controller.

---

# 51. Responsabilidade do MockServer

```text
somente infraestrutura de teste
```

Ele simula:

```text
Analysis Provider
```

Não é uma camada da aplicação.

---

# 52. Primeiro ciclo TDD

Primeiro cenário:

```text
Dado:
CLIENT PENDING

E:
MockServer preparado para responder APPROVE

Quando:
POST /client/{client_key}/analysis

Então:
HTTP 200
```

---

# 53. Preparação do CLIENT

Preferencialmente utilizar a própria R01:

```text
POST /client
↓
CLIENT nasce PENDING
↓
obter client_key
```

Usar dados únicos.

Evitar:

```text
email fixo
CPF fixo
client_key fixo
```

---

# 54. Primeiro teste proposto

Nome:

```python
test_approve_pending_client_returns_200
```

Fluxo:

```text
1. reset MockServer
2. criar CLIENT PENDING pela R01
3. obter client_key
4. configurar expectation APPROVE
5. chamar R03
6. assert HTTP 200
```

Somente isso no primeiro comportamento.

---

# 55. Primeiro RED

Como a R03 ainda não existe, o resultado poderá ser:

```text
esperado:
200

recebido:
404
```

Esse é um RED válido.

---

# 56. Primeiro teste NÃO valida ainda

Não testar tudo de uma vez.

Não adicionar no primeiro teste:

```text
status ACTIVE no banco
evento
actor_type
verify
REJECT
concorrência
rollback
provider 500
timeout
```

Cada comportamento terá seu ciclo.

---

# 57. Sequência TDD revisada

## Ciclo 0 — infraestrutura mínima MockServer

Confirmar:

```text
container sobe
porta responde
pytest consegue criar expectation
API consegue acessar ANALYSIS_PROVIDER_URL
```

---

## Ciclo 1 — APPROVE -> HTTP 200

```text
provider APPROVE
↓
R03 200
```

---

## Ciclo 2 — resposta ACTIVE

```text
response.status == ACTIVE
```

---

## Ciclo 3 — persistência

```text
CLIENT.status == ACTIVE
```

---

## Ciclo 4 — evento APPROVE

```text
PENDING -> ACTIVE
actor_type = INTERNAL
```

---

## Ciclo 5 — verify

Confirmar que a nossa API realmente chamou:

```text
POST /v1/client-analysis
```

---

## Ciclo 6 — REJECT

```text
provider REJECT
↓
R03 200
↓
CLIENT REJECTED
```

---

## Ciclo 7 — evento REJECT

```text
PENDING -> REJECTED
actor_type = INTERNAL
reason correto
```

---

## Ciclo 8 — validação da response externa

Testar:

```text
decision inválida
REJECT sem reason
reason vazio
reason > 500
```

---

## Ciclo 9 — CLIENT não PENDING

```text
ACTIVE -> 409 CLI0002
REJECTED -> 409 CLI0002
INACTIVE -> 409 CLI0002
```

Idealmente:

```text
provider nem deve ser chamado
```

---

## Ciclo 10 — CLIENT inexistente

```text
404 CLI0001
```

E:

```text
provider não chamado
```

---

## Ciclo 11 — provider retorna erro

Exemplo:

```text
MockServer -> HTTP 500
```

O erro público da nossa API deve ser definido após revisar a taxonomia de erros existente.

Não inventar código de erro antes disso.

---

## Ciclo 12 — timeout

Connector deve possuir timeout finito.

Não implementar retry complexo neste momento.

---

## Ciclo 13 — concorrência

```text
2 requests
1 CLIENT PENDING
```

Resultado:

```text
1 sucesso
1 conflito
```

---

## Ciclo 14 — atomicidade/rollback

Forçar falha entre:

```text
alteração do status
```

e:

```text
criação do evento
```

Esperado:

```text
rollback integral
```

---

# 58. Timeout HTTP

O Connector deve possuir timeout.

Nunca:

```python
requests.post(url, json=payload)
```

sem limite de tempo, caso a biblioteca utilizada exija definição explícita.

A duração exata deve seguir o padrão existente ou uma decisão simples do projeto.

---

# 59. O que NÃO implementar agora

Não implementar:

```text
retry automático sofisticado
circuit breaker
fallback
fila
Kafka
processamento assíncrono
múltiplos providers
score
cache
persistência completa da response externa
```

Isso aumentaria demais o escopo.

---

# 60. Erro do provider

Casos mínimos a considerar posteriormente:

```text
HTTP 500
timeout
JSON inválido
decision inválida
REJECT sem reason
```

A resposta pública da nossa API deve seguir o sistema de erros existente.

Inspecionar:

```text
src/errors/
```

antes de definir novos códigos.

---

# 61. Autenticação

A R03 continua usando:

```text
INTERNAL-TOKEN
```

Reutilizar o middleware atual.

Não implementar autenticação dentro do Controller.

---

# 62. Autenticação com provider

Para o exercício inicial, não é obrigatório criar autenticação específica entre:

```text
nossa API
```

e:

```text
Analysis Provider
```

Só adicionar se houver razão concreta.

---

# 63. Cenários em que o provider NÃO deve ser chamado

A API consegue rejeitar alguns cenários antes da integração externa.

Exemplos:

```text
token inválido
client_key inválida
CLIENT inexistente
CLIENT não PENDING
```

Nesses casos:

```text
0 chamadas ao provider
```

Isso poderá ser comprovado com MockServer `verify`.

---

# 64. Verify

Depois de fazer o happy path funcionar, devemos provar que a integração realmente ocorreu.

Fluxo:

```text
configurar expectation
↓
chamar R03
↓
verify
```

Pergunta do teste:

> O Analysis Provider recebeu a chamada esperada?

---

# 65. O que verificar no request externo

Podemos posteriormente confirmar que a API enviou:

```text
client_key correto
client_type correto
document correto
```

Isso testa o contrato entre:

```text
nossa API
```

e:

```text
Analysis Provider
```

---

# 66. Estrutura final esperada

```text
bootcamp-qitech-bank-api/
│
├── src/
│   ├── connectors/
│   │   ├── __init__.py
│   │   └── client_analysis_connector.py
│   │
│   ├── resources/
│   │   └── client_analysis.py
│   │
│   ├── controllers/
│   │   └── client_analysis_controller.py
│   │
│   ├── repositories/
│   │   └── client_analysis_repository.py
│   │
│   └── models/
│       ├── client.py
│       ├── client_status.py
│       └── client_status_event.py
│
├── tests/
│   ├── integration/
│   │   └── client/
│   │       └── test_r03_analyze_client.py
│   │
│   └── utils/
│       └── mockserver.py
│
└── docker-compose.yml / compose.yaml
```

Essa estrutura é uma proposta.

O Repository e helper devem ser criados somente se a inspeção confirmar que fazem sentido.

---

# 67. Arquivos compartilhados com R02

Maior cuidado com:

```text
src/app.py
src/resources/__init__.py
src/controllers/__init__.py
src/repositories/__init__.py
src/errors/
src/repositories/client_repository.py
```

Moha está implementando R02 em paralelo.

Evitar alterações compartilhadas desnecessárias.

---

# 68. Atualização da branch antes do PR

Quando R02 ou outras mudanças entrarem na `main`:

```text
atualizar branch
↓
resolver conflitos conscientemente
↓
rodar R03
↓
rodar suíte completa
```

Não aceitar automaticamente um lado inteiro de conflito sem revisar.

---

# 69. Documentação anterior fica desatualizada

A Issue original dizia que:

```text
caller fornece APPROVE/REJECT
```

e que:

```text
MockServer estava fora do escopo
```

Essa decisão foi substituída.

Não tratar essas duas afirmações antigas como fonte de verdade durante a nova implementação.

---

# 70. Documentos que deverão ser atualizados

Depois de congelar esta solução:

```text
Issue #04
Contexto da R03
Rotas
Fluxos
RFC, se necessário
```

Principal mudança:

```text
ANTES:
caller decide

DEPOIS:
Analysis Provider decide
```

---

# 71. O que a R03 demonstra no Bootcamp

Com essa arquitetura, a feature demonstrará:

```text
TDD
✓

black-box HTTP
✓

arquitetura em camadas
✓

PostgreSQL
✓

Connector
✓

integração entre serviços
✓

variável de ambiente
✓

MockServer
✓

expectation
✓

verify
✓

atomicidade
✓

concorrência
✓

SELECT FOR UPDATE
✓
```

---

# 72. Regra de uso do Codex

Antes da implementação, Codex deve receber este documento.

Inicialmente ele deve:

```text
ler
inspecionar
comparar
confirmar
```

Ele não deve imediatamente implementar a R03 inteira.

---

# 73. O que o Codex precisa inspecionar

Especialmente:

```text
docker-compose.yml / compose.yaml

src/app.py

src/config/
ou mecanismo equivalente

src/resources/client.py

src/controllers/client_controller.py

src/repositories/client_repository.py

src/models/client.py

src/models/individual_client.py

src/models/company_client.py

src/models/client_status.py

src/models/client_status_event.py

src/errors/

tests/integration/client/test_r01_create_client.py

tests/utils/requisition.py

tests/utils/

requirements
pyproject
ou configuração de dependências
```

---

# 74. Perguntas que o Codex deve responder antes do código

```text
1. Qual biblioteca HTTP já está disponível?
2. Como configurações/environment são lidas?
3. Como adicionar MockServer ao Compose atual?
4. Como API resolve hostname entre containers?
5. Como pytest acessará MockServer pela máquina host?
6. Já existe algum helper MockServer no projeto-base?
7. Como recuperar CPF/CNPJ pelo CLIENT?
8. Já existe get_by_client_key?
9. Existe algum FOR UPDATE no projeto?
10. Como sessions/transactions são controladas?
11. Como os errors são modelados?
12. É necessário schema para POST sem body?
13. Quais arquivos a R02 já pode estar alterando?
```

---

# 75. O primeiro prompt para Codex deverá parar no RED

O objetivo inicial deve ser:

```text
configurar infraestrutura mínima necessária
↓
criar primeiro teste APPROVE
↓
executar
↓
obter RED correto
↓
parar
```

Não implementar o GREEN sem aprovação humana.

---

# 76. Definition of Done revisada

A R03 estará concluída quando:

- [x] caller não envia `APPROVE` ou `REJECT`
- [x] R03 chama Analysis Provider
- [x] existe `ClientAnalysisConnector`
- [x] provider URL vem de configuração
- [x] produção não referencia MockServer diretamente
- [x] MockServer sobe no ambiente de teste/desenvolvimento
- [x] pytest configura expectations
- [x] APPROVE externo produz `ACTIVE`
- [x] REJECT externo produz `REJECTED`
- [x] reason de REJECT é registrado no evento
- [x] eventos usam `actor_type = INTERNAL`
- [x] estado e evento são atômicos
- [x] rollback não deixa estado parcial
- [x] CLIENT inexistente é tratado
- [x] CLIENT não PENDING é tratado
- [x] provider não é chamado quando análise já é impossível localmente
- [x] pelo menos um teste usa MockServer `verify`
- [x] request externo correto é testado
- [x] response externa inválida é tratada
- [x] erro básico do provider é tratado
- [x] Connector possui timeout
- [x] lock não fica aberto durante HTTP externo
- [x] `FOR UPDATE` é usado na etapa crítica
- [x] status é revalidado após lock
- [x] concorrência produz somente uma transição válida
- [x] repository não executa commit
- [x] testes R03 verdes
- [x] suíte completa verde
- [x] PR contém somente mudanças necessárias

---

# 77. Decisão congelada para início do desenvolvimento

A partir deste documento, considerar como desenho da R03:

```text
POST /client/{client_key}/analysis
↓
validar CLIENT
↓
ClientAnalysisConnector
↓
POST /v1/client-analysis
↓
Analysis Provider
↓
APPROVE / REJECT
↓
SELECT CLIENT FOR UPDATE
↓
revalidar PENDING
↓
ACTIVE / REJECTED
↓
CLIENT_STATUS_EVENT
↓
COMMIT
```

Nos testes:

```text
Analysis Provider = MockServer
```

---

# 78. Princípio principal

A aplicação não deve saber que o fornecedor é falso.

Para a nossa API existe apenas:

```text
ANALYSIS_PROVIDER_URL
```

Para os testes:

```text
ANALYSIS_PROVIDER_URL
```

aponta para:

```text
MockServer
```

Essa separação permite testar a integração real HTTP sem depender de um fornecedor verdadeiro.

---

# 79. Princípio de decisão dos testes

O MockServer não decide autonomamente.

Quem define o cenário é o teste:

```text
teste APPROVE
→ provider responde APPROVE
```

```text
teste REJECT
→ provider responde REJECT
```

```text
teste provider 500
→ provider responde 500
```

```text
teste response inválida
→ provider responde payload inválido
```

Cada teste possui controle completo sobre seu cenário.

---

# 80. Próximo passo

Depois de aprovar este contexto:

```text
1. entregar este documento ao Codex
2. informar que esta decisão substitui o desenho antigo da R03
3. pedir inspeção rápida do repositório
4. confirmar infraestrutura real
5. adicionar MockServer de forma mínima
6. preparar expectation APPROVE
7. criar primeiro teste:
   test_approve_pending_client_returns_200
8. executar
9. obter RED
10. revisar o RED
11. somente depois implementar o GREEN mínimo
```

---

# 81. Resumo final

A R03 agora terá uma dependência externa simulada.

```text
Caller
↓
R03
↓
Controller
↓
Connector
↓ HTTP
Analysis Provider
```

Nos testes:

```text
Analysis Provider
=
MockServer
```

O teste controla a decisão:

```text
APPROVE
ou
REJECT
```

O MockServer responde exatamente o que o cenário pediu.

Depois da resposta externa:

```text
FOR UPDATE
↓
revalidação
↓
status
↓
evento
↓
commit
```

O objetivo é aplicar MockServer de forma real e justificável, sem transformar a feature em uma arquitetura maior do que o necessário para a entrega.
