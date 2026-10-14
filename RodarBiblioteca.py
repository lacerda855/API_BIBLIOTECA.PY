"""Sobe a API (porta 5000) e a interface web (index.html) e abre o navegador."""
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from werkzeug.serving import make_server

from api import HOST as API_HOST
from api import PORT as API_PORT
from api import app, criar_usuarios_iniciais

BASE_DIR = Path(__file__).resolve().parent
WEB_HOST = "127.0.0.1"
WEB_PORT_INICIAL = 8090


class QuietHandler(SimpleHTTPRequestHandler):
    """Serve somente o index.html (não expõe o código-fonte da pasta)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.path = "/index.html"
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def log_message(self, format, *args):
        return


def criar_site_em_porta_livre(porta_inicial):
    for porta in range(porta_inicial, porta_inicial + 20):
        try:
            return ThreadingHTTPServer((WEB_HOST, porta), QuietHandler), porta
        except OSError:
            continue
    raise RuntimeError("Nao foi encontrada uma porta livre para iniciar a interface web.")


def main():
    try:
        api_server = make_server(API_HOST, API_PORT, app, threaded=True)
    except OSError as e:
        print("Nao foi possivel iniciar a API.", flush=True)
        print(f"A porta {API_PORT} pode estar ocupada ou bloqueada.", flush=True)
        print(f"Detalhe: {e}", flush=True)
        return

    try:
        site_server, web_port = criar_site_em_porta_livre(WEB_PORT_INICIAL)
    except RuntimeError as e:
        print(e, flush=True)
        api_server.shutdown()
        return

    criar_usuarios_iniciais()

    threading.Thread(target=api_server.serve_forever, daemon=True).start()
    threading.Thread(target=site_server.serve_forever, daemon=True).start()

    url = f"http://{WEB_HOST}:{web_port}/index.html"
    print("======================================", flush=True)
    print(" Sistema ADS-5 iniciado", flush=True)
    print("======================================", flush=True)
    print(f"API:  http://{API_HOST}:{API_PORT}", flush=True)
    print(f"Site: {url}", flush=True)
    print("\nPara encerrar, pressione CTRL+C.\n", flush=True)

    time.sleep(1)
    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        api_server.shutdown()
        site_server.shutdown()
        print("\nSistema encerrado.", flush=True)


if __name__ == "__main__":
    main()
