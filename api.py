"""
API unificada: Login + Produtos + Biblioteca (Flask + pyodbc + SQL Server)

Dependências:  pip install flask flask-cors pyodbc requests
Executar:      python api.py        (porta 5000)
"""
import hmac
import logging
import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from functools import wraps

import pyodbc
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

# =============================================================================
# CONFIGURAÇÃO (variáveis de ambiente; os valores abaixo são os padrões)
# =============================================================================
def _env(nome, padrao=None):
    """Lê ADS_DB_<nome>; aceita também os nomes antigos BIBLIOTECA_DB_ e PRODUTOS_DB_."""
    for prefixo in ("ADS_DB_", "BIBLIOTECA_DB_", "PRODUTOS_DB_"):
        valor = os.getenv(prefixo + nome)
        if valor:
            return valor
    return padrao


DB_BACKEND = os.getenv("ADS_DB_BACKEND", "sqlite").lower()
DB_SERVER = _env("SERVER", "localhost")
DB_NAME = _env("NAME", "ADS-5")
DB_DRIVER = _env("DRIVER", "ODBC Driver 18 for SQL Server")
DB_USER = _env("USER")
DB_PASSWORD = _env("PASSWORD")
DB_SQLITE_PATH = os.getenv("ADS_DB_PATH", os.path.join(os.path.dirname(__file__), "ads5.db"))

SECRET_KEY = os.getenv("ADS_SECRET_KEY", "ads5-chave-de-desenvolvimento-troque-isto")
TOKEN_MAX_AGE = int(os.getenv("ADS_TOKEN_MAX_AGE", "28800"))  # 8 horas
HOST = os.getenv("ADS_HOST", "127.0.0.1")
PORT = int(os.getenv("ADS_PORT", "5000"))

# Quem pode o quê. Para mudar uma regra, edite apenas este dicionário.
TODOS = {"admin", "professor", "cliente"}
PERMISSOES = {
    "produtos:ler": TODOS,
    "produtos:escrever": {"admin"},
    "livros:ler": TODOS,
    "livros:escrever": {"admin", "professor"},
    "emprestimos:ler": {"admin", "professor"},        # ver nomes dos leitores
    "emprestimos:gerenciar": {"admin", "professor"},  # emprestar / devolver
}

# Criados automaticamente (se não existirem). TROQUE essas senhas depois.
USUARIOS_INICIAIS = (
    ("admin", "admin", "admin"),
    ("professor", "professor", "professor"),
    ("cliente", "cliente", "cliente"),
)

log = logging.getLogger("ads5")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
CORS(app)  # libera a interface web (index.html) em outra porta


# =============================================================================
# BANCO DE DADOS
# =============================================================================
def conectar():
    if DB_BACKEND == "sqlite":
        conn = sqlite3.connect(DB_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    conn_str = f"DRIVER={{{DB_DRIVER}}};SERVER={DB_SERVER};DATABASE={DB_NAME};"
    if DB_USER and DB_PASSWORD:
        conn_str += f"UID={DB_USER};PWD={DB_PASSWORD};Encrypt=no;"
    else:
        conn_str += "Trusted_Connection=yes;"
    return pyodbc.connect(conn_str + "TrustServerCertificate=yes;")


def inicializar_banco_sqlite():
    """Cria a estrutura mínima do banco em SQLite para rodar localmente."""
    with db(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login VARCHAR(50) NOT NULL UNIQUE,
                senha VARCHAR(255) NOT NULL,
                tipo VARCHAR(20) NOT NULL DEFAULT 'cliente'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome VARCHAR(100) NOT NULL,
                preco DECIMAL(10, 2) NOT NULL,
                quantidade INTEGER NOT NULL CHECK (quantidade >= 0)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo VARCHAR(150) NOT NULL,
                autor VARCHAR(100) NOT NULL,
                editora VARCHAR(100) NOT NULL,
                ano INTEGER NOT NULL CHECK (ano > 0),
                estoque INTEGER NOT NULL CHECK (estoque >= 0)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Emprestimos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                livro_id INTEGER NOT NULL,
                nome_aluno VARCHAR(100) NOT NULL,
                data_emprestimo DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data_devolucao DATETIME NULL,
                FOREIGN KEY (livro_id) REFERENCES Livros(id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_emprestimos_abertos ON Emprestimos (livro_id) WHERE data_devolucao IS NULL"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_emprestimos_livro ON Emprestimos (livro_id)")

        if cur.execute("SELECT COUNT(*) FROM Livros").fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO Livros (titulo, autor, editora, ano, estoque) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Grande Sertão: Veredas", "João Guimarães Rosa", "Nova Fronteira", 1956, 5),
                    ("Vidas Secas", "Graciliano Ramos", "Record", 1938, 4),
                    ("Capitães da Areia", "Jorge Amado", "Companhia das Letras", 1937, 2),
                ],
            )


