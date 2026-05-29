"""Render a Mermaid diagram to a tightly cropped PDF via mermaid-cli + pdfcrop."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PWD = Path(__file__).parent


def find_chrome() -> str | None:
    """Locate a usable Chrome / Chromium headless binary."""
    for name in (
        "chrome-headless-shell",
        "chromium-browser",
        "chromium",
        "google-chrome-stable",
        "google-chrome",
    ):
        path = shutil.which(name)
        if path:
            return path

    # Puppeteer cache (npx puppeteer browsers install chrome-headless-shell)
    home = Path.home()
    for base in (
        home / ".cache" / "puppeteer",
        Path("/tmp"),
    ):
        for match in sorted(base.rglob("chrome-headless-shell"), reverse=True):
            if match.is_file() and os.access(match, os.X_OK):
                return str(match)

    return None


def require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        print(f"ERROR: '{tool}' not found in PATH.")
        sys.exit(1)
    return path


def render(
    mmd_path: Path,
    out_path: Path,
    margin: int = 10,
    theme: str | None = None,
    background: str | None = None,
) -> None:
    """Render .mmd → .pdf (full page) → crop to content + uniform margin."""

    mmdc = require("mmdc")
    pdfcrop = require("pdfcrop")

    chrome = os.environ.get("PUPPETEER_EXECUTABLE_PATH") or find_chrome()
    if not chrome:
        print("ERROR: No Chrome/Chromium binary found.")
        print(
            "  Install one with: npx puppeteer browsers install chrome-headless-shell"
        )
        sys.exit(1)

    env = {**os.environ, "PUPPETEER_EXECUTABLE_PATH": chrome}

    with tempfile.TemporaryDirectory() as tmp:
        raw_pdf = Path(tmp) / "raw.pdf"

        print(f"[1/2] Rendering {mmd_path.name} → PDF (via mmdc) ...")
        cmd = [mmdc, "-i", str(mmd_path), "-o", str(raw_pdf)]
        if theme:
            cmd += ["-t", theme]
        if background:
            cmd += ["-b", background]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: mmdc failed:\n{result.stderr}")
            sys.exit(1)

        print(f"[2/2] Cropping whitespace (margin={margin}pt) ...")
        result = subprocess.run(
            [pdfcrop, "--margins", str(margin), str(raw_pdf), str(out_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR: pdfcrop failed:\n{result.stderr}")
            sys.exit(1)

    print(f"  OK → {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Render a Mermaid .mmd file to a tightly cropped PDF."
    )
    parser.add_argument("input", help="Path to .mmd file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output PDF path (default: same name as input with .pdf extension)",
    )
    parser.add_argument(
        "-m",
        "--margin",
        type=int,
        default=10,
        help="Uniform margin in pt around the cropped content (default: 10)",
    )
    parser.add_argument(
        "-t",
        "--theme",
        help="Mermaid theme (e.g. default, neutral, dark, forest)",
    )
    parser.add_argument(
        "-b",
        "--background",
        help="Background color (e.g. white, transparent, '#ff0000')",
    )
    args = parser.parse_args()

    mmd_path = Path(args.input)
    if not mmd_path.exists():
        print(f"ERROR: {mmd_path} not found.")
        sys.exit(1)

    out_path = Path(args.output) if args.output else mmd_path.with_suffix(".pdf")

    render(
        mmd_path,
        out_path,
        margin=args.margin,
        theme=args.theme,
        background=args.background,
    )


if __name__ == "__main__":
    main()
