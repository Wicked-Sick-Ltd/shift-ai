#!/usr/bin/env python3
"""Run the Shift API curl commands from the skills and reject config redirection.

The run and refactor skills tell the agent to post the Shift API token with
curl. Curl reads CURL_HOME/.curlrc unless -q is its first argument, and it
follows proxy environment variables unless the command disables them. These
tests execute those commands inside a network namespace whose only interface
is loopback. They fail while a curlrc or a proxy still receives the token.
"""

from __future__ import annotations

import fcntl
import os
import pathlib
import re
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading

TOKEN = "PLACEHOLDER_SHIFT_API_TOKEN"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = {
    "run": ("skills/run/SKILL.md", "/api/run"),
    "refactor": ("skills/refactor/SKILL.md", "/api/build"),
}
BASH_FENCE = re.compile(r"^[ \t]*```bash\n(.*?)^[ \t]*```", re.M | re.S)


def fail(message: str) -> None:
    raise AssertionError(message)


def skill_command(relative_path: str, endpoint: str) -> str:
    text = (REPO_ROOT / relative_path).read_text()
    commands = []
    for block in BASH_FENCE.findall(text):
        command = textwrap.dedent(block).strip()
        if command.startswith("curl ") and "api_token" in command:
            commands.append(command)
    if len(commands) != 1:
        fail(f"{relative_path} must contain one curl command that posts api_token, found {len(commands)}")
    command = commands[0]
    urls = re.findall(r"https?://[^\s\"']+", command)
    expected = f"https://laravelshift.com{endpoint}"
    if urls != [expected]:
        fail(f"{relative_path} must post only to {expected}, found {urls}")
    return command


def bring_up_loopback() -> None:
    iff_up = 0x1
    siocgifflags = 0x8913
    siocsifflags = 0x8914
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        current = fcntl.ioctl(sock, siocgifflags, struct.pack("16sH14s", b"lo", 0, b"\0" * 14))
        _name, flags, _rest = struct.unpack("16sH14s", current)
        fcntl.ioctl(
            sock,
            siocsifflags,
            struct.pack("16sH14s", b"lo", flags | iff_up, b"\0" * 14),
        )
    finally:
        sock.close()
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    probe.listen(1)
    port = probe.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    client.close()
    probe.close()


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TlsSink:
    """Local TLS peer that records one HTTP request body."""

    def __init__(self) -> None:
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="shift-curl-tls-"))
        subprocess.check_call(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(self.directory / "key.pem"),
                "-out",
                str(self.directory / "cert.pem"),
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.port = free_port()
        self.body = b""
        self.saw_request = False
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=5):
            fail("TLS sink did not start")

    def _serve(self) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.directory / "cert.pem", self.directory / "key.pem")
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", self.port))
        server.listen(1)
        server.settimeout(8)
        self._started.set()
        try:
            connection, _address = server.accept()
        except socket.timeout:
            server.close()
            return
        try:
            tls = context.wrap_socket(connection, server_side=True)
            tls.settimeout(3)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                data += chunk
            header, _, rest = data.partition(b"\r\n\r\n")
            length = 0
            for line in header.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":", 1)[1].strip())
            while len(rest) < length:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                rest += chunk
            self.body = rest
            self.saw_request = True
            payload = b'{"ok":true}'
            tls.sendall(
                b"HTTP/1.1 202 Accepted\r\nContent-Length: "
                + str(len(payload)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + payload
            )
            tls.close()
        except Exception:
            self.saw_request = False
        finally:
            server.close()

    def close(self) -> None:
        self._thread.join(timeout=2)


class TcpSink:
    def __init__(self) -> None:
        self.port = free_port()
        self.accepted = False
        self.plaintext = b""
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=5):
            fail("TCP sink did not start")

    def _serve(self) -> None:
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", self.port))
        server.listen(1)
        server.settimeout(8)
        self._started.set()
        try:
            connection, _address = server.accept()
        except socket.timeout:
            server.close()
            return
        self.accepted = True
        connection.settimeout(2)
        try:
            while len(self.plaintext) < 65536:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                self.plaintext += chunk
        except socket.timeout:
            pass
        connection.close()
        server.close()

    def close(self) -> None:
        self._thread.join(timeout=2)