@contextmanager
def db(commit=False):
    """Entrega um cursor. Com commit=True grava ao sair; em erro faz rollback.
    A conexão é sempre fechada.

        with db() as cur:              # leitura
        with db(commit=True) as cur:   # gravação
    """
    conn = conectar()
    try:
        yield conn.cursor()
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def criar_usuarios_iniciais():
    """Cria admin/professor/cliente (com senha em hash) se ainda não existirem."""
    try:
        with db(commit=True) as cur:
            for login_, senha, tipo in USUARIOS_INICIAIS:
                cur.execute("SELECT 1 FROM Usuarios WHERE login = ?", (login_,))
                if cur.fetchone() is None:
                    cur.execute(
                        "INSERT INTO Usuarios (login, senha, tipo) VALUES (?, ?, ?)",
                        (login_, generate_password_hash(senha), tipo),
                    )
                    log.warning("Usuário '%s' criado com a senha padrão. Troque-a.", login_)
    except Exception:
        log.exception("Não foi possível preparar os usuários. O banco foi criado com Tabelas.sql?")


# =============================================================================
# AUTENTICAÇÃO / AUTORIZAÇÃO
# =============================================================================
def _serializer():
    return URLSafeTimedSerializer(SECRET_KEY, salt="ads5-auth")


def valor_linha(linha, campo):
    if linha is None:
        return None
    try:
        return linha[campo]
    except (TypeError, KeyError, IndexError):
        return getattr(linha, campo)


def permissoes_do_tipo(tipo):
    return sorted(p for p, tipos in PERMISSOES.items() if tipo in tipos)


def verificar_senha(armazenada, informada):
    """Devolve (senha_confere, precisa_regravar_como_hash).
    Aceita senhas antigas em texto puro e as converte para hash no 1º login."""
    if armazenada.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(armazenada, informada), False
    confere = hmac.compare_digest(armazenada.encode("utf-8"), informada.encode("utf-8"))
    return confere, confere


def requer(permissao):
    """Decorator: exige token válido e que o tipo do usuário tenha a permissão."""
    if permissao not in PERMISSOES:
        raise ValueError(f"Permissão desconhecida: {permissao}")

    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cabecalho = request.headers.get("Authorization", "")
            if not cabecalho.startswith("Bearer "):
                return jsonify({"erro": "Token de acesso ausente"}), 401
            try:
                usuario = _serializer().loads(cabecalho[7:].strip(), max_age=TOKEN_MAX_AGE)
            except SignatureExpired:
                return jsonify({"erro": "Sessão expirada. Faça login novamente"}), 401
            except BadSignature:
                return jsonify({"erro": "Token inválido"}), 401

            if usuario.get("tipo") not in PERMISSOES[permissao]:
                return jsonify({"erro": "Você não tem permissão para esta operação"}), 403
            g.usuario = usuario
            return func(*args, **kwargs)

        return wrapper

    return decorador


# =============================================================================
# VALIDAÇÃO DE ENTRADAS
# =============================================================================
def inteiro(valor, campo, minimo=0):
    if isinstance(valor, bool):
        raise ValueError(f"{campo} deve ser um número inteiro")
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{campo} deve ser um número inteiro")
    if numero < minimo:
        raise ValueError(f"{campo} deve ser maior ou igual a {minimo}")
    return numero


def texto(valor, campo, max_len):
    limpo = str(valor if valor is not None else "").strip()
    if not limpo:
        raise ValueError(f"{campo} é obrigatório")
    if len(limpo) > max_len:
        raise ValueError(f"{campo} deve ter no máximo {max_len} caracteres")
    return limpo


def _exigir_campos(data, campos):
    if not isinstance(data, dict) or not data:
        raise ValueError("Corpo da requisição deve ser um JSON")
    faltando = [c for c in campos if c not in data]
    if faltando:
        raise ValueError("Campos obrigatórios: " + ", ".join(faltando))


