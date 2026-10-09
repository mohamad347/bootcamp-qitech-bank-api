# Testes do schema bancário v1.1

Este guia descreve o contrato coberto por `tests/integration/database/` e
como manter essa suíte. A fonte das regras é o [ERD v1.1](ERD_v1_1_FINAL_BaaS_QITech.md);
o SQL testado fica em [`database/database.sql`](../database/database.sql).
As docstrings dos testes registram a intenção de cada cenário junto ao código.

## Escopo e organização

São testes de **integração com PostgreSQL real**. Eles verificam a estrutura
física do banco e o efeito de constraints por meio de `INSERT`/`UPDATE`.
Não chamam a API HTTP e não testam regras de fluxo de depósito, transferência
ou cadastro. Esses fluxos terão testes próprios nas respectivas issues.

| Arquivo | Tabelas e responsabilidade |
| --- | --- |
| [`test_schema_bootstrap.py`](../tests/integration/database/test_schema_bootstrap.py) | Confere que o script principal produz exatamente as dez tabelas do ERD. |
| [`test_client_schema.py`](../tests/integration/database/test_client_schema.py) | Cliente, status, perfis PF/PJ e histórico de status. |
| [`test_account_schema.py`](../tests/integration/database/test_account_schema.py) | Conta, saldo, status e histórico de status. |
| [`test_financial_schema.py`](../tests/integration/database/test_financial_schema.py) | Operações financeiras e lançamentos. |
| [`conftest.py`](../tests/integration/database/conftest.py) | Bootstrap do banco descartável e isolamento das inserções por teste. |
| [`assertions.py`](../tests/integration/database/assertions.py) | Comparações reutilizáveis do catálogo PostgreSQL. |
| [`builders.py`](../tests/integration/database/builders.py) | Linhas mínimas válidas para preparar cenários. |

As classes agrupam cenários de uma tabela. Nomes `test_...` descrevem a
regra; as docstrings acrescentam contexto quando o nome sozinho não basta.
O código do teste mostra os dados de entrada e a consequência exigida.

## Contratos verificados

### Cliente e perfis

| Tabela | Contrato estrutural | Comportamento exercitado |
| --- | --- | --- |
| `client_status` | ID, enumerador obrigatório e único. | Seeds exatas `PENDING`, `ACTIVE`, `REJECTED`, `INACTIVE`; valor desconhecido rejeitado. |
| `client` | Colunas, tipos, nulidade, PK, FK de status com `ON DELETE RESTRICT`, unicidade de `client_key`/`email` e `idx_client_status`. | Tipo fora de `INDIVIDUAL`/`COMPANY` e e-mail duplicado são rejeitados. |
| `individual_client` | `client_id` como PK/FK restritiva; CPF único; dados obrigatórios. | CPF duplicado em outro cliente é rejeitado. |
| `company_client` | `client_id` como PK/FK restritiva; CNPJ único; `trade_name` anulável. | CNPJ duplicado é rejeitado; empresa sem nome fantasia é aceita. |
| `client_status_event` | Colunas, três FKs restritivas e índice de histórico `(client_id, created_at, id)`. | Evento inicial aceita origem nula; `SYSTEM`/`INTERNAL` são aceitos; ator desconhecido é rejeitado. |

### Conta

| Tabela | Contrato estrutural | Comportamento exercitado |
| --- | --- | --- |
| `account_status` | ID, enumerador obrigatório e único. | Seeds exatas `ACTIVE`, `INACTIVE`, `CLOSED`; valor desconhecido rejeitado. |
| `account` | UUID público, timestamps com fuso, FKs restritivas, `UNIQUE(account_key)`, `UNIQUE(client_id)` e `idx_account_status`. | Saldo omitido inicia em zero; saldo negativo e segunda conta do mesmo cliente são rejeitados. |
| `account_status_event` | Colunas, três FKs restritivas e índice `(account_id, created_at, id)`. | Evento inicial aceita origem nula; `SYSTEM`/`INTERNAL` são aceitos; ator desconhecido é rejeitado. |

### Operações e lançamentos

| Tabela | Contrato estrutural | Comportamento exercitado |
| --- | --- | --- |
| `financial_transaction` | UUIDs únicos para `transaction_key` e `request_control_key`, hash `CHAR(64)`, PK e timestamp com fuso. | `DEPOSIT` e `TRANSFER` são aceitos; outro tipo é rejeitado; chave de controle repetida é rejeitada mesmo entre tipos distintos. |
| `transaction_entry` | Colunas, PK, FKs restritivas para transação e conta; montantes `BIGINT`. | Crédito principal e débito de tarifa positivos são aceitos; direção/tipo desconhecidos, valor zero e saldo posterior negativo são rejeitados. |

O teste de bootstrap consulta as tabelas físicas de `public` e compara o
conjunto inteiro com as dez tabelas aprovadas. Assim ele identifica tanto
uma tabela ausente quanto uma tabela extra, como `sample_entity`.

### O que cada tipo de verificação demonstra

