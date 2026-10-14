"""Cliente interativo (menu) do sistema ADS-5: Produtos + Biblioteca.

Os itens de menu exibidos dependem das permissões devolvidas pela API no login.
Execução:  python cliente.py   (com a API rodando: python api.py)
"""
import getpass
import os
import sys
from decimal import Decimal, InvalidOperation

import requests

BASE_URL = os.getenv("ADS_API_URL", "http://127.0.0.1:5000")
TIMEOUT = 10


# ------------------------------------------------------------------ API
class Api:
    def __init__(self):
        self.sessao = requests.Session()
        self.usuario = None
        self.tipo = None
        self.permissoes = set()

    def pode(self, permissao):
        return permissao is None or permissao in self.permissoes

    def chamar(self, metodo, caminho, **kwargs):
        """Devolve (status, corpo_json). Nunca levanta por resposta não-JSON."""
        res = self.sessao.request(metodo, BASE_URL + caminho, timeout=TIMEOUT, **kwargs)
        try:
            corpo = res.json()
        except ValueError:
            corpo = {"erro": f"Resposta inválida da API (HTTP {res.status_code})"}
        return res.status_code, corpo

    def login(self, login, senha):
        status, corpo = self.chamar("POST", "/login", json={"login": login, "senha": senha})
        if status != 200:
            return False, corpo.get("erro", "Erro desconhecido")
        self.usuario, self.tipo = corpo["usuario"], corpo["tipo"]
        self.permissoes = set(corpo["permissoes"])
        self.sessao.headers["Authorization"] = f"Bearer {corpo['token']}"
        return True, corpo["mensagem"]


api = Api()


# ------------------------------------------------------------- entrada/saída
def mostrar(status, corpo):
    if status == 401:
        print("[ERRO]", corpo.get("erro", "Não autenticado"), "- reinicie o cliente e faça login.")
    elif "mensagem" in corpo:
        print("[OK]", corpo["mensagem"])
    elif "erro" in corpo:
        print("[ERRO]", corpo["erro"])
    else:
        print(corpo)


def ler_texto(prompt):
    while True:
        valor = input(prompt).strip()
        if valor:
            return valor
        print("[!] Campo obrigatório.")


def ler_int(prompt, minimo=0):
    while True:
        try:
            numero = int(input(prompt).strip())
        except ValueError:
            print("[!] Digite um número inteiro.")
            continue
        if numero < minimo:
            print(f"[!] O valor deve ser maior ou igual a {minimo}.")
            continue
        return numero


def ler_preco(prompt):
    while True:
        try:
            valor = Decimal(input(prompt).strip().replace(",", "."))
            if valor.is_finite() and valor >= 0:
                return str(valor)
        except InvalidOperation:
            pass
        print("[!] Digite um preço válido (ex.: 19,90).")


def mostrar_lista(status, corpo, vazio, formatar, titulo=None):
    if not isinstance(corpo, list):
        mostrar(status, corpo)
        return
    if not corpo:
        print(f"[INFO] {vazio}")
        return
    if titulo:
        print(f"\n--- {titulo} ---")
    for item in corpo:
        print(formatar(item))


# ---------------------------------------------------------------- formatos
def fmt_produto(p):
    return f"ID: {p['id']} | Nome: {p['nome']} | Preço: R${p['preco']:.2f} | Estoque: {p['quantidade']}"


def fmt_livro(l):
    return (
        f"ID: {l['id']} | Título: {l['titulo']} | Autor: {l['autor']} | "
        f"Editora: {l['editora']} | Ano: {l['ano']} | Estoque: {l['estoque']}"
    )


def fmt_emprestimo(e):
    return (
        f"Empréstimo: {e['id']} | Livro ID: {e['livro_id']} | Título: {e['titulo']} | "
        f"Leitor: {e['nome_aluno']} | Data: {e['data_emprestimo']}"
    )


def fmt_emprestado(l):
    return (
        f"ID: {l['id']} | Título: {l['titulo']} | Autor: {l['autor']} | "
        f"Quantidade emprestada: {l['quantidade_emprestada']}"
    )


# ------------------------------------------------------------------ produtos
def produto_incluir():
    print("\n--- INCLUIR PRODUTO ---")
    corpo = {
        "nome": ler_texto("Nome do produto: "),
        "preco": ler_preco("Preço: "),
        "quantidade": ler_int("Quantidade: "),
    }
    mostrar(*api.chamar("POST", "/produtos", json=corpo))