def validar_produto(data):
    """Devolve (dados_limpos, None) ou (None, mensagem_de_erro)."""
    try:
        _exigir_campos(data, ("nome", "preco", "quantidade"))
        try:
            preco = Decimal(str(data["preco"]).replace(",", ".")).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError("Preço deve ser um número")
        if not preco.is_finite() or preco < 0 or preco > Decimal("99999999.99"):
            raise ValueError("Preço fora do intervalo permitido")
        return {
            "nome": texto(data["nome"], "Nome", 100),
            "preco": preco,
            "quantidade": inteiro(data["quantidade"], "Quantidade"),
        }, None
    except ValueError as e:
        return None, str(e)


def validar_livro(data):
    try:
        _exigir_campos(data, ("titulo", "autor", "editora", "ano", "estoque"))
        return {
            "titulo": texto(data["titulo"], "Título", 150),
            "autor": texto(data["autor"], "Autor", 100),
            "editora": texto(data["editora"], "Editora", 100),
            "ano": inteiro(data["ano"], "Ano", minimo=1),
            "estoque": inteiro(data["estoque"], "Estoque"),
        }, None
    except ValueError as e:
        return None, str(e)


# =============================================================================
# TRATAMENTO DE ERROS (detalhes vão para o log, não para o cliente)
# =============================================================================
@app.errorhandler(HTTPException)
def erro_http(e):
    return jsonify({"erro": e.description}), e.code


@app.errorhandler(Exception)
def erro_inesperado(e):
    log.exception("Erro não tratado")
    return jsonify({"erro": "Erro interno do servidor"}), 500


# =============================================================================
# ROTAS: HOME E LOGIN
# =============================================================================
@app.get("/")
def home():
    return jsonify({"mensagem": "API ADS-5 (Produtos + Biblioteca) em funcionamento"})


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    login_ = str(data.get("login", "")).strip()
    senha = str(data.get("senha", ""))

    if not login_ or not senha:
        return jsonify({"erro": "Login e senha são obrigatórios"}), 400

    with db(commit=True) as cur:
        cur.execute("SELECT id, login, senha, tipo FROM Usuarios WHERE login = ?", (login_,))
        row = cur.fetchone()
        confere, regravar = (False, False) if row is None else verificar_senha(valor_linha(row, "senha"), senha)
        if confere and regravar:
            cur.execute(
                "UPDATE Usuarios SET senha = ? WHERE id = ?",
                (generate_password_hash(senha), valor_linha(row, "id")),
            )

    if not confere:
        return jsonify({"erro": "Credenciais inválidas"}), 401

    token = _serializer().dumps(
        {"id": valor_linha(row, "id"), "login": valor_linha(row, "login"), "tipo": valor_linha(row, "tipo")}
    )
    return jsonify(
        {
            "mensagem": "Autenticado com sucesso",
            "usuario": valor_linha(row, "login"),
            "tipo": valor_linha(row, "tipo"),
            "permissoes": permissoes_do_tipo(valor_linha(row, "tipo")),
            "token": token,
        }
    ), 200


# =============================================================================
# ROTAS: PRODUTOS
# =============================================================================
def produto_to_dict(row):
    return {
        "id": valor_linha(row, "id"),
        "nome": valor_linha(row, "nome"),
        "preco": float(valor_linha(row, "preco")),
        "quantidade": valor_linha(row, "quantidade"),
    }


@app.get("/produtos")
@requer("produtos:ler")
def listar_produtos():
    with db() as cur:
        cur.execute("SELECT id, nome, preco, quantidade FROM Produtos ORDER BY id")
        return jsonify([produto_to_dict(r) for r in cur.fetchall()]), 200


@app.get("/produtos/<int:id>")
@requer("produtos:ler")
def obter_produto(id):
    with db() as cur:
        cur.execute("SELECT id, nome, preco, quantidade FROM Produtos WHERE id = ?", (id,))
        row = cur.fetchone()
    if row is None:
        return jsonify({"erro": "Produto não encontrado"}), 404
    return jsonify(produto_to_dict(row)), 200


@app.post("/produtos")
@requer("produtos:escrever")
def incluir_produto():
    d, erro = validar_produto(request.get_json(silent=True))
    if erro:
        return jsonify({"erro": erro}), 400
    with db(commit=True) as cur:
        cur.execute(
            "INSERT INTO Produtos (nome, preco, quantidade) VALUES (?, ?, ?)",
            (d["nome"], d["preco"], d["quantidade"]),
        )
    return jsonify({"mensagem": "Produto incluído com sucesso"}), 201


