import ast
import hashlib
import urllib.request
import re

def get_function_source(code: str, class_name: str, func_name: str) -> str:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for func in node.body:
                if isinstance(func, ast.FunctionDef) and func.name == func_name:
                    lines = code.splitlines()
                    start = func.lineno - 1
                    while start > 0 and lines[start - 1].strip().startswith("@"):
                        start -= 1
                    end = func.end_lineno
                    if end < len(lines) and lines[end].strip() == "":
                        end += 1
                    return "\n".join(lines[start:end])
    return ""

def add_patch_modifications(func_code: str) -> str:
    """Aggiunge la variabile extra e il piccolo elif in modo robusto."""
    lines = func_code.splitlines()
    new_lines = []

    # Check se la variabile esiste già
    if any("latest_non_gps_zone" in line for line in lines):
        return func_code  # Patch già presente, nulla da fare
    
    variable_added = False

    add_coordinates = any("coordinates =" in line for line in lines)

    for i, line in enumerate(lines):
        new_lines.append(line)

        # Inseriamo la nuova variabile subito dopo una variabile già esistente
        if not variable_added and "latest_non_gps_home" in line:
            indent = re.match(r"(\s*)", line).group(1)
            new_lines.append(f"{indent}latest_non_gps_zone = None")
            variable_added = True

        # Inseriamo il piccolo elif subito dopo la riga di latest_non_gps_home
        if "latest_non_gps_home = _get_latest(latest_non_gps_home, state)" in line:
            # Prendiamo indentazione della riga originale
            orig_indent = re.match(r"(\s*)", line).group(1)
            # L'elif deve avere un livello in meno rispetto a line
            elif_indent = orig_indent[:-4] if len(orig_indent) >= 4 else ""
            new_lines.append(f"{elif_indent}elif state.state not in (STATE_HOME, STATE_NOT_HOME):")
            # La riga con la nuova variabile va indentata dentro l'elif
            new_lines.append(f"{elif_indent}    latest_non_gps_zone = _get_latest(latest_non_gps_zone, state)")

        #Inseriamo l'altro blocco elif subito prima della riga elif latest_gps:
        if "elif latest_gps:" in line:
            # Trova indentazione coerente con il blocco if/elif
            indent = re.match(r"(\s*)", line).group(1)
            # Aggiungiamo subito prima il nostro blocco
            insert_pos = len(new_lines) - 1
            new_lines.insert(insert_pos, f"{indent}elif latest_non_gps_zone:")
            new_lines.insert(insert_pos + 1, f"{indent}    latest = latest_non_gps_zone")
            if add_coordinates:
                new_lines.insert(insert_pos + 2, f"{indent}    coordinates = latest_non_gps_zone")

    return "\n".join(new_lines)


def compute_hash(func_code: str) -> str:
    return hashlib.sha1(func_code.encode("utf-8")).hexdigest()
    
# --- Config ---
tag = "2025.10.3"
url = f"https://raw.githubusercontent.com/home-assistant/core/{tag}/homeassistant/components/person/__init__.py"

print("Scarico file:", url)
with urllib.request.urlopen(url) as resp:
    code = resp.read().decode("utf-8")

func_code = get_function_source(code, "Person", "_update_state")

print("\n--- CODICE ORIGINALE ESTRATTO ---")
print(func_code)
print("-----------------------\n")

patched_code = add_patch_modifications(func_code)

print("\n--- CODICE CON PATCH DINAMICA ---")
print(patched_code)
print("-----------------------\n")

func_hash = compute_hash(func_code)
print("NUOVO HASH DEL CODICE ORIGINALE:\n")
print(f"    \"{tag}+\": \"{func_hash}\",")

with open(".github/utility/original_code.txt", "w", encoding="utf-8") as f:
    f.write(func_code)

with open(".github/utility/patched_code.txt", "w", encoding="utf-8") as f:
    f.write(patched_code)

with open(".github/utility/hash.txt", "w", encoding="utf-8") as f:
    f.write(f'    "{tag}+": "{func_hash}",\n')