def produto_alterar():
    print("\n--- ALTERAR PRODUTO ---")
    id_ = ler_int("ID do produto: ", 1)
    corpo = {
        "nome": ler_texto("Novo nome: "),
        "preco": ler_preco("Novo preço: "),
        "quantidade": ler_int("Nova quantidade: "),
    }
    mostrar(*api.chamar("PUT", f"/produtos/{id_}", json=corpo))


def produto_excluir():
    print("\n--- EXCLUIR PRODUTO ---")
    id_ = ler_int("ID do produto: ", 1)
    mostrar(*api.chamar("DELETE", f"/produtos/{id_}"))


def produto_consultar():
    print("\n--- CONSULTAR PRODUTO ---")
    id_ = ler_int("ID do produto: ", 1)
    status, corpo = api.chamar("GET", f"/produtos/{id_}")
    if status == 200:
        print(fmt_produto(corpo))
    else:
        mostrar(status, corpo)


def produto_listar():
    status, corpo = api.chamar("GET", "/produtos")
    mostrar_lista(status, corpo, "Nenhum produto cadastrado.", fmt_produto, "LISTA DE PRODUTOS")


# -------------------------------------------------------------------- livros
def _ler_dados_livro(prefixo=""):
    return {
        "titulo": ler_texto(f"{prefixo}Título: "),
        "autor": ler_texto(f"{prefixo}Autor: "),
        "editora": ler_texto(f"{prefixo}Editora: "),
        "ano": ler_int(f"{prefixo}Ano: ", 1),
        "estoque": ler_int(f"{prefixo}Estoque: "),
    }


def livro_incluir():
    print("\n--- INCLUIR LIVRO ---")
    mostrar(*api.chamar("POST", "/livros", json=_ler_dados_livro()))


def livro_alterar():
    print("\n--- ALTERAR LIVRO ---")
    id_ = ler_int("ID do livro: ", 1)
    mostrar(*api.chamar("PUT", f"/livros/{id_}", json=_ler_dados_livro("Novo(a) ")))


def livro_excluir():
    print("\n--- EXCLUIR LIVRO ---")
    id_ = ler_int("ID do livro: ", 1)
    mostrar(*api.chamar("DELETE", f"/livros/{id_}"))


def livro_consultar():
    print("\n--- CONSULTAR LIVRO ---")
    id_ = ler_int("ID do livro: ", 1)
    status, corpo = api.chamar("GET", f"/livros/{id_}")
    if status == 200:
        print(fmt_livro(corpo))
    else:
        mostrar(status, corpo)


def livro_listar():
    status, corpo = api.chamar("GET", "/livros")
    mostrar_lista(status, corpo, "Nenhum livro cadastrado.", fmt_livro, "LISTAGEM DE LIVROS")


def livro_listar_disponiveis():
    status, corpo = api.chamar("GET", "/livros-disponiveis")
    mostrar_lista(status, corpo, "Nenhum livro disponível.", fmt_livro, "LIVROS COM ESTOQUE > 0")


def livro_listar_emprestados():
    status, corpo = api.chamar("GET", "/livros-emprestados")
    mostrar_lista(status, corpo, "Nenhum livro emprestado.", fmt_emprestado, "LIVROS EMPRESTADOS")


def emprestimo_realizar():
    print("\n--- EMPRÉSTIMO ---")
    corpo = {"livro_id": ler_int("ID do livro: ", 1), "nome_aluno": ler_texto("Nome do aluno/leitor: ")}
    mostrar(*api.chamar("POST", "/emprestimos", json=corpo))


def emprestimo_listar_abertos():
    status, corpo = api.chamar("GET", "/emprestimos-abertos")
    mostrar_lista(status, corpo, "Nenhum empréstimo aberto.", fmt_emprestimo, "EMPRÉSTIMOS ABERTOS")
    return corpo if status == 200 and isinstance(corpo, list) else []


def emprestimo_devolver():
    print("\n--- DEVOLUÇÃO ---")
    if not emprestimo_listar_abertos():
        return
    id_ = ler_int("\nID do empréstimo a devolver: ", 1)
    mostrar(*api.chamar("POST", "/devolucoes", json={"emprestimo_id": id_}))


