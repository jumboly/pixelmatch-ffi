"""GitHub Releases に添付した wheel から PEP 503 (Simple Repository API) の静的インデックスを生成する。

GitHub Pages に置くと、uv / pip が `--index-url` / `[[tool.uv.index]]` として利用できる。
wheel 本体は Releases に置いたまま、インデックスからはその URL を参照する。

使い方 (GitHub Actions 内): python scripts/gen_simple_index.py <出力ディレクトリ>
  環境変数 GITHUB_REPOSITORY と GH_TOKEN を使い、gh CLI で全リリースの asset を列挙する。
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = "pixelmatch-ffi"


def release_assets(repo: str) -> list[dict]:
    out = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/releases", "--jq", ".[] | select(.draft | not) | .assets[]"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main() -> int:
    out_dir = Path(sys.argv[1])
    repo = os.environ["GITHUB_REPOSITORY"]

    links = []
    for a in sorted(release_assets(repo), key=lambda a: a["name"]):
        if not a["name"].endswith(".whl"):
            continue
        url = a["browser_download_url"]
        # GitHub が asset に付与する sha256 をハッシュフラグメントにし、uv/pip に改ざん検知させる
        digest = a.get("digest") or ""
        if digest.startswith("sha256:"):
            url += "#sha256=" + digest.removeprefix("sha256:")
        links.append(f'    <a href="{html.escape(url)}">{html.escape(a["name"])}</a><br/>')

    pkg_dir = out_dir / "simple" / PROJECT
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "simple" / "index.html").write_text(
        f'<!DOCTYPE html>\n<html><body>\n    <a href="{PROJECT}/">{PROJECT}</a>\n</body></html>\n'
    )
    (pkg_dir / "index.html").write_text(
        "<!DOCTYPE html>\n<html><body>\n" + "\n".join(links) + "\n</body></html>\n"
    )
    # Jekyll がアンダースコア始まりのファイル等を除外しないよう無効化
    (out_dir / ".nojekyll").touch()
    print(f"{len(links)} wheels indexed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
