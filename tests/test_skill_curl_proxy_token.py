"""Shift skill curl commands must not deliver the API token to a proxy.

The refactor and run skills tell the agent to POST the Shift API token with
curl. Curl's own default is to honor a proxy and a CA bundle from the
environment. These tests run the fenced commands from the skills in an
environment that supplies those settings, against a local proxy that terminates
TLS with a certificate signed by that CA.

A command that still inherits the proxy and CA settings makes the test fail,
because the proxy then records the placeholder token. A command that ignores
those settings, or that refuses the substituted CA, makes the test pass.

The network namespace has no route except loopback, so a command that skips
the proxy cannot reach the host named in the skill.

Run from the repository root:

    python3 -m unittest tests.test_skill_curl_proxy_token -v
"""

import fcntl
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
ORIGIN = "laravelshift.com"
TOKEN_POST_URL = "https://laravelshift.com/"

# Names curl 8.5.0 consults for an https URL, and the CA inputs the curl CLI
# copies onto the transfer when the command does not pass --cacert/--capath.
PROXY_ENV_NAMES = (
    "https_proxy",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
    "http_proxy",
    "HTTP_PROXY",
    "no_proxy",
    "NO_PROXY",
)
CA_ENV_NAMES = ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR")

# Each pair is one way the documented request can be steered. http_proxy and
# HTTP_PROXY are cleared by the environment setup but are not cases: curl does
# not select them for an https URL.
ATTACK_CASES = (
    ("https_proxy", "CURL_CA_BUNDLE"),
    ("HTTPS_PROXY", "CURL_CA_BUNDLE"),
    ("all_proxy", "CURL_CA_BUNDLE"),
    ("ALL_PROXY", "CURL_CA_BUNDLE"),
    ("https_proxy", "SSL_CERT_FILE"),
    ("https_proxy", "SSL_CERT_DIR"),
)

FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
CONTROL_TOKEN = "control-placeholder-not-a-secret"
SKILL_TOKEN = "skill-placeholder-not-a-secret"


def _bring_up_loopback():
    """Bring up lo inside a fresh network namespace. No iproute2 required."""
    iff_up = 0x1
    siocgifflags = 0x8913
    siocsifflags = 0x8914
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("16sH14s", b"lo", 0, b"\x00" * 14)
        current = fcntl.ioctl(sock, siocgifflags, packed)
        flags = struct.unpack("16sH", current[:18])[1]
        updated = struct.pack("16sH14s", b"lo", flags | iff_up, b"\x00" * 14)
        fcntl.ioctl(sock, siocsifflags, updated)
    finally:
        sock.close()


def _default_routes():
    routes = []
    text = Path("/proc/net/route").read_text()
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "00000000":
            routes.append(fields[0])
    return routes


def setUpModule():
    if os.environ.get("SKILL_CURL_TEST_ISOLATED") == "1":
        _bring_up_loopback()
        routes = _default_routes()
        if routes:
            raise RuntimeError(
                "refusing to run with a default route via " + ",".join(routes)
            )
        return

    env = os.environ.copy()
    env["SKILL_CURL_TEST_ISOLATED"] = "1"
    for name in PROXY_ENV_NAMES + CA_ENV_NAMES:
        env.pop(name, None)
    # Replace this process so the suite runs where the only reachable address
    # is loopback. A command that ignores the proxy then fails closed.
    os.execvpe(
        "unshare",
        [
            "unshare",
            "--net",
            "--map-root-user",
            sys.executable,
            "-m",
            "unittest",
            "tests.test_skill_curl_proxy_token",
            "-v",
        ],
        env,
    )


def _token_post_blocks():
    """Every fenced shell command that posts the token to the Shift API."""
    found = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = path.read_text()
        blocks = []
        for block in FENCE.findall(text):
            if "SHIFT_API_TOKEN" in block and TOKEN_POST_URL in block and "curl" in block:
                blocks.append(block)
        mentions_token = "SHIFT_API_TOKEN" in text
        mentions_curl = "curl " in text or "\ncurl " in text or text.startswith("curl ")
        if mentions_token and mentions_curl and not blocks:
            raise AssertionError(
                f"{path} mentions the token and curl outside a fenced request"
            )
        if blocks:
            found[str(path.relative_to(REPO_ROOT))] = blocks
    if not found:
        raise AssertionError("no skill posts the token with curl")
    return found