def base_env(work: pathlib.Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in list(environment):
        if "proxy" in name.lower() or name in {"CURL_HOME", "XDG_CONFIG_HOME"}:
            environment.pop(name)
    empty_home = work / "empty-home"
    empty_config = work / "empty-xdg"
    empty_home.mkdir()
    empty_config.mkdir()
    environment["HOME"] = str(empty_home)
    environment["XDG_CONFIG_HOME"] = str(empty_config)
    environment["SHIFT_API_TOKEN"] = TOKEN
    environment["ARGUMENTS"] = "CI"
    return environment


def run_command(command: str, environment: dict[str, str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-x", "-c", command],
        env=environment,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


def curl_trace_contains_token(stderr: str) -> bool:
    for line in stderr.splitlines():
        traced = line.strip()
        if traced.startswith("+") and " curl " in f" {traced} " or traced.startswith("+ curl "):
            if TOKEN in traced:
                return True
    return False


def assert_not_redirected(skill: str, command: str) -> None:
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"shift-{skill}-"))
    curl_home = work / "curl-home"
    curl_home.mkdir()
    sink = TlsSink()
    try:
        (curl_home / ".curlrc").write_text(
            "insecure\n"
            f'connect-to = "laravelshift.com:443:127.0.0.1:{sink.port}"\n'
        )
        environment = base_env(work)
        # A committed settings env value is a relative directory, which curl
        # resolves from the working directory. No shell expands it first.
        environment["CURL_HOME"] = "curl-home"
        completed = run_command(command, environment, work)
    finally:
        sink.close()
    problems = []
    if TOKEN.encode() in sink.body or (sink.saw_request and b"api_token=" in sink.body):
        problems.append(
            f"{skill}: CURL_HOME/.curlrc received the api_token field while the URL still named laravelshift.com"
        )
    if curl_trace_contains_token(completed.stderr):
        problems.append(f"{skill}: the curl command line contains the token after shell expansion")
    if problems:
        fail("\n".join(problems))


def assert_proxy_not_used(skill: str, command: str, variable: str) -> None:
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"shift-{skill}-proxy-"))
    sink = TcpSink()
    try:
        environment = base_env(work)
        environment[variable] = f"http://127.0.0.1:{sink.port}"
        run_command(command, environment, work)
    finally:
        sink.close()
    if sink.accepted or TOKEN.encode() in sink.plaintext:
        fail(f"{skill}: {variable} received the curl transfer")


def check_skill(skill: str, relative_path: str, endpoint: str) -> None:
    command = skill_command(relative_path, endpoint)
    errors: list[str] = []
    for check in (
        lambda: assert_not_redirected(skill, command),
        lambda: assert_proxy_not_used(skill, command, "https_proxy"),
        lambda: assert_proxy_not_used(skill, command, "ALL_PROXY"),
    ):
        try:
            check()
        except AssertionError as error:
            errors.append(str(error))
    if errors:
        fail("\n".join(errors))


def main() -> int:
    if os.environ.get("SHIFT_CURL_TEST_INSIDE_NETNS") != "1":
        os.environ["SHIFT_CURL_TEST_INSIDE_NETNS"] = "1"
        os.execvp("unshare", ["unshare", "-Urn", "--", sys.executable, *sys.argv])
    bring_up_loopback()
    failures: list[str] = []
    for skill, (relative_path, endpoint) in SKILLS.items():
        try:
            check_skill(skill, relative_path, endpoint)
        except AssertionError as error:
            failures.append(str(error))
        except subprocess.TimeoutExpired:
            failures.append(f"{skill}: curl did not finish inside the network namespace")
    if failures:
        for message in failures:
            print(message, file=sys.stderr)
        return 1
    print("shift api token was not redirected by curl config or proxy env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
