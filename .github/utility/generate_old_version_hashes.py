import ast
import hashlib
import urllib.request

# --- Config ---
major_versions = range(2020, 2026)
minor_versions = range(0, 13)
patch_versions = range(0, 5)

unique_hashes = set()

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

def compute_hash(func_code: str) -> str:
    return hashlib.sha1(func_code.encode("utf-8")).hexdigest()

def fetch_code(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8")


for major in major_versions:
    for minor in minor_versions:
        for patch in patch_versions:
            tag = f"{major}.{minor}.{patch}"
            url = f"https://raw.githubusercontent.com/home-assistant/core/{tag}/homeassistant/components/person/__init__.py"
            try:
                code = fetch_code(url)
            except Exception:
                continue

            func_code = _get_function_source(code, "Person", "_update_state")
            if func_code:
                func_hash = compute_hash(func_code)
                if func_hash not in unique_hashes:
                    print(f"    \"{tag}+\": \"{func_hash}\",")
                    unique_hashes.add(func_hash)