def _openssl(*args, cwd):
    result = subprocess.run(
        ["openssl", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "openssl " + " ".join(args) + "\n" + result.stderr
        )
    return result


def _make_ca(directory):
    """CA and a server certificate for the host named in the skill."""
    ca_key = directory / "ca.key"
    ca_pem = directory / "ca.pem"
    server_key = directory / "server.key"
    server_pem = directory / "server.pem"
    ext = directory / "server.ext"
    ext.write_text(
        "\n".join(
            [
                "basicConstraints=CA:FALSE",
                "keyUsage=digitalSignature,keyEncipherment",
                "extendedKeyUsage=serverAuth",
                "subjectAltName=DNS:laravelshift.com",
                "",
            ]
        )
    )
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(ca_key),
        "-out",
        str(ca_pem),
        "-days",
        "1",
        "-nodes",
        "-subj",
        "/CN=SkillTestCA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        cwd=directory,
    )
    csr = directory / "server.csr"
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(server_key),
        "-out",
        str(csr),
        "-nodes",
        "-subj",
        "/CN=laravelshift.com",
        cwd=directory,
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        str(csr),
        "-CA",
        str(ca_pem),
        "-CAkey",
        str(ca_key),
        "-CAcreateserial",
        "-out",
        str(server_pem),
        "-days",
        "1",
        "-extfile",
        str(ext),
        cwd=directory,
    )
    capath = directory / "capath"
    capath.mkdir()
    shutil.copy(ca_pem, capath / "ca.pem")
    _openssl("rehash", str(capath), cwd=directory)
    return ca_pem, capath, server_pem, server_key


