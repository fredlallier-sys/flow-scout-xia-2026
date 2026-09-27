#!/usr/bin/env python3
"""Serve the local Jury Mode and expose one guarded full-run endpoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class JuryModeServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], project: Path) -> None:
        self.project = project.resolve()
        self.run_lock = threading.Lock()
        super().__init__(address, JuryModeHandler)

    def run_agent(self) -> dict[str, object]:
        environment = os.environ.copy()
        environment.update(
            {
                "FLOW_SCOUT_NO_OPEN": "1",
                "FLOW_SCOUT_SERVE": "0",
            }
        )
        try:
            completed = subprocess.run(
                ["/bin/bash", str(self.project / "Lancer_Flow_Scout_Jury.command")],
                cwd=self.project,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": "L’exécution a dépassé cinq minutes et a été arrêtée.",
            }
        output = "\n".join(
            line.strip()
            for line in (completed.stdout + "\n" + completed.stderr).splitlines()
            if line.strip()
        )
        return {
            "ok": completed.returncode == 0,
            "message": (
                "Flow Scout a terminé : résultats et Atlas v3 ont été reconstruits."
                if completed.returncode == 0
                else "Flow Scout n’a pas terminé ses contrôles. Consulte le journal local."
            ),
            "return_code": completed.returncode,
            "output": output[-4000:],
        }


class JuryModeHandler(SimpleHTTPRequestHandler):
    server: JuryModeServer

    def __init__(
        self,
        request: object,
        client_address: tuple[str, int],
        server: JuryModeServer,
    ) -> None:
        super().__init__(
            request,
            client_address,
            server,
            directory=str(server.project / "outputs"),
        )

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - API de http.server
        if self.path in {"", "/"}:
            self.send_response(302)
            self.send_header("Location", "/jury-mode/latest/index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - API de http.server
        if self.path != "/api/run":
            self._json_response(404, {"ok": False, "message": "Route inconnue."})
            return
        if not self._same_origin_request():
            self._json_response(403, {"ok": False, "message": "Origine refusée."})
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._json_response(415, {"ok": False, "message": "JSON requis."})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 1024:
            self._json_response(413, {"ok": False, "message": "Requête trop grande."})
            return
        if length:
            self.rfile.read(length)
        if not self.server.run_lock.acquire(blocking=False):
            self._json_response(
                409, {"ok": False, "message": "Flow Scout est déjà en cours d’exécution."}
            )
            return
        try:
            result = self.server.run_agent()
        finally:
            self.server.run_lock.release()
        self._json_response(200 if result["ok"] else 500, result)

    def _same_origin_request(self) -> bool:
        origin = self.headers.get("Origin", "")
        parsed = urlparse(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port == self.server.server_port
        )

    def _json_response(self, status: int, payload: dict[str, object]) -> None:
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(project: Path, first_port: int) -> JuryModeServer:
    last_error: OSError | None = None
    for port in range(first_port, first_port + 11):
        try:
            return JuryModeServer(("127.0.0.1", port), project)
        except OSError as error:
            last_error = error
    raise OSError("Aucun port local disponible entre 8765 et 8775.") from last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    server = create_server(args.project, args.port)
    url = f"http://127.0.0.1:{server.server_port}/jury-mode/latest/index.html"
    url_file = args.project / "outputs" / "jury-mode" / "server-url.txt"
    url_file.parent.mkdir(parents=True, exist_ok=True)
    url_file.write_text(url + "\n", encoding="utf-8")
    print(f"Flow Scout est prêt : {url}", flush=True)
    print("Laisse cette fenêtre ouverte pendant la démonstration.", flush=True)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur Flow Scout arrêté.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
