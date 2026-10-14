import importlib.util
import os
import tempfile
import unittest


class TestSqliteFallback(unittest.TestCase):
    def test_sqlite_database_works(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.environ['ADS_DB_BACKEND'] = 'sqlite'
        os.environ['ADS_DB_PATH'] = path
        os.environ['ADS_SECRET_KEY'] = 'test-secret'

        spec = importlib.util.spec_from_file_location('ads5_api', 'api.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.inicializar_banco_sqlite()
        module.criar_usuarios_iniciais()

        with module.db() as cur:
            cur.execute('SELECT login FROM Usuarios WHERE login = ?', ('admin',))
            self.assertIsNotNone(cur.fetchone())

        client = module.app.test_client()
        resp = client.post('/login', json={'login': 'admin', 'senha': 'admin'})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertIn('token', payload)
        self.assertEqual(payload['usuario'], 'admin')

        os.remove(path)


if __name__ == '__main__':
    unittest.main()