@app.put("/produtos/<int:id>")
@requer("produtos:escrever")
def alterar_produto(id):
    d, erro = validar_produto(request.get_json(silent=True))
    if erro:
        return jsonify({"erro": erro}), 400
    with db(commit=True) as cur:
        cur.execute(
            "UPDATE Produtos SET nome = ?, preco = ?, quantidade = ? WHERE id = ?",
            (d["nome"], d["preco"], d["quantidade"], id),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "Produto não encontrado"}), 404
    return jsonify({"mensagem": "Produto alterado com sucesso"}), 200


@app.delete("/produtos/<int:id>")
@requer("produtos:escrever")
def excluir_produto(id):
    with db(commit=True) as cur:
        cur.execute("DELETE FROM Produtos WHERE id = ?", (id,))
        if cur.rowcount == 0:
            return jsonify({"erro": "Produto não encontrado"}), 404
    return jsonify({"mensagem": "Produto excluído com sucesso"}), 200


# =============================================================================
# ROTAS: LIVROS
# =============================================================================
LIVRO_COLUNAS = "id, titulo, autor, editora, ano, estoque"


def livro_to_dict(row):
    return {
        "id": valor_linha(row, "id"),
        "titulo": valor_linha(row, "titulo"),
        "autor": valor_linha(row, "autor"),
        "editora": valor_linha(row, "editora"),
        "ano": valor_linha(row, "ano"),
        "estoque": valor_linha(row, "estoque"),
    }


@app.get("/livros")
@requer("livros:ler")
def listar_livros():
    with db() as cur:
        cur.execute(f"SELECT {LIVRO_COLUNAS} FROM Livros ORDER BY id")
        return jsonify([livro_to_dict(r) for r in cur.fetchall()]), 200


@app.get("/livros/<int:id>")
@requer("livros:ler")
def consultar_livro(id):
    with db() as cur:
        cur.execute(f"SELECT {LIVRO_COLUNAS} FROM Livros WHERE id = ?", (id,))
        row = cur.fetchone()
    if row is None:
        return jsonify({"erro": "Livro não encontrado"}), 404
    return jsonify(livro_to_dict(row)), 200


@app.post("/livros")
@requer("livros:escrever")
def incluir_livro():
    d, erro = validar_livro(request.get_json(silent=True))
    if erro:
        return jsonify({"erro": erro}), 400
    with db(commit=True) as cur:
        cur.execute(
            "INSERT INTO Livros (titulo, autor, editora, ano, estoque) VALUES (?, ?, ?, ?, ?)",
            (d["titulo"], d["autor"], d["editora"], d["ano"], d["estoque"]),
        )
    return jsonify({"mensagem": "Livro incluído com sucesso"}), 201


@app.put("/livros/<int:id>")
@requer("livros:escrever")
def alterar_livro(id):
    d, erro = validar_livro(request.get_json(silent=True))
    if erro:
        return jsonify({"erro": erro}), 400
    with db(commit=True) as cur:
        cur.execute(
            "UPDATE Livros SET titulo = ?, autor = ?, editora = ?, ano = ?, estoque = ? WHERE id = ?",
            (d["titulo"], d["autor"], d["editora"], d["ano"], d["estoque"], id),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "Livro não encontrado"}), 404
    return jsonify({"mensagem": "Livro alterado com sucesso"}), 200


@app.delete("/livros/<int:id>")
@requer("livros:escrever")
def excluir_livro(id):
    with db(commit=True) as cur:
        cur.execute("SELECT 1 FROM Livros WHERE id = ?", (id,))
        if cur.fetchone() is None:
            return jsonify({"erro": "Livro não encontrado"}), 404

        cur.execute(
            "SELECT COUNT(*) FROM Emprestimos WHERE livro_id = ? AND data_devolucao IS NULL", (id,)
        )
        if cur.fetchone()[0] > 0:
            return jsonify({"erro": "Não é possível excluir livro com empréstimo em aberto"}), 409

        # Comportamento original: o histórico de devoluções do livro também é removido.
        cur.execute("DELETE FROM Emprestimos WHERE livro_id = ?", (id,))
        cur.execute("DELETE FROM Livros WHERE id = ?", (id,))
    return jsonify({"mensagem": "Livro excluído com sucesso"}), 200


@app.get("/livros-disponiveis")
@requer("livros:ler")
def listar_livros_disponiveis():
    with db() as cur:
        cur.execute(f"SELECT {LIVRO_COLUNAS} FROM Livros WHERE estoque > 0 ORDER BY titulo")
        return jsonify([livro_to_dict(r) for r in cur.fetchall()]), 200


