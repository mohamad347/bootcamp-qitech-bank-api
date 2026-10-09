# Organização do projeto

Este guia descreve o repositório **no estágio atual** e indica onde cada
parte das próximas rotas bancárias será implementada. O contrato do produto
está no [ERD](ERD_v1_1_FINAL_BaaS_QITech.md), nas
[rotas](Rotas_v1_1_FINAL_CONSOLIDADA_BaaS_QITech.md) e nos
[fluxos](Fluxos_v1_1_FINAL_BaaS_QITech.md).

## Estado atual

O schema PostgreSQL v1.1 está em `database/database.sql` e tem testes de
integração em `tests/integration/database/`. A API FastAPI responde à
rota de saúde e ainda registra endpoints `sample_entity` do exemplo do
bootcamp. **As rotas bancárias R01–R09 ainda não estão implementadas.**
Os modelos, repositories, controllers, schemas e DTOs existentes em `src/`
tratam do exemplo; não representam as dez tabelas bancárias do SQL principal.

O SQL principal não cria tabelas `sample_entity`. Portanto, subir a API e
receber resposta do `/health_check` não comprova que os endpoints do
exemplo funcionem com o banco bancário.

## Mapa do repositório

| Local | Responsabilidade atual |
| --- | --- |
| `database/database.sql` | Criação das dez tabelas bancárias, seeds, chaves, restrições e índices. |
| `src/app.py` | Montagem do FastAPI, registro dos middlewares e das rotas disponíveis. |
| `src/middlewares/` | Contexto de requisição, log, token interno e ciclo de vida da sessão. |
| `src/resources/` | Entrada e saída HTTP; hoje contém health check e rotas do exemplo. |
| `src/schemas/` | JSON Schemas de entrada usados pelo exemplo. |
| `src/controllers/` | Regras e coordenação das operações; os controllers de negócio bancário ainda serão criados. |
| `src/repositories/` | Consultas e escritas no banco; atualmente contém apenas o repository do exemplo. |
| `src/models/` | Mapeamentos SQLAlchemy existentes para o exemplo; os modelos bancários ainda serão adicionados conforme a implementação. |
| `src/dtos/` | Montagem das respostas do exemplo; respostas bancárias ainda serão definidas no código. |
| `src/errors/` | Exceções e tradução de erros para respostas HTTP. |
| `src/connectors/` | Código de integração externa herdado da estrutura inicial. |
| `src/database.py` | Engine SQLAlchemy e contexto da sessão por requisição. |
| `tests/integration/database/` | Testes do schema físico em PostgreSQL real. |
| `tests/integration/test_healthcheck.py` | Testes HTTP da rota de saúde. |
| `docker-compose.yml` e `compose.test.yml` | Ambiente da API e banco separado para testes de schema. |

## Caminho de uma requisição

Em `src/app.py`, os middlewares são registrados na ordem inversa à
execução de entrada. Uma requisição passa pelo contexto, pelo log, pela
verificação do `INTERNAL-TOKEN` quando exigido e pelo gerenciador de
sessão antes de chegar ao resource. O `/health_check` dispensa token.

Para uma rota bancária futura, o fluxo de código previsto é:

```text
HTTP → resource → validação de entrada → controller → repository → PostgreSQL
                                controller → DTO/resposta → HTTP
```

O resource trata protocolo HTTP e delega a operação. O controller aplica
regras de negócio e define quando a transação pode ser confirmada. O
repository faz a persistência e as consultas. Os modelos descrevem o
mapeamento das tabelas, enquanto schemas e DTOs cuidam dos formatos de
entrada e saída. Essas responsabilidades são uma orientação para as
features novas; a implementação deve seguir o contrato de cada rota.

### Sessão e transação

O middleware em `src/middlewares/session_manager.py` abre um contexto no
início da requisição. `BaseController` obtém esse contexto de
`src/database.py` e cria uma sessão somente quando algum controller
precisa do banco. Em caso de exceção não tratada, o middleware executa
`rollback`; ao final, fecha a sessão se ela tiver sido criada.

O middleware **não executa `commit`**. Quem implementa cada operação deve
definir o ponto de confirmação depois das validações e escritas exigidas
pelo fluxo. Para operações financeiras, consulte as regras de
atomicidade, idempotência e concorrência nos
[fluxos v1.1](Fluxos_v1_1_FINAL_BaaS_QITech.md).

## Como acrescentar uma rota bancária

1. Leia o contrato da rota em `Rotas v1.1`, o fluxo correspondente e as
   invariantes do ERD. Identifique comportamento observável e erros.
2. Escreva um teste de integração HTTP para um comportamento por vez e
   confirme o **RED**: a funcionalidade ainda não existe.
3. Implemente apenas as peças necessárias para passar o teste: rota em
   `src/app.py`, resource, validação, controller, repository, modelos e
   resposta conforme o caso. Os nomes e a quantidade dessas peças podem
   variar conforme o fluxo.
4. Confirme o **GREEN** com o banco de teste apropriado. Em seguida,
   **REFACTOR** preservando o comportamento coberto.
5. Acrescente cenários de erro, estado e concorrência exigidos pelo
   contrato. Atualize o README quando uma rota passar a existir de fato.

Os testes de schema atuais verificam a estrutura e as constraints do
banco; não substituem testes HTTP dos fluxos bancários. Consulte o
[guia dos testes do schema](Testes_do_Schema_v1_1.md) antes de modificar
`database/database.sql`. O banco usado nesses testes é descartável:
o setup apaga e recria o schema `public`.

## Fonte de verdade

O [README](../README.md) informa o que já funciona e como executar o
projeto. O ERD define o modelo de dados, Rotas v1.1 define os contratos
HTTP, Fluxos v1.1 detalha as operações e o
[RFC](RFC_v1_BaaS_Simplificado_QITech.md) registra o contexto e as
escolhas. Se uma decisão mudar durante a implementação, atualize o
contrato afetado junto com o código e os testes.