class RecordingProxy:
    """HTTP proxy that terminates CONNECT with the supplied server certificate.

    This is the proxy half of curl's HTTPS tunnel: a cleartext CONNECT, then
    TLS, then the origin request. Nothing is forwarded.
    """

    def __init__(self, certfile, keyfile):
        self._certfile = str(certfile)
        self._keyfile = str(keyfile)
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen.bind(("127.0.0.1", 0))
        self.port = self._listen.getsockname()[1]
        self._listen.listen(16)
        self._listen.settimeout(0.2)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.records = []
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(self._certfile, self._keyfile)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._listen.close()

    def clear(self):
        with self._lock:
            self.records.clear()

    def snapshot(self):
        with self._lock:
            return list(self.records)

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self._listen.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            worker = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            worker.start()

    def _read_until(self, reader, buffer, marker):
        while marker not in buffer:
            chunk = reader(4096)
            if not chunk:
                break
            buffer += chunk
        return buffer

    def _handle(self, conn):
        conn.settimeout(5)
        try:
            raw = self._read_until(conn.recv, b"", b"\r\n\r\n")
            if b"\r\n\r\n" not in raw:
                self._record(b"", raw, tls=False)
                return
            head, rest = raw.split(b"\r\n\r\n", 1)
            first = head.split(b"\r\n", 1)[0]
            if not first.startswith(b"CONNECT "):
                self._record(first, raw, tls=False)
                return
            authority = first.split()[1] if len(first.split()) > 1 else b""
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            try:
                tls = self._ctx.wrap_socket(conn, server_side=True)
            except ssl.SSLError:
                self._record(authority, b"", tls=False)
                return
            try:
                request = self._read_until(tls.recv, rest, b"\r\n\r\n")
                if b"\r\n\r\n" in request:
                    header, body = request.split(b"\r\n\r\n", 1)
                    match = re.search(br"(?i)\r\ncontent-length:\s*(\d+)\r\n", header + b"\r\n")
                    if match:
                        need = int(match.group(1))
                        while len(body) < need:
                            chunk = tls.recv(4096)
                            if not chunk:
                                break
                            body += chunk
                    request = header + b"\r\n\r\n" + body
                self._record(authority, request, tls=True)
                response_body = b'{"build_number":"1"}\n'
                response = (
                    b"HTTP/1.1 202 Accepted\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(response_body)).encode() + b"\r\n"
                    b"Connection: close\r\n\r\n" + response_body
                )
                tls.sendall(response)
            finally:
                tls.close()
                return
        except (socket.timeout, OSError, ssl.SSLError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _record(self, authority, request, tls):
        with self._lock:
            self.records.append(
                {"authority": authority, "request": request, "tls": tls}
            )


def _base_env():
    env = os.environ.copy()
    for name in PROXY_ENV_NAMES + CA_ENV_NAMES:
        env.pop(name, None)
    env["PATH"] = "/usr/bin:/bin"
    env["HOME"] = env.get("SKILL_CURL_EMPTY_HOME", env["HOME"])
    env["CURL_HOME"] = env["HOME"]
    return env


def _apply_attack(env, proxy_url, proxy_name, ca_name, ca_file, ca_dir):
    env[proxy_name] = proxy_url
    if ca_name == "SSL_CERT_DIR":
        env[ca_name] = str(ca_dir)
    else:
        env[ca_name] = str(ca_file)


def _contains(records, needle):
    raw = needle.encode()
    hits = []
    for record in records:
        blob = record["authority"] + b"\n" + record["request"]
        if raw in blob:
            hits.append(record)
    return hits


class SkillCurlProxyTokenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="skill-curl-proxy-")
        root = Path(cls._tmpdir.name)
        empty_home = root / "empty-home"
        empty_home.mkdir()
        os.environ["SKILL_CURL_EMPTY_HOME"] = str(empty_home)
        cls.ca_file, cls.ca_dir, server_pem, server_key = _make_ca(root)
        cls.proxy = RecordingProxy(server_pem, server_key)
        cls.blocks = _token_post_blocks()

    @classmethod
    def tearDownClass(cls):
        cls.proxy.close()
        cls._tmpdir.cleanup()

    def test_skills_that_post_the_token_are_covered(self):
        self.assertEqual(
            sorted(self.blocks),
            ["skills/refactor/SKILL.md", "skills/run/SKILL.md"],
        )
        for path, blocks in self.blocks.items():
            self.assertGreaterEqual(len(blocks), 1, path)

    def test_fenced_commands_do_not_send_the_token(self):
        proxy_url = f"http://127.0.0.1:{self.proxy.port}"
        for skill_path, blocks in self.blocks.items():
            for index, block in enumerate(blocks):
                for proxy_name, ca_name in ATTACK_CASES:
                    with self.subTest(skill=skill_path, block=index, proxy=proxy_name, ca=ca_name):
                        self._assert_command_keeps_token(
                            block, proxy_url, proxy_name, ca_name, skill_path
                        )

    def _assert_command_keeps_token(self, block, proxy_url, proxy_name, ca_name, skill_path):
        control_env = _base_env()
        _apply_attack(
            control_env, proxy_url, proxy_name, ca_name, self.ca_file, self.ca_dir
        )
        control_env["SHIFT_API_TOKEN"] = CONTROL_TOKEN
        self.proxy.clear()
        control = subprocess.run(
            [
                "/usr/bin/curl",
                "-sS",
                "--max-time",
                "10",
                "-d",
                f"api_token={CONTROL_TOKEN}",
                "https://laravelshift.com/api/build",
            ],
            env=control_env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        control_hits = _contains(self.proxy.snapshot(), CONTROL_TOKEN)
        self.assertTrue(
            control_hits,
            "the local proxy did not observe a direct curl POST under "
            f"{proxy_name} and {ca_name}, so this case would not prove anything\n"
            f"curl exit {control.returncode}\n{control.stderr}\n"
            f"records {self.proxy.snapshot()!r}",
        )
        for hit in control_hits:
            self.assertTrue(hit["tls"], "token arrived outside the TLS tunnel")
            self.assertTrue(
                hit["authority"].startswith(ORIGIN.encode()),
                hit["authority"],
            )

        skill_env = _base_env()
        _apply_attack(
            skill_env, proxy_url, proxy_name, ca_name, self.ca_file, self.ca_dir
        )
        skill_env["SHIFT_API_TOKEN"] = SKILL_TOKEN
        self.proxy.clear()
        skill = subprocess.run(
            ["bash", "-c", block],
            env=skill_env,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        leaked = _contains(self.proxy.snapshot(), SKILL_TOKEN)
        self.assertFalse(
            leaked,
            f"{skill_path} sent the token to the proxy via {proxy_name} and {ca_name}\n"
            f"curl exit {skill.returncode}\n{skill.stderr}\n{skill.stdout}",
        )


if __name__ == "__main__":
    unittest.main()