# --------------------------------------------------------------------- menus
# (rótulo, função, permissão exigida)
MENU_PRODUTOS = [
    ("Incluir produto", produto_incluir, "produtos:escrever"),
    ("Alterar produto", produto_alterar, "produtos:escrever"),
    ("Excluir produto", produto_excluir, "produtos:escrever"),
    ("Consultar produto pelo ID", produto_consultar, "produtos:ler"),
    ("Listar todos os produtos", produto_listar, "produtos:ler"),
]

MENU_BIBLIOTECA = [
    ("Incluir livro", livro_incluir, "livros:escrever"),
    ("Alterar livro", livro_alterar, "livros:escrever"),
    ("Excluir livro", livro_excluir, "livros:escrever"),
    ("Consultar livro pelo ID", livro_consultar, "livros:ler"),
    ("Listar todos os livros", livro_listar, "livros:ler"),
    ("Listar livros com estoque > 0", livro_listar_disponiveis, "livros:ler"),
    ("Realizar empréstimo", emprestimo_realizar, "emprestimos:gerenciar"),
    ("Realizar devolução", emprestimo_devolver, "emprestimos:gerenciar"),
    ("Listar livros emprestados", livro_listar_emprestados, "livros:ler"),
    ("Listar empréstimos abertos", emprestimo_listar_abertos, "emprestimos:ler"),
]


def executar_menu(titulo, itens, rotulo_saida):
    """Menu genérico: mostra só os itens permitidos e numera em sequência."""
    visiveis = [(r, f) for r, f, perm in itens if api.pode(perm)]
    while True:
        print(f"\n--- {titulo} ---")
        for n, (rotulo, _) in enumerate(visiveis, start=1):
            print(f"{n}. {rotulo}")
        print(f"0. {rotulo_saida}")

        opcao = input("Escolha uma opção: ").strip()
        if opcao == "0":
            return
        if not (opcao.isdigit() and 1 <= int(opcao) <= len(visiveis)):
            print("[!] Opção inválida.")
            continue
        try:
            visiveis[int(opcao) - 1][1]()
        except requests.exceptions.ConnectionError:
            print(f"[ERRO] Não foi possível conectar à API em {BASE_URL}. Execute: python api.py")
        except requests.exceptions.Timeout:
            print("[ERRO] A API demorou demais para responder.")
        except requests.exceptions.RequestException as e:
            print("[ERRO] Falha na requisição:", e)


def menu_principal():
    secoes = [
        ("Produtos", MENU_PRODUTOS),
        ("Biblioteca", MENU_BIBLIOTECA),
    ]
    # Só mostra a seção se o usuário puder usar ao menos um item dela.
    secoes = [(n, itens) for n, itens in secoes if any(api.pode(p) for _, _, p in itens)]

    while True:
        print("\n===================================")
        print("        SISTEMA ADS-5")
        print(f" Usuário: {api.usuario} ({api.tipo})")
        print("===================================")
        for n, (nome, _) in enumerate(secoes, start=1):
            print(f"{n}. {nome}")
        print("0. Sair")

        opcao = input("Escolha uma opção: ").strip()
        if opcao == "0":
            print("Saindo do sistema...")
            return
        if opcao.isdigit() and 1 <= int(opcao) <= len(secoes):
            nome, itens = secoes[int(opcao) - 1]
            executar_menu(nome.upper(), itens, "Voltar")
        else:
            print("[!] Opção inválida.")


def fazer_login(tentativas=3):
    print("=====================================")
    print("===        SISTEMA ADS-5          ===")
    print("=====================================")
    for _ in range(tentativas):
        login = input("Login: ").strip()
        senha = getpass.getpass("Senha: ")
        try:
            ok, mensagem = api.login(login, senha)
        except requests.exceptions.RequestException:
            print(f"[ERRO] Não foi possível conectar à API em {BASE_URL}. Execute: python api.py")
            return False
        if ok:
            print(f"\n[+] {mensagem} - Bem-vindo, {api.usuario}!")
            return True
        print("[-] Falha na autenticação:", mensagem)
    return False


def main():
    if not fazer_login():
        print("Acesso negado. Encerrando.")
        sys.exit(1)
    menu_principal()


if __name__ == "__main__":
    main()
