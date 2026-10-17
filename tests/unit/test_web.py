"""Deterministic HTTP integration against a local test server."""
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from focu.web import FetchError, fetch_page


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/missing":
            self.send_error(404)
            return
        if self.path == "/large":
            payload = b"x" * 1000
        else:
            payload = b"<html><head><title>Example Research</title></head><body><main>Evidence body</main><script>hidden</script></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class WebFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_extract_title_and_text(self):
        page = fetch_page(self.base + "/")
        self.assertEqual(page.title, "Example Research")
        self.assertIn("Evidence body", page.text)
        self.assertNotIn("hidden", page.text)

    def test_http_404_is_not_silent(self):
        with self.assertRaises(FetchError):
            fetch_page(self.base + "/missing")

    def test_max_response_size(self):
        with self.assertRaises(FetchError):
            fetch_page(self.base + "/large", max_bytes=20)

    def test_reject_non_http(self):
        with self.assertRaises(ValueError):
            fetch_page("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