- **Catálogo:** `information_schema.columns` e o inspector do SQLAlchemy
  conferem tipos, nulidade, PK, FKs, `ON DELETE`, `UNIQUE` e índices. A
  comparação das colunas é exata; uma coluna extra também falha.
- **Inserção válida:** demonstra que um valor permitido é realmente aceito.
- **Inserção inválida:** `pytest.raises(IntegrityError)` demonstra a recusa
  pelo PostgreSQL. `23514` identifica violação de `CHECK`; `23505`, violação
  de `UNIQUE`. O teste verifica o código para não aceitar uma falha por
  motivo diferente.
- **Parâmetros:** um teste parametrizado gera um cenário por valor. Por
  exemplo, os quatro valores inválidos de `transaction_entry` aparecem
  separadamente no resultado do pytest.

Uma leitura de `UNIQUE` no catálogo confirma a definição da constraint;
os cenários de duplicidade comprovam seu efeito nas chaves mais relevantes.
Não há uma tentativa de duplicação para **toda** coluna única.

## Isolamento e ciclo de vida

O Compose de testes em [`compose.test.yml`](../compose.test.yml) fornece um
PostgreSQL separado do Compose da API. A suíte usa `TEST_DATABASE_URL`.

1. `schema_engine` valida que a URL existe, que o nome do banco termina em
   `_test` e que ela difere de `DATABASE_URL`.
2. [`DbUtils.reset_schema()`](../tests/utils/db_utils.py) remove e recria
   `public` **nesse banco descartável**, depois executa `database.sql`.
   Isso ocorre uma vez por sessão de pytest.
3. Um teste de estrutura recebe a engine e consulta o catálogo.
4. Um teste que escreve recebe `db_connection`. Essa fixture abre uma
   transação antes do teste e faz rollback ao fim, inclusive se o teste
   falhar. As tabelas permanecem; as linhas inseridas naquele teste somem.
5. Ao final da sessão, a engine é descartada e suas conexões são liberadas.

O `reset_schema()` é destrutivo para o schema `public` do banco apontado.
O sufixo `_test` e a comparação de URLs são proteções, mas não substituem
a conferência da URL antes de executar a suíte. IDs de sequências podem
avançar após rollback; os testes não dependem de IDs específicos.

Os builders recebem a conexão da fixture, geram UUIDs únicos e usam
`RETURNING id` para criar somente os registros pai necessários. Eles não
passam pela API, pois o objetivo desta suíte é testar o banco diretamente.

## Execução no PowerShell

Na raiz do repositório, com a `.venv` instalada:

```powershell
docker compose -f compose.test.yml up -d --build --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:5433/bootcamp_test"
.\.venv\Scripts\python.exe -m pytest tests/integration/database -q
```

`--wait` aguarda o healthcheck do PostgreSQL. `-q` reduz a saída do pytest;
remova-o ou use `-v` para ver cada cenário. A porta padrão no computador é
`5433`. Se estiver ocupada, escolha outra **antes** de subir o serviço:

```powershell
$env:TEST_DB_PORT = "55432"
docker compose -f compose.test.yml up -d --build --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@127.0.0.1:55432/bootcamp_test"
.\.venv\Scripts\python.exe -m pytest tests/integration/database -q
```

Para focar em uma tabela ou cenário:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/database/test_account_schema.py::TestAccountSchema -v
.\.venv\Scripts\python.exe -m pytest tests/integration/database/test_account_schema.py::TestAccountSchema::test_balance_starts_at_zero -q
```

Para parar o banco de teste:

```powershell
docker compose -f compose.test.yml stop db_test
```

`pytest -q` na suíte inteira também executa os testes HTTP de
`tests/integration/test_healthcheck.py`. Nesse caso, a API precisa estar
respondendo e `DATABASE_URL` deve apontar para **outro** banco, distinto de
`TEST_DATABASE_URL`. Os testes HTTP não usam o rollback transacional da
suíte de schema.

## Como manter a documentação e os testes

Ao mudar uma regra do ERD:

1. Coloque o cenário na classe da tabela correspondente e descreva na
   docstring **qual contrato ele protege**. Use `schema_engine` para leitura
   estrutural ou `db_connection` quando houver `INSERT`/`UPDATE`.
2. Rode o cenário para observar a falha (**RED**). Ajuste
   `database/database.sql` até passar (**GREEN**), depois simplifique o
   código sem enfraquecer a asserção.
3. Se a preparação for repetida em vários testes, adicione um helper em
   `builders.py`. Se uma consulta estrutural se repetir, adicione uma
   função em `assertions.py`. Mantenha os valores importantes visíveis no
   próprio teste.
4. Atualize a matriz de cobertura deste guia e rode toda a pasta de
   testes de schema. Antes de integrar a branch, rode a suíte completa
   com API e bancos separados.

**Limite do contrato:** os testes atuais não provam que um cliente PF
tenha obrigatoriamente um perfil PF, que `balance_after_cents` corresponda
ao saldo efetivo da conta, nem que uma transferência tenha todos os
lançamentos esperados. Essas são regras de fluxo a cobrir nas próximas
issues. A suíte do schema comprova apenas o que o SQL v1.1 declara e os
cenários explicitamente exercitados acima.
