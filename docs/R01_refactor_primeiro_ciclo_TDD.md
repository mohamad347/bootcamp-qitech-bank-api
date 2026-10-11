# R01 — refactor do primeiro ciclo TDD

**Data:** 11/10/2026

**Base:** commit `f01098e` (`feat: add R01 individual client creation`)

**Escopo:** primeiro cenário de `POST /client` para pessoa física válida.

## O que mudou

- Em `src/controllers/client_controller.py`, os três campos da resposta são
  capturados antes de `session.commit()`. O retorno continua ocorrendo somente
  após o commit bem-sucedido. Isso evita ler atributos ORM que a sessão pode
  expirar no commit e fazer consultas adicionais depois da gravação.
- O import de `datetime` foi movido para o topo do controller.
- Em `src/resources/client.py`, o nome local `client_response` deixa claro que
  o controller devolve dados de resposta, não um objeto ORM.
- Foram ajustados espaçamento, linhas finais e quebras de linha nos arquivos
  tocados da R01, sem modificar a lógica de validação ou persistência.
- `README.md` e `docs/como-o-projeto-e-organizado.md` agora registram que
  somente o primeiro cenário da R01 está implementado, em vez de afirmar que
  nenhuma rota bancária existe.

## Comportamento preservado

`POST /client` com cliente `INDIVIDUAL` válido e `INTERNAL-TOKEN` válido
continua retornando HTTP `201 Created`. O resource escolhe o status HTTP; o
controller faz um único commit; o repository faz `add` e `flush`, sem commit.
Nenhum erro CLI, regra de negócio, contrato HTTP ou cenário de teste foi
acrescentado neste refactor.

## Verificação

O teste isolado `tests/integration/client/test_r01_create_client.py` passou:
`1 passed`. Ele envia um POST real e cria um cliente no banco configurado para
a API. `git diff --check` não apontou erros de espaço em branco. A suíte de
schema não foi executada nesta etapa, pois seu setup recria `public` no banco
de testes. O resultado anterior de `65 passed` foi informado pela equipe antes
deste refactor; não foi reproduzido aqui.

## Próximos ciclos TDD, fora deste refactor

- Respostas de erro contratadas para CPF, timezone, idade, data inválida e
  duplicidade de e-mail/CPF.
- Criação de cliente `COMPANY`.
- Testes adicionais para corpo da resposta, estado `PENDING`, especialização PF
  e evento inicial `NULL → PENDING` persistidos.
- Casos de normalização e validação de campos após `trim`.

Esses itens alteram ou ampliam comportamento observável e devem nascer de
testes próprios, não ser misturados a este refactor.
