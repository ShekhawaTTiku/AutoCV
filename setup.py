"""
AutoCV Setup Script
Automates:
  1. Installing Python dependencies (requirements.txt)
  2. Initializing .env configuration from .env.example
  3. Downloading the portable Tectonic LaTeX compiler into tools/ (if no compiler is installed)
"""

import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"
FALLBACK_TECTONIC_VERSION = "0.17.0"


def print_step(num: int, total: int, title: str):
    print(f"\n[{num}/{total}] {title}")


def install_requirements():
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        print("  Warning: requirements.txt not found. Skipping.")
        return
    print("  Installing Python packages from requirements.txt...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("  Warning: pip install encountered errors. You may need to retry manually.")
    else:
        print("  Dependencies installed successfully.")


def setup_env_file():
    env_file = ROOT / ".env"
    example_file = ROOT / ".env.example"

    if env_file.exists():
        print("  .env file already exists. (Skipping copy)")
        return

    if example_file.exists():
        shutil.copy(example_file, env_file)
        print("  Created .env from .env.example template.")
    else:
        # Create minimal .env template if .env.example was missing
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("GROQ_API_KEY=\nGEMINI_API_KEY=\nMISTRAL_API_KEY=\n")
        print("  Created new .env file.")
    print("  --> IMPORTANT: Open .env and add your API keys before running the app!")


def find_existing_compiler() -> str:
    # 1. Check tools/ directory
    local_binary = TOOLS_DIR / ("tectonic.exe" if os.name == "nt" else "tectonic")
    if local_binary.exists():
        return f"Local Tectonic binary ({local_binary})"

    # 2. Check system PATH
    for name in ("tectonic", "pdflatex", "xelatex"):
        found = shutil.which(name)
        if found:
            return f"System {name} on PATH ({found})"

    return ""


def get_tectonic_asset_info():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        pattern = "x86_64-pc-windows-msvc.zip"
        binary_name = "tectonic.exe"
    elif system == "darwin":
        binary_name = "tectonic"
        if "arm" in machine or "aarch64" in machine:
            pattern = "aarch64-apple-darwin.tar.gz"
        else:
            pattern = "x86_64-apple-darwin.tar.gz"
    elif system == "linux":
        binary_name = "tectonic"
        if "aarch64" in machine or "arm64" in machine:
            pattern = "aarch64-unknown-linux-musl.tar.gz"
        else:
            pattern = "x86_64-unknown-linux-musl.tar.gz"
    else:
        return None, None, None

    # Fetch latest release assets from GitHub API
    api_url = "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"
    download_url = None
    tag_name = None

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "AutoCV-Setup"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag_name = data.get("tag_name", f"tectonic@{FALLBACK_TECTONIC_VERSION}")
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if pattern in name:
                    download_url = asset.get("browser_download_url")
                    break
    except Exception:
        # Fallback to direct release URL if GitHub API rate-limits
        tag_name = f"tectonic@{FALLBACK_TECTONIC_VERSION}"
        filename = f"tectonic-{FALLBACK_TECTONIC_VERSION}-{pattern}"
        download_url = f"https://github.com/tectonic-typesetting/tectonic/releases/download/{tag_name}/{filename}"

    if not download_url:
        tag_name = f"tectonic@{FALLBACK_TECTONIC_VERSION}"
        filename = f"tectonic-{FALLBACK_TECTONIC_VERSION}-{pattern}"
        download_url = f"https://github.com/tectonic-typesetting/tectonic/releases/download/{tag_name}/{filename}"

    return download_url, binary_name, pattern


def download_and_extract_tectonic():
    download_url, binary_name, pattern = get_tectonic_asset_info()
    if not download_url:
        print("  Could not determine platform download for Tectonic.")
        print("  Please install tectonic manually (e.g. winget install tectonic or brew install tectonic).")
        return False

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = TOOLS_DIR / binary_name

    print(f"  Downloading portable Tectonic ({binary_name})...")
    print(f"  Source: {download_url}")

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "AutoCV-Setup"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()

        print("  Extracting executable...")
        if pattern.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.namelist():
                    if member.endswith(binary_name):
                        with zf.open(member) as source, open(target_path, "wb") as dest:
                            dest.write(source.read())
                        break
        elif pattern.endswith(".tar.gz"):
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith(binary_name) and member.isfile():
                        extracted = tf.extractfile(member)
                        if extracted:
                            with open(target_path, "wb") as dest:
                                dest.write(extracted.read())
                        break

        if target_path.exists():
            # Grant execute permission on Unix
            if os.name != "nt":
                os.chmod(target_path, 0o755)

            # Test invocation
            ver = subprocess.run([str(target_path), "--version"], capture_output=True, text=True)
            output = ver.stdout.strip() or ver.stderr.strip()
            print(f"  Installed {output} to {target_path}")
            return True
        else:
            print("  Extraction failed: binary not found in archive.")
            return False

    except Exception as exc:
        print(f"  Download/extraction failed: {exc}")
        print("  You can install tectonic manually: 'winget install tectonic' or 'brew install tectonic'.")
        return False


def setup_compiler():
    existing = find_existing_compiler()
    if existing:
        print(f"  Found existing compiler: {existing}")
        return

    print("  No LaTeX compiler detected on this machine.")
    download_and_extract_tectonic()


def main():
    print("=" * 60)
    print("           AutoCV Automatic Environment Setup")
    print("=" * 60)

    print_step(1, 3, "Installing Python Dependencies")
    install_requirements()

    print_step(2, 3, "Setting Up Configuration (.env)")
    setup_env_file()

    print_step(3, 3, "Checking LaTeX Compiler")
    setup_compiler()

    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("\nNext Steps:")
    print("  1. Add your API keys to the '.env' file:")
    print("     - GEMINI_API_KEY")
    print("     - GROQ_API_KEY")
    print("     - MISTRAL_API_KEY")
    print("\n  2. Start the application:")
    print("     streamlit run app.py\n")


if __name__ == "__main__":
    main()
