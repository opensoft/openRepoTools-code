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


def test_standalone_assembly_launcher_refuses_failed_payload_fetch(tmp_path):
    """Run the complete, byte-identical launcher through all curl fallbacks.

    The transport tests above enforce protocol behavior. This public CLI case
    also gives the collector real canonical-source execution, and proves that
    a failed implementation fetch cannot run a partial payload.
    """
    assembly = ROOTS.root_of("assembly")
    if assembly is None:
        ROOTS.need("assembly", "openRepoTools canonical download fallbacks")
    source = assembly / "openRepoTools"
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    launcher = standalone / "openRepoTools"
    launcher.write_bytes(source.read_bytes())
    launcher.chmod(0o755)
    pin = assembly / "contracts" / "code-pin.yaml"
    commit = re.search(r"^commit: *['\"]?([0-9a-f]{40})", pin.read_text(),
                       re.MULTILINE).group(1)
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh").write_text("#!/bin/sh\nexit 1\n")
    (fake / "gh").chmod(0o755)
    (fake / "curl").write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
url = next(arg for arg in sys.argv[1:] if arg.startswith("https://"))
with open(os.environ["DOWNLOAD_REQUESTS"], "a") as out:
    out.write(url + "\\n")
if "/commits/" in url:
    print("a" * 40)
elif url.endswith("/contracts/code-pin.yaml"):
    sys.stdout.buffer.write(Path(os.environ["DOWNLOAD_PIN"]).read_bytes())
elif "/git/trees/" in url:
    print(json.dumps({"tree": [{"type": "commit", "path": "code",
                               "sha": os.environ["DOWNLOAD_COMMIT"]}]}))
else:
    print("#!/usr/bin/env bash")
    print('printf ran > "$DOWNLOAD_EXECUTED"')
    print("fixture refuses implementation download", file=sys.stderr)
    sys.exit(22)
""")
    (fake / "curl").chmod(0o755)
    requests = tmp_path / "requests"
    executed = tmp_path / "payload-ran"
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}",
           "TMPDIR": str(tmp_path), "OPENREPOTOOLS_REPO": "example/assembly",
           "OPENREPOTOOLS_REF": "main", "DOWNLOAD_REQUESTS": str(requests),
           "DOWNLOAD_PIN": str(pin), "DOWNLOAD_COMMIT": commit,
           "DOWNLOAD_EXECUTED": str(executed)}
    result = subprocess.run(["bash", str(launcher), "--install"], env=env,
                            cwd=standalone, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2, result.stderr
    assert "could not fetch openRepoTools" in result.stderr, result.stderr
    assert "fixture refuses implementation download" in result.stderr
    assert not executed.exists(), "a partial payload ran after curl failed"
    urls = requests.read_text().splitlines()
    assert len(urls) == 4, urls
    assert urls[0].endswith("/commits/main")
    assert urls[1].endswith("/contracts/code-pin.yaml")
    assert "/git/trees/" in urls[2]
    assert urls[3].endswith("/openRepoTools")
    assert launcher.read_bytes() == source.read_bytes()
