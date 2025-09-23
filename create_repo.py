# create_repo.py
# Usage:
#   1) Place this script in the SAME folder as the unzipped files I provided.
#   2) (Optional) Set the remote:
#        - Edit REMOTE_URL below, OR
#        - set env var GITHUB_REMOTE to your repo URL (e.g., https://github.com/YourOrg/scholarone-report-generator.git)
#   3) (Optional) Set PUSH=1 in your environment if you want the script to push the initial commit.
#   4) Run:  python create_repo.py
#
# Result:
#   C:\Users\casher\OneDrive - Informs\2025\Projects\S1 API App- Codex\scholarone-report-generator
#   with files copied, .env written, and a git repo initialized + initial commit.
#
# Notes:
# - If REMOTE_URL is set, the script will add 'origin'. If PUSH=1, it will push 'main'.
# - If a repo already exists at the target path, files will be updated and re-committed.

import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ====== CONFIG ======
TARGET_ROOT = r"C:\Users\casher\OneDrive - Informs\2025\Projects\S1 API App- Codex"
REPO_NAME   = "scholarone-report-generator"   # use your GitHub repo's name
DEFAULT_BRANCH = "main"

# Option A: hardcode your GitHub remote here (HTTPS or SSH)
REMOTE_URL = ""  # e.g., "https://github.com/YourOrg/scholarone-report-generator.git"
# Option B: or export GITHUB_REMOTE in your env and leave REMOTE_URL="" above
REMOTE_URL = os.getenv("GITHUB_REMOTE", REMOTE_URL)

# If you want to auto-push the initial commit to origin/main, set env PUSH=1
AUTO_PUSH = os.getenv("PUSH", "0") == "1"

ALLOWED_SITES = [
    "deca", "isr", "inte", "ijoc", "ijds", "ijoo", "ite", "ms", "msom",
    "mksc", "mathor", "opre", "serv", "stratsci", "ssy", "orgsci", "transci",
    "msomconference"
]

# ====== SOURCE LAYOUT (relative to this script's directory) ======
FILES = [
    (".gitignore", ".gitignore"),
    ("LICENSE", "LICENSE"),
    ("requirements.txt", "requirements.txt"),
    (".env.example", ".env.example"),
    ("README.md", "README.md"),
    ("Dockerfile", "Dockerfile"),
    ("Makefile", "Makefile"),
    ("docs/scholarone-api-complete-documentation.md", "docs/scholarone-api-complete-documentation.md"),
    ("src/app/__init__.py", "src/app/__init__.py"),
    ("src/app/main.py", "src/app/main.py"),
    ("src/core/__init__.py", "src/core/__init__.py"),
    ("src/core/constants.py", "src/core/constants.py"),
    ("src/s1_client/__init__.py", "src/s1_client/__init__.py"),
    ("src/s1_client/client.py", "src/s1_client/client.py"),
    ("tests/__init__.py", "tests/__init__.py"),
    ("tests/test_smoke.py", "tests/test_smoke.py"),
]

FOLDERS = ["docs", "src/app", "src/core", "src/s1_client", "tests"]

def run(cmd, cwd=None, check=True):
    """Run a shell command with nice errors."""
    print(f"[cmd] {cmd} (cwd={cwd})")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
            raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result

def ensure_repo_root():
    repo_root = Path(TARGET_ROOT) / REPO_NAME
    repo_root.mkdir(parents=True, exist_ok=True)
    return repo_root

def copy_files(src_dir: Path, repo_root: Path):
    # Ensure folders
    for rel in FOLDERS:
        (repo_root / rel).mkdir(parents=True, exist_ok=True)

    # Copy files
    for dest_rel, src_rel in FILES:
        src = src_dir / src_rel
        dest = repo_root / dest_rel
        if not src.exists():
            print(f"[WARN] Missing source file: {src}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"[OK] Copied {src_rel} -> {dest}")

def maybe_update_readme_title(repo_root: Path):
    readme = repo_root / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    if lines and lines[0].startswith("#"):
        lines[0] = "# Scholarone Report Generator (FastAPI)"
        text = "\n".join(lines)
        readme.write_text(text, encoding="utf-8")
        print("[OK] Updated README title")

def write_env_file(repo_root: Path):
    """Auto-create .env using environment if present; else safe placeholders."""
    env_path = repo_root / ".env"
    if env_path.exists():
        print("[i] .env already exists; leaving as-is.")
        return

    s1_user = os.getenv("S1_USERNAME", "replace_me")
    s1_key  = os.getenv("S1_API_KEY", "replace_me")
    s1_site = os.getenv("S1_SITE_NAME", "orgsci")
    if s1_site not in ALLOWED_SITES:
        s1_site = "orgsci"

    content = (
        "S1_BASE_URL=https://mc-api.manuscriptcentral.com\\n"
        f"S1_USERNAME={s1_user}\\n"
        f"S1_API_KEY={s1_key}\\n"
        f"S1_SITE_NAME={s1_site}\\n"
        "\\n# Allowed sites (for reference):\\n"
        f"# {', '.join(ALLOWED_SITES)}\\n"
    )
    env_path.write_text(content, encoding="utf-8")
    print(f"[OK] Wrote {env_path}")

def git_init_and_commit(repo_root: Path):
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        run(f'git -c init.defaultBranch=main init', cwd=str(repo_root))

    # Ensure .gitignore exists before add
    if not (repo_root / ".gitignore").exists():
        (repo_root / ".gitignore").write_text("__pycache__/\\n.venv/\\n.env\\n", encoding="utf-8")

    run("git add .", cwd=str(repo_root))
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run(f'git commit -m "chore: initial scaffold ({ts})"', cwd=str(repo_root))
    except RuntimeError as e:
        if "nothing to commit" in str(e).lower():
            print("[i] Nothing new to commit.")
        else:
            raise

    try:
        run("git branch -M main", cwd=str(repo_root))
    except RuntimeError:
        pass

def git_set_remote_and_push(repo_root: Path):
    if not REMOTE_URL:
        print("[i] REMOTE_URL not set. Skipping remote add/push.")
        return
    try:
        run(f'git remote add origin "{REMOTE_URL}"', cwd=str(repo_root))
    except RuntimeError as e:
        if "remote origin already exists" in str(e).lower():
            run(f'git remote set-url origin "{REMOTE_URL}"', cwd=str(repo_root))
        else:
            raise
    if AUTO_PUSH:
        run("git push -u origin main", cwd=str(repo_root), check=False)

def main():
    src_dir = Path(__file__).parent
    repo_root = ensure_repo_root()
    copy_files(src_dir, repo_root)
    maybe_update_readme_title(repo_root)
    write_env_file(repo_root)
    git_init_and_commit(repo_root)
    git_set_remote_and_push(repo_root)

    print(f"\\nDone. Repository ready at: {repo_root}")
    print("\\nNext steps (if you skipped remote/push):")
    print(rf'  cd "{repo_root}"')
    print(r'  git remote add origin "https://github.com/<you-or-org>/scholarone-report-generator.git"')
    print(r"  git push -u origin main")
    print("\\nRun locally:")
    print(r"  python -m venv .venv && . .venv\\Scripts\\activate && pip install -r requirements.txt")
    print(r"  uvicorn src.app.main:app --reload")

if __name__ == "__main__":
    main()
