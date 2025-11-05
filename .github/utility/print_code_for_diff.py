import ast
import hashlib
import json
import urllib.request
import re


API_URL_RELEASE = "https://api.github.com/repos/home-assistant/core/releases/latest"


def _get_latest_release_tag():
    """Ritorna il tag della release stabile più recente."""
    with urllib.request.urlopen(API_URL_RELEASE) as resp:
        data = json.load(resp)
    return data["tag_name"]

#tag = "2025.10.3"
tag = _get_latest_release_tag()
url = f"https://raw.githubusercontent.com/home-assistant/core/{tag}/homeassistant/components/person/__init__.py"


def _get_function_source(code: str, class_name: str, func_name: str) -> str:
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


def _patch_update_state(func_code: str) -> str:
    """Aggiunge la variabile extra e il piccolo elif in modo robusto."""
    lines = func_code.splitlines()

    variable_added = False
    elif_state_added = False
    elif_zone_added = False
    add_coordinates = False
    elif_zone_coordinates = False

    # Check se le modifiche esistono già
    for line in lines:
        if "latest_non_gps_zone" in line:
            variable_added = True
        if "elif state.state not in (STATE_HOME, STATE_NOT_HOME):" in line:
            elif_state_added = True
        if "elif latest_non_gps_zone:" in line:
            elif_zone_added = True
        if "latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None" in line:
            elif_zone_coordinates = True
        if "coordinates =" in line:
            add_coordinates = True

    if variable_added and elif_state_added and elif_zone_added and elif_zone_coordinates:
        return func_code  # Patch già presente, nulla da fare

    new_lines = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        new_lines.append(line)

        # Inseriamo la nuova variabile subito dopo la dichiarazioni delle variabili note
        if not variable_added and "latest_non_gps_home" in line and "latest_not_home" in line and "latest_gps" in line:
            indent = re.match(r"(\s*)", line).group(1)
            new_lines.append(f"{indent}latest_non_gps_zone = None")
            variable_added = True

        # Inseriamo il piccolo elif subito dopo la riga di latest_non_gps_home
        if not elif_state_added and "latest_non_gps_home = _get_latest(latest_non_gps_home, state)" in line:
            # Prendiamo indentazione della riga originale
            orig_indent = re.match(r"(\s*)", line).group(1)
            # L'elif deve avere un livello in meno rispetto a line
            elif_indent = orig_indent[:-4] if len(orig_indent) >= 4 else ""
            new_lines.append(f"{elif_indent}elif state.state not in (STATE_HOME, STATE_NOT_HOME):")
            # La riga con la nuova variabile va indentata dentro l'elif
            new_lines.append(f"{elif_indent}    latest_non_gps_zone = _get_latest(latest_non_gps_zone, state)")
            elif_state_added = True

        #Inseriamo l'altro blocco elif subito prima della riga elif latest_gps:
        if not elif_zone_added and "elif latest_gps:" in line:
            # Trova indentazione coerente con il blocco if/elif
            indent = re.match(r"(\s*)", line).group(1)
            # Aggiungiamo subito prima il nostro blocco
            insert_pos = len(new_lines) - 1
            new_lines.insert(insert_pos, f"{indent}elif latest_non_gps_zone:")
            new_lines.insert(insert_pos + 1, f"{indent}    latest = latest_non_gps_zone")
            if add_coordinates:
                new_lines.insert(insert_pos + 2, f"{indent}    if (")
                new_lines.insert(insert_pos + 3, f"{indent}        latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None")
                new_lines.insert(insert_pos + 4, f"{indent}        and latest_non_gps_zone.attributes.get(ATTR_LONGITUDE) is None")
                new_lines.insert(
                    insert_pos + 5,
                    indent + '        and (zone := self.hass.states.get(f"zone.{latest_non_gps_zone.state.lower().replace(\' \', \'_\')}"))'
                )
                new_lines.insert(insert_pos + 6, f"{indent}    ):")
                new_lines.insert(insert_pos + 7, f"{indent}        coordinates = zone")
                new_lines.insert(insert_pos + 8, f"{indent}    else:")
                new_lines.insert(insert_pos + 9, f"{indent}        coordinates = latest_non_gps_zone")
            elif_zone_added = True
            elif_zone_coordinates = True

        #Se invece l'ultimo blocco elif esiste ma non ha il check sulle coordinate
        elif elif_zone_added and add_coordinates and not elif_zone_coordinates and "latest = latest_non_gps_zone" in line:
            indent = re.match(r"(\s*)", line).group(1)
            # Controlla se la prossima riga è quella da sostituire
            if i + 1 < len(lines) and "coordinates = latest_non_gps_zone" in lines[i + 1]:
                # Inserisci il blocco completo invece della riga semplice
                new_lines.append(f"{indent}if (")
                new_lines.append(f"{indent}    latest_non_gps_zone.attributes.get(ATTR_LATITUDE) is None")
                new_lines.append(f"{indent}    and latest_non_gps_zone.attributes.get(ATTR_LONGITUDE) is None")
                new_lines.append(indent + f'    and (zone := self.hass.states.get(f"zone.{latest_non_gps_zone.state.lower().replace(" ", "_")}"))')
                new_lines.append(f"{indent}):")
                new_lines.append(f"{indent}    coordinates = zone")
                new_lines.append(f"{indent}else:")
                new_lines.append(f"{indent}    coordinates = latest_non_gps_zone")
                elif_zone_coordinates = True
                skip_next = True


    # Controlli di coerenza finale
    if not variable_added:
        raise RuntimeError("Patch Person: variabile 'latest_non_gps_zone' non aggiunta — struttura inattesa.")
    if not elif_state_added:
        raise RuntimeError("Patch Person: blocco 'elif state.state not in (...)' non aggiunto — struttura inattesa.")
    if not elif_zone_added or not elif_zone_coordinates:
        raise RuntimeError("Patch Person: blocco 'elif latest_non_gps_zone' non aggiunto/modificato — struttura inattesa.")

    return "\n".join(new_lines)


def _compute_hash(func_code: str) -> str:
    return hashlib.sha1(func_code.encode("utf-8")).hexdigest()


print("Scarico file:", url)
with urllib.request.urlopen(url) as resp:
    code = resp.read().decode("utf-8")

func_code = _get_function_source(code, "Person", "_update_state")

print("\n--- CODICE ORIGINALE ESTRATTO ---")
print(func_code)
print("-----------------------\n")

patched_code = _patch_update_state(func_code)

print("\n--- CODICE CON PATCH DINAMICA ---")
print(patched_code)
print("-----------------------\n")

func_hash = _compute_hash(func_code)
print("NUOVO HASH DEL CODICE ORIGINALE:\n")
print(f"    \"{tag}+\": \"{func_hash}\",")

with open(".github/utility/original_code.txt", "w", encoding="utf-8") as f:
    f.write(func_code)

with open(".github/utility/patched_code.txt", "w", encoding="utf-8") as f:
    f.write(patched_code)

with open(".github/utility/hash.txt", "w", encoding="utf-8") as f:
    f.write(f'    "{tag}+": "{func_hash}",\n')