@app.get("/livros-emprestados")
@requer("livros:ler")  # só títulos e quantidades, sem nomes de leitores
def listar_livros_emprestados():
    with db() as cur:
        cur.execute(
            """
            SELECT l.id, l.titulo, l.autor, COUNT(e.id) AS quantidade_emprestada
            FROM Livros l
            INNER JOIN Emprestimos e ON e.livro_id = l.id
            WHERE e.data_devolucao IS NULL
            GROUP BY l.id, l.titulo, l.autor
            ORDER BY l.titulo
            """
        )
        return jsonify(
            [
                {
                    "id": valor_linha(r, "id"),
                    "titulo": valor_linha(r, "titulo"),
                    "autor": valor_linha(r, "autor"),
                    "quantidade_emprestada": valor_linha(r, "quantidade_emprestada"),
                }
                for r in cur.fetchall()
            ]
        ), 200


# =============================================================================
# ROTAS: EMPRÉSTIMOS E DEVOLUÇÕES
# =============================================================================
@app.post("/emprestimos")
@requer("emprestimos:gerenciar")
def realizar_emprestimo():
    data = request.get_json(silent=True) or {}
    try:
        livro_id = inteiro(data.get("livro_id"), "livro_id", minimo=1)
        nome_aluno = texto(data.get("nome_aluno"), "nome_aluno", 100)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    with db(commit=True) as cur:
        # Baixa de estoque numa única instrução: dois empréstimos simultâneos
        # não conseguem levar o último exemplar.
        cur.execute("UPDATE Livros SET estoque = estoque - 1 WHERE id = ? AND estoque > 0", (livro_id,))
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM Livros WHERE id = ?", (livro_id,))
            if cur.fetchone() is None:
                return jsonify({"erro": "Livro não encontrado"}), 404
            return jsonify({"erro": "Livro sem estoque disponível"}), 409

        cur.execute("INSERT INTO Emprestimos (livro_id, nome_aluno) VALUES (?, ?)", (livro_id, nome_aluno))
    return jsonify({"mensagem": "Empréstimo realizado com sucesso"}), 201


@app.post("/devolucoes")
@requer("emprestimos:gerenciar")
def realizar_devolucao():
    data = request.get_json(silent=True) or {}
    try:
        emprestimo_id = inteiro(data.get("emprestimo_id"), "emprestimo_id", minimo=1)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    with db(commit=True) as cur:
        cur.execute(
            "UPDATE Emprestimos SET data_devolucao = CURRENT_TIMESTAMP WHERE id = ? AND data_devolucao IS NULL",
            (emprestimo_id,),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "Empréstimo aberto não encontrado"}), 404

        cur.execute("SELECT livro_id FROM Emprestimos WHERE id = ?", (emprestimo_id,))
        livro_id = valor_linha(cur.fetchone(), "livro_id")
        cur.execute("UPDATE Livros SET estoque = estoque + 1 WHERE id = ?", (livro_id,))
    return jsonify({"mensagem": "Devolução realizada com sucesso"}), 200


@app.get("/emprestimos-abertos")
@requer("emprestimos:ler")
def listar_emprestimos_abertos():
    with db() as cur:
        cur.execute(
            """
            SELECT e.id, e.livro_id, l.titulo, e.nome_aluno,
                   strftime('%Y-%m-%dT%H:%M:%S', e.data_emprestimo) AS data_emprestimo
            FROM Emprestimos e
            INNER JOIN Livros l ON l.id = e.livro_id
            WHERE e.data_devolucao IS NULL
            ORDER BY e.data_emprestimo DESC
            """
        )
        return jsonify(
            [
                {
                    "id": valor_linha(r, "id"),
                    "livro_id": valor_linha(r, "livro_id"),
                    "titulo": valor_linha(r, "titulo"),
                    "nome_aluno": valor_linha(r, "nome_aluno"),
                    "data_emprestimo": valor_linha(r, "data_emprestimo"),
                }
                for r in cur.fetchall()
            ]
        ), 200


# =============================================================================
# EXECUÇÃO
# =============================================================================
if __name__ == "__main__":
    if SECRET_KEY.startswith("ads5-chave-de-desenvolvimento"):
        log.warning("ADS_SECRET_KEY não definida: usando chave de desenvolvimento.")
    if DB_BACKEND == "sqlite":
        inicializar_banco_sqlite()
    criar_usuarios_iniciais()
    app.run(host=HOST, port=PORT, debug=os.getenv("ADS_DEBUG") == "1")
