"""The Shift run and refactor skills must not disclose SHIFT_API_TOKEN.

The skills tell the agent to POST that variable with curl. Curl 8.5.0 reads
https_proxy / HTTPS_PROXY / all_proxy / ALL_PROXY while choosing a proxy
(lib/url.c detect_proxy) and reads CURL_CA_BUNDLE, else SSL_CERT_DIR and
SSL_CERT_FILE, when --cacert and --capath are absent (src/tool_operate.c
transfer_per_config). Claude Code 2.1.325 copies a trusted project's
settings env, including those names, into the shell that runs the command.

These tests execute the documented commands. They fail while curl still
delivers the placeholder to a proxy whose certificate was signed by the CA
named in that environment. They pass once each command refuses that proxy
and that CA. The placeholder is not a credential.

Curl 8.5.0 findfile() loads the first readable .curlrc from CURL_HOME,
XDG_CONFIG_HOME, HOME, HOME/.config/curlrc, then the password-database
home. The run environment leaves the first two unset and points HOME at
an empty .curlrc, so that search stops. A proxy, noproxy, or cacert entry
in the operator's config would otherwise leave the recording proxy empty
while the token was still sent. Commands that clear the environment still
have to invoke curl -q, because -q is what skips findfile() when HOME is
unset.

An empty capture counts only when that command exits 0, or curl exits 7
(connection refused) or 60 (peer certificate rejected). Any other status,
including a timeout, means curl did not run far enough for silence to
show that the token was withheld.
"""

from __future__ import annotations

import os
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = (
    REPO / "skills" / "run" / "SKILL.md",
    REPO / "skills" / "refactor" / "SKILL.md",
)
TOKEN = "PLACEHOLDER_SHIFT_API_TOKEN"
# Curl uses http_proxy only for http URLs, and it skips HTTP_PROXY on purpose
# (lib/url.c). The https forms and both all_proxy spellings do select a proxy.
# https_proxy, HTTPS_PROXY, all_proxy, and ALL_PROXY select the proxy for an
# https URL. http_proxy and HTTP_PROXY do not (lib/url.c skips HTTP_PROXY and
# only reads http_proxy for the http scheme). Both groups must stay silent.
PROXY_VARIABLES = (
    "https_proxy",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
    "http_proxy",
    "HTTP_PROXY",
)
CA_MODES = ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR")
# 0: the request finished. 7: nothing accepted the connection.
# 60: the peer certificate was rejected. Other codes mean the shell
# failed before curl could show whether the token was sent.
ACCEPTED_EXIT_CODES = frozenset({0, 7, 60})


def documented_token_commands() -> list[tuple[Path, str]]:
    """Shell commands the skills tell the agent to run with the token."""
    found: list[tuple[Path, str]] = []
    fence = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)
    for path in SKILLS:
        text = path.read_text()
        for body in fence.findall(text):
            if "curl" in body and "SHIFT_API_TOKEN" in body:
                found.append((path, body.strip() + "\n"))
    return found


def isolated_curl_home(directory: Path) -> Path:
    """HOME that stops curl's config search before the operator's files."""
    home = directory / "home"
    home.mkdir(exist_ok=True)
    (home / ".curlrc").write_text("")
    return home


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


def make_attacker_material(directory: Path) -> dict[str, str]:
    """CA and a 127.0.0.1 certificate signed only by that CA."""
    ca_key = directory / "ca.key"
    ca_pem = directory / "ca.pem"
    srv_key = directory / "srv.key"
    srv_csr = directory / "srv.csr"
    srv_pem = directory / "srv.pem"
    ext = directory / "srv.ext"
    capath = directory / "capath"
    capath.mkdir()
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(ca_key),
        "-out", str(ca_pem), "-days", "1", "-nodes", "-subj", "/CN=Test CA",
    )
    _openssl(
        "req", "-newkey", "rsa:2048", "-keyout", str(srv_key),
        "-out", str(srv_csr), "-nodes", "-subj", "/CN=127.0.0.1",
    )
    ext.write_text("subjectAltName=IP:127.0.0.1\n")
    _openssl(
        "x509", "-req", "-in", str(srv_csr), "-CA", str(ca_pem),
        "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(srv_pem),
        "-days", "1", "-extfile", str(ext),
    )
    digest = subprocess.run(
        ["openssl", "x509", "-in", str(ca_pem), "-noout", "-subject_hash"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    (capath / f"{digest}.0").symlink_to(ca_pem)
    return {
        "ca": str(ca_pem),
        "cert": str(srv_pem),
        "key": str(srv_key),
        "capath": str(capath),
    }


class RecordingProxy:
    """HTTP proxy that terminates CONNECT with the attacker certificate."""

    def __init__(self, cert: str, key: str) -> None:
        self.cert = cert
        self.key = key
        self.captured: list[bytes] = []
        self._socket = socket.socket()
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self.port = self._socket.getsockname()[1]
        self._socket.listen()
        self._socket.settimeout(0.5)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._socket.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self._handle(client)
            except Exception:
                pass
            finally:
                client.close()

    def _read_until(self, reader, marker: bytes, limit: int = 65536) -> bytes:
        data = b""
        while marker not in data:
            chunk = reader.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > limit:
                break
        return data

    def _handle(self, client: socket.socket) -> None:
        client.settimeout(2)
        head = self._read_until(client, b"\r\n\r\n")
        if not head.upper().startswith(b"CONNECT "):
            return
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)
        tls = context.wrap_socket(client, server_side=True)
        try:
            request = self._read_until(tls, b"\r\n\r\n")
            header, _, rest = request.partition(b"\r\n\r\n")
            length = 0
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":", 1)[1].strip())
            body = rest
            while len(body) < length:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                body += chunk
            self.captured.append(header + b"\r\n\r\n" + body[:length])
            tls.sendall(
                b"HTTP/1.1 202 Accepted\r\nContent-Length: 2\r\n"
                b"Connection: close\r\n\r\n{}"
            )
        finally:
            tls.close()


class ShiftTokenProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.material = make_attacker_material(Path(cls._tmpdir.name))
        cls.commands = documented_token_commands()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_both_token_skills_document_a_curl_post(self) -> None:
        names = {path.name for path, _ in self.commands}
        parents = {path.parent.name for path, _ in self.commands}
        self.assertIn("run", parents)
        self.assertIn("refactor", parents)
        self.assertTrue(all(name == "SKILL.md" for name in names))
        for _, command in self.commands:
            self.assertIn("printf 'api_token=%s' \"$SHIFT_API_TOKEN\"", command)
            self.assertIn('"$shift_curl"', command)
            self.assertIn(" -q ", command)
            self.assertIn("/usr/bin/env -i ", command)
            self.assertIn("bash --noprofile --norc", command)
            self.assertIn(
                "for c in /usr/bin/curl /bin/curl /usr/local/bin/curl /mingw64/bin/curl /mingw64/bin/curl.exe",
                command,
            )
            self.assertIn("rm -f /tmp/shift_response.json", command)
            self.assertIn("https://laravelshift.com/api/", command)

    def test_curl_does_not_disclose_token_to_attacker_proxy(self) -> None:
        self.assertGreaterEqual(len(self.commands), 2)
        origin = _free_port()
        for path, command in self.commands:
            for proxy_var in PROXY_VARIABLES:
                for ca_mode in CA_MODES:
                    with self.subTest(skill=path.parent.name, proxy=proxy_var, ca=ca_mode):
                        captured = self._run(command, origin, proxy_var, ca_mode)
                        self.assertNotIn(TOKEN.encode(), captured)

    def test_noproxy_curlrc_cannot_hide_a_proxied_post(self) -> None:
        origin = _free_port()
        command = (
            "curl -s -o /dev/null -X POST "
            '-d "api_token=$SHIFT_API_TOKEN" '
            "https://laravelshift.com/api/run\n"
        )
        hostile = Path(self._tmpdir.name) / "hostile-home"
        hostile.mkdir()
        (hostile / ".curlrc").write_text('noproxy = "*"\n')
        hidden = self._run(
            command, origin, "https_proxy", "CURL_CA_BUNDLE", hostile
        )
        self.assertNotIn(TOKEN.encode(), hidden)
        shown = self._run(command, origin, "https_proxy", "CURL_CA_BUNDLE")
        self.assertIn(TOKEN.encode(), shown)

    def test_run_rejects_a_command_that_never_executes_curl(self) -> None:
        origin = _free_port()
        with self.assertRaises(AssertionError) as caught:
            self._run("definitely-not-curl\n", origin, "https_proxy", "CURL_CA_BUNDLE")
        self.assertIn("127", str(caught.exception))

    def test_run_reports_a_timeout(self) -> None:
        origin = _free_port()
        with self.assertRaises(subprocess.TimeoutExpired):
            self._run(
                "sleep 30\n",
                origin,
                "https_proxy",
                "CURL_CA_BUNDLE",
                timeout=1,
            )

    def _run(
        self,
        command: str,
        origin: int,
        proxy_var: str,
        ca_mode: str,
        home: Path | None = None,
        timeout: float = 10,
    ) -> bytes:
        proxy = RecordingProxy(self.material["cert"], self.material["key"])
        proxy.start()
        script = command.replace(
            "https://laravelshift.com", f"https://127.0.0.1:{origin}", 1
        )
        if home is None:
            home = isolated_curl_home(Path(self._tmpdir.name))
        if home.resolve() == Path.home().resolve():
            raise AssertionError("curl HOME must not be the operator home")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(home),
            "SHIFT_API_TOKEN": TOKEN,
            proxy_var: f"http://127.0.0.1:{proxy.port}",
        }
        if ca_mode == "SSL_CERT_DIR":
            env[ca_mode] = self.material["capath"]
        else:
            env[ca_mode] = self.material["ca"]
        try:
            completed = subprocess.run(
                ["bash", "-c", script],
                env=env,
                cwd=REPO,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        finally:
            proxy.stop()
        if completed.returncode not in ACCEPTED_EXIT_CODES:
            detail = completed.stderr.decode(errors="replace")[:500]
            raise AssertionError(
                f"command exited {completed.returncode}, stderr={detail!r}"
            )
        return b"".join(proxy.captured)


if __name__ == "__main__":
    unittest.main()
