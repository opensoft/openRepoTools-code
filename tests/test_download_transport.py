# SPDX-License-Identifier: Apache-2.0
"""Exercise the curl arguments of every implementation/assembly download.

The shell functions run with refusing gh/curl stubs to capture their actual
expanded arguments. Real curl then uses those arguments against ephemeral
loopback HTTPS/HTTP servers. No GitHub request or downloaded code is executed.
"""
import http.server
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import threading

import pytest

from conftest import ROOTS


@pytest.fixture(scope="module")
def transport_servers(tmp_path_factory):
    work = tmp_path_factory.mktemp("download-transport")
    cert, key = work / "cert.pem", work / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
    ], check=True, capture_output=True)
    plain_requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.server is plain:
                plain_requests.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{plain.server_port}/unsafe")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Length", "7")
                self.end_headers()
                self.wfile.write(b"payload")

        def log_message(self, *args):
            pass

    plain = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    secure = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    secure.socket = context.wrap_socket(secure.socket, server_side=True)
    threads = [threading.Thread(target=s.serve_forever, daemon=True)
               for s in (plain, secure)]
    for thread in threads:
        thread.start()
    try:
        yield cert, secure.server_port, plain.server_port, plain_requests
    finally:
        for server in (secure, plain):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


CASES = [
    ("code", "fetch_from_repo", ["payload", "destination"]),
    ("code", "api_sha", ["main"]),
    ("code", "api_tree", ["main", "destination"]),
    ("code", "probe_path", ["payload", "destination"]),
    ("code", "wip_fetch_template_file", ["payload", "destination", "main"]),
    ("assembly", "fetch_at", ["example/repo", "main", "payload", "destination"]),
    ("assembly", "gitlink_at", ["main", "code"]),
    ("assembly", "delegate_remote", []),
]


@pytest.mark.parametrize("role,name,arguments", CASES,
                         ids=[f"{role}-{name}" for role, name, _ in CASES])
def test_download_refuses_insecure_redirect_and_initial_http(
        role, name, arguments, tmp_path, transport_servers):
    source_root = ROOTS.root_of(role)
    if source_root is None:
        ROOTS.need(role, "openRepoTools download transport")
    source = (source_root / "openRepoTools").read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\).*?^}}", source, re.MULTILINE | re.DOTALL)
    assert match, name
    capture = tmp_path / "curl-arguments"
    script = r"""
gh() { return 1; }
jq() { return 1; }
api_said() { printf unavailable; }
said() { printf unavailable; }
is_slug() { return 0; }
is_lower_hex() { return 0; }
die() { exit 2; }
curl() { printf '%s\0' "$@" >"$CAPTURE"; return 22; }
""" + match.group() + f'\n{name} "$@"\n'
    env = {**os.environ, "CAPTURE": str(capture), "TMPDIR": str(tmp_path),
           "WORKDIR": str(tmp_path), "TMP": str(tmp_path),
           "REPO": "example/repo", "REF": "main", "PAYLOAD_REPO": "",
           "PAYLOAD_REV": "", "SHAPE_REPOSITORY": "example/shape",
           "SELF": str(tmp_path / "absent"), "WIP_TEMPLATE_DIR": "template"}
    subprocess.run(["bash", "-c", script, name, *arguments], env=env,
                   cwd=tmp_path, capture_output=True, timeout=10)
    captured = capture.read_bytes().split(b"\0")
    args = [os.fsdecode(arg) for arg in captured if arg]
    urls = [index for index, arg in enumerate(args) if arg.startswith("https://")]
    assert len(urls) == 1, args
    cert, secure_port, plain_port, plain_requests = transport_servers

    def request(url):
        actual = list(args)
        actual[urls[0]] = url
        return subprocess.run([
            shutil.which("curl"), "-q", "--noproxy", "*", "--cacert", str(cert),
            "--connect-timeout", "2", "--max-time", "5", *actual,
        ], cwd=tmp_path, capture_output=True, timeout=10)

    good = request(f"https://localhost:{secure_port}/ok")
    assert good.returncode == 0, good.stderr
    before = len(plain_requests)
    redirect = request(f"https://localhost:{secure_port}/redirect")
    assert redirect.returncode != 0, "HTTPS download followed an HTTP redirect"
    assert len(plain_requests) == before, "insecure redirect reached the HTTP server"
    initial = request(f"http://localhost:{plain_port}/unsafe")
    assert initial.returncode != 0, "download accepted an initial HTTP URL"
    assert len(plain_requests) == before, "initial HTTP reached the server"
