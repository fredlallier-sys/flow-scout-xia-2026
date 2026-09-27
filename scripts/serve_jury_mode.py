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

    def run_codex_local(self, *, confirmed_subscription_usage: bool) -> dict[str, object]:
        if not confirmed_subscription_usage:
            return {
                "ok": False,
                "message": "Confirmation de l'usage du compte Codex local requise.",
            }
        source = self.project / "docs" / "references" / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
        receipt = self.project / "outputs" / "winner-demo" / "codex-local-receipt.json"
        project_python = self.project / "backend" / ".venv" / "bin" / "python"
        python = str(project_python) if project_python.is_file() else "python3"
        try:
            completed = subprocess.run(
                [
                    python,
                    "-m",
                    "app.flow_scout",
                    "codex-local-review",
                    str(source),
                    "--output",
                    str(receipt),
                    "--project-root",
                    str(self.project),
                    "--confirm-subscription-usage",
                ],
                cwd=self.project / "backend",
                env={**os.environ, "PYTHONPATH": "."},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=360,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": "Codex local a depasse six minutes."}
        return self._codex_result(
            completed,
            receipt,
            success_message="Codex local a relu le paquet sous le contrat Flow Scout.",
            failure_message="Codex local a ete refuse ou son resultat n'a pas passe le contrat.",
        )

    def run_codex_api(self, *, confirmed_existing_credits: bool) -> dict[str, object]:
        if not confirmed_existing_credits:
            return {
                "ok": False,
                "message": "Confirmation des credits OpenAI API existants requise.",
            }
        source = self.project / "docs" / "references" / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
        receipt = self.project / "outputs" / "winner-demo" / "codex-harness-receipt.json"
        project_python = self.project / "backend" / ".venv" / "bin" / "python"
        python = str(project_python) if project_python.is_file() else "python3"
        environment = os.environ.copy()
        try:
            completed = subprocess.run(
                [
                    python,
                    "-m",
                    "app.flow_scout",
                    "codex-review",
                    str(source),
                    "--output",
                    str(receipt),
                    "--confirm-existing-credits",
                ],
                cwd=self.project / "backend",
                env={**environment, "PYTHONPATH": "."},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": "Codex a depasse cinq minutes."}
        return self._codex_result(
            completed,
            receipt,
            success_message="Codex API a relu le paquet sous le contrat Flow Scout.",
            failure_message="L'appel Codex API a ete refuse ou son resultat est invalide.",
        )

    @staticmethod
    def _codex_result(
        completed: subprocess.CompletedProcess[str],
        receipt: Path,
        *,
        success_message: str,
        failure_message: str,
    ) -> dict[str, object]:
        output = "\n".join(
            line.strip()
            for line in (completed.stdout + "\n" + completed.stderr).splitlines()
            if line.strip()
        )
        result: dict[str, object] = {
            "ok": completed.returncode == 0,
            "message": success_message if completed.returncode == 0 else failure_message,
            "return_code": completed.returncode,
            "output": output[-4000:],
        }
        if completed.returncode == 0 and receipt.is_file():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            result["receipt"] = {
                "provider": saved.get("provider"),
                "runtime": saved.get("runtime"),
                "model": saved.get("model"),
                "session_id": saved.get("session_id"),
                "usage": saved.get("usage"),
            }
        return result


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

    def do_GET(self) -> None:
        if self.path in {"", "/"}:
            self.send_response(302)
            self.send_header("Location", "/jury-mode/latest/index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path not in {"/api/run", "/api/run/codex", "/api/run/codex-api"}:
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
        request: dict[str, object] = {}
        if length:
            try:
                request = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json_response(400, {"ok": False, "message": "JSON invalide."})
                return
            if not isinstance(request, dict):
                self._json_response(400, {"ok": False, "message": "Objet JSON requis."})
                return
        if not self.server.run_lock.acquire(blocking=False):
            self._json_response(
                409, {"ok": False, "message": "Flow Scout est déjà en cours d’exécution."}
            )
            return
        try:
            if self.path == "/api/run/codex":
                result = self.server.run_codex_local(
                    confirmed_subscription_usage=request.get("confirmed_subscription_usage")
                    is True
                )
            elif self.path == "/api/run/codex-api":
                result = self.server.run_codex_api(
                    confirmed_existing_credits=request.get("confirmed_existing_credits") is True
                )
            else:
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
