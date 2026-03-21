from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Arch PKGBUILD template.")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True, help="GitHub repository in owner/repo form")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()

    owner, repo = args.repository.split("/", 1)
    rendered = args.template.read_text(encoding="utf-8")
    replacements = {
        "@PKGVER@": args.version,
        "@REPO_URL@": f"https://github.com/{owner}/{repo}",
        "@SOURCE_URL@": args.source_url,
        "@SOURCE_SHA256@": args.source_sha256,
    }
    for needle, value in replacements.items():
        rendered = rendered.replace(needle, value)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
