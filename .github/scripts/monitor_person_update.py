import ast
import hashlib
import json
import sys
import urllib.request
import os


REFERENCE_HASHES = {
    "_update_state": "03003c1662579b5895e9741177ab7aebf2631179", #2025.9.0+
    "_parse_source_state": "82112bc96ed78526273c9873913947e60ef8a9b0", #2025.9.0+
}


API_URL_RELEASE = "https://api.github.com/repos/home-assistant/core/releases/latest"
TARGET_REPO = "5a2v0/HA-WiFi-Sensor-Tracker"


def _get_latest_release_tag():
    """Ritorna il tag della release stabile più recente."""
    with urllib.request.urlopen(API_URL_RELEASE) as resp:
        data = json.load(resp)
    return data["tag_name"]


def _get_function_source(code: str, class_name: str, func_name: str) -> str:
    """Estrae il sorgente completo di una funzione, incluso decoratore e riga vuota finale."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for func in node.body:
                if isinstance(func, ast.FunctionDef) and func.name == func_name:
                    lines = code.splitlines()
                    start = func.lineno - 1
                    # Includi eventuali decoratori sopra
                    while start > 0 and lines[start - 1].strip().startswith("@"):
                        start -= 1
                    end = func.end_lineno
                    # Aggiungi riga vuota dopo, se presente
                    if end < len(lines) and lines[end].strip() == "":
                        end += 1
                    return "\n".join(lines[start:end])
    return ""


def _get_existing_issues(token: str):
    """Restituisce la lista delle issue aperte nel repo target."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{TARGET_REPO}/issues?state=open",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "wifi-sensor-tracker-monitor",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def _issue_already_exists(issues, tag, func_name):
    """Controlla se esiste già una issue aperta per quella funzione e release."""
    for issue in issues:
        if f"{func_name} modificata in {tag}" in issue["title"]:
            return True
    return False


def _create_github_issue(token: str, tag: str, func_name: str, new_hash: str):
    """Crea una issue automatica nel repo corrente se l'hash differisce."""
    issues = _get_existing_issues(token)
    if _issue_already_exists(issues, tag, func_name):
        print(f"Esiste già una issue aperta per {func_name} ({tag}), nessuna nuova creata.")
        return

    issue_title = f"[AutoCheck] Person.{func_name} modificata in {tag}"
    issue_body = (
        f"La funzione `Person.{func_name}` nel core di Home Assistant è cambiata nella release **{tag}**.\n\n"
        f"Nuovo hash: `{new_hash}`\n\n"
        f"File monitorato:\n"
        f"https://github.com/home-assistant/core/blob/{tag}/homeassistant/components/person/__init__.py\n\n"
        f"Aggiorna la patch nel modulo `person_patch.py` per mantenere compatibilità."
    )

    data = json.dumps({"title": issue_title, "body": issue_body}).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.github.com/repos/{TARGET_REPO}/issues",
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "wifi-sensor-tracker-monitor",
        },
    )

    with urllib.request.urlopen(req) as resp:
        if resp.status in (200, 201):
            print(f"Issue per {func_name} creata con successo.")
        else:
            print(f"Creazione issue fallita per {func_name} (status {resp.status}).")


def main():
    tag = _get_latest_release_tag()
    print(f"Ultima release stabile: {tag}")

    raw_url = (
        f"https://raw.githubusercontent.com/home-assistant/core/{tag}/"
        "homeassistant/components/person/__init__.py"
    )

    with urllib.request.urlopen(raw_url) as resp:
        code = resp.read().decode("utf-8")

    token = os.environ.get("GH_TOKEN")
    issues_to_create = []

    for func_name, known_hash in REFERENCE_HASHES.items():
        func_code = _get_function_source(code, "Person", func_name)
        if not func_code:
            print(f"Errore: funzione {func_name} non trovata.")
            continue

        func_hash = hashlib.sha1(func_code.encode("utf-8")).hexdigest()
        print(f"{func_name} → hash corrente: {func_hash}")

        if func_hash != known_hash:
            print(f"Attenzione: {func_name} con hash modificato!")
            issues_to_create.append((func_name, func_hash))
        else:
            print(f">Info: {func_name} nessuna modifica rilevata.")

    # Se ci sono modifiche, crea le issue
    if issues_to_create:
        if not token:
            print("Nessun GH_TOKEN trovato. Issue non create.")
            sys.exit(2)
        for func_name, func_hash in issues_to_create:
            _create_github_issue(token, tag, func_name, func_hash)
    else:
        print("Tutte le funzioni monitorate sono invariate.")


if __name__ == "__main__":
    main()
