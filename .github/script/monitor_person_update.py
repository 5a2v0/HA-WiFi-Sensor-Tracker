import ast
import hashlib
import json
import sys
import urllib.request
import os

REFERENCE_HASH = "6eb5b353829ab6ec0d256f1ad8d0c4d3e003a0c7"
API_URL_RELEASE = "https://api.github.com/repos/home-assistant/core/releases/latest"
TARGET_REPO = "5a2v0/HA-WiFi-Sensor-Tracker"


def get_latest_release_tag():
    """Ritorna il tag della release stabile più recente."""
    with urllib.request.urlopen(API_URL_RELEASE) as resp:
        data = json.load(resp)
    return data["tag_name"]


def get_function_source(code: str, class_name: str, func_name: str) -> str:
    """Estrae il sorgente esatto di una funzione da una classe usando AST."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for func in node.body:
                if isinstance(func, ast.FunctionDef) and func.name == func_name:
                    lines = code.splitlines()
                    return "\n".join(lines[func.lineno - 1 : func.end_lineno])
    return ""


def get_existing_issues(token: str):
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


def issue_already_exists(issues, tag):
    """Controlla se esiste già una issue aperta per quella release."""
    for issue in issues:
        if f"Person._update_state modificata in {tag}" in issue["title"]:
            return True
    return False


def create_github_issue(token: str, tag: str, new_hash: str):
    """Crea una issue automatica nel repo corrente se l'hash differisce."""
    issues = get_existing_issues(token)
    if issue_already_exists(issues, tag):
        print(f"Esiste già una issue aperta per {tag}, nessuna nuova creata.")
        return

    issue_title = f"[AutoCheck] Person._update_state modificata in {tag}"
    issue_body = (
        f"La funzione `Person._update_state` nel core di Home Assistant è cambiata nella release **{tag}**.\n\n"
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
            print("Issue creata con successo.")
        else:
            print(f"Creazione issue fallita (status {resp.status}).")


def main():
    tag = get_latest_release_tag()
    print(f"Ultima release stabile: {tag}")

    raw_url = (
        f"https://raw.githubusercontent.com/home-assistant/core/{tag}/"
        "homeassistant/components/person/__init__.py"
    )

    with urllib.request.urlopen(raw_url) as resp:
        code = resp.read().decode("utf-8")

    func_code = get_function_source(code, "Person", "_update_state")
    if not func_code:
        print("Errore: funzione non trovata.")
        sys.exit(1)

    func_hash = hashlib.sha1(func_code.encode("utf-8")).hexdigest()
    print("Hash corrente:", func_hash)

    if func_hash != REFERENCE_HASH:
        print("Attenzione: hash modificato! Creazione issue...")
        token = os.environ.get("GH_TOKEN")
        if not token:
            print("❌ Nessun GH_TOKEN trovato. Issue non creata.")
            sys.exit(2)
        create_github_issue(token, tag, func_hash)
        sys.exit(3)
    else:
        print("Nessuna modifica rilevata. Tutto OK.")


if __name__ == "__main__":
    main()
