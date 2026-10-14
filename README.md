# Sistema ADS-5 (Produtos + Biblioteca)

## Arquivos
| Arquivo | Função |
|---|---|
| `Tabelas.sql` | Cria banco e tabelas (substitui `Tabelas.sql` e `TabelasBiblioteca.sql`) |
| `api.py` | API única (substitui `api.py`, `apicors.py` e `APILIB.py`) — porta 5000 |
| `cliente.py` | Menu de console único (substitui `cliente.py` e `Biblioteca.py`) |
| `RodarBiblioteca.py` | Sobe API + interface web e abre o navegador |
| `index.html` | Interface web da biblioteca (agora com login real) |
| `instdep.bat` | Instala as dependências |

Pode apagar: `apicors.py`, `APILIB.py`, `Biblioteca.py`, `TabelasBiblioteca.sql` e os arquivos `.pyc`.

## Passo a passo
1. Execute `instdep.bat` (ou `pip install flask pyodbc requests flask-cors`).
2. No SSMS / Azure Data Studio, execute `Tabelas.sql` (pode rodar mais de uma vez; não apaga dados).
3. Escolha como usar:
   - **Web:** `python RodarBiblioteca.py` (abre http://127.0.0.1:8090/index.html)
   - **Console:** `python api.py` num terminal e `python cliente.py` em outro

## Usuários iniciais (criados pela API na 1ª execução — troque as senhas)
| Login | Senha | Perfil |
|---|---|---|
| admin | admin | admin |
| professor | professor | professor |
| cliente | cliente | cliente |

## Permissões (editar no dicionário `PERMISSOES` de `api.py`)
| Operação | admin | professor | cliente |
|---|---|---|---|
| Consultar produtos, livros, disponíveis e emprestados | ✔ | ✔ | ✔ |
| Incluir/alterar/excluir produtos | ✔ | | |
| Incluir/alterar/excluir livros | ✔ | ✔ | |
| Emprestar, devolver e ver empréstimos abertos | ✔ | ✔ | |

## Variáveis de ambiente (opcionais)
`ADS_SECRET_KEY` (defina em uso real), `ADS_DB_SERVER`, `ADS_DB_NAME`, `ADS_DB_DRIVER`,
`ADS_DB_USER`, `ADS_DB_PASSWORD` (sem usuário/senha usa autenticação do Windows),
`ADS_PORT`, `ADS_DEBUG=1`. Os nomes antigos `BIBLIOTECA_DB_*` e `PRODUTOS_DB_*` continuam valendo.
# API_BIBLIOTECA.PY
