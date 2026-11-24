"""GitHub Pages に置くサイト一式を GitHub Releases の情報から生成する。

- index.html: トップページ（概要・インストール方法・リリースごとのダウンロード一覧）
- simple/: PEP 503 (Simple Repository API) の静的インデックス。uv / pip が
  `--index` / `[[tool.uv.index]]` として利用する

配布物本体は Releases に置いたまま、どちらのページからもその URL を参照する。
リリースのたびに全リリースから作り直すため、手で編集する必要はない。

使い方 (GitHub Actions 内): python scripts/gen_pages.py <出力ディレクトリ>
  環境変数 GITHUB_REPOSITORY と GH_TOKEN を使い、gh CLI で Releases と Pages の情報を取得する。
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = "pixelmatch-ffi"
UPSTREAM = "https://github.com/mapbox/pixelmatch-cpp"

# 公開後に見つかった不具合。リリース自体は消さずに残し、ここで利用者に知らせる
KNOWN_ISSUES = {
    "v0.1.0": "nupkg はネイティブライブラリの配置に不具合があり、実行時に読み込めません。"
    ".NET では v0.1.1 以降を使ってください（wheel は問題ありません）。",
}

# wheel のプラットフォームタグ → 表示名
PLATFORMS = [
    ("manylinux_2_28_x86_64", "Linux x64", "glibc 2.28+"),
    ("manylinux_2_28_aarch64", "Linux arm64", "glibc 2.28+"),
    ("win_amd64", "Windows x64", ""),
    ("win_arm64", "Windows arm64", ""),
]


def gh_json(*args: str) -> object:
    out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def releases(repo: str) -> list[dict]:
    # --paginate だと配列が連結されず複数の JSON になるため、--slurp で 1 つの配列にまとめる
    pages = gh_json("--paginate", "--slurp", f"repos/{repo}/releases")
    items = [r for page in pages for r in page if not r["draft"]]
    return sorted(items, key=lambda r: r["published_at"], reverse=True)


def site_url(repo: str) -> str:
    try:
        url = gh_json(f"repos/{repo}/pages")["html_url"]
    except subprocess.CalledProcessError:
        owner, name = repo.split("/")
        url = f"https://{owner}.github.io/{name}/"
    # 独自ドメインでは http の URL が返るが、HTTPS でも配信されているため利用者には HTTPS を案内する
    return re.sub(r"^http://", "https://", url).rstrip("/") + "/"


def hashed_url(asset: dict) -> str:
    # GitHub が asset に付与する sha256 をハッシュフラグメントにし、uv/pip に改ざん検知させる
    url = asset["browser_download_url"]
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        url += "#sha256=" + digest.removeprefix("sha256:")
    return url


def write_simple_index(out_dir: Path, rels: list[dict]) -> int:
    wheels = sorted((a for r in rels for a in r["assets"] if a["name"].endswith(".whl")), key=lambda a: a["name"])
    links = [f'    <a href="{html.escape(hashed_url(a))}">{html.escape(a["name"])}</a><br/>' for a in wheels]
    pkg_dir = out_dir / "simple" / PROJECT
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "simple" / "index.html").write_text(
        f'<!DOCTYPE html>\n<html><body>\n    <a href="{PROJECT}/">{PROJECT}</a>\n</body></html>\n',
        encoding="utf-8",
    )
    (pkg_dir / "index.html").write_text(
        "<!DOCTYPE html>\n<html><body>\n" + "\n".join(links) + "\n</body></html>\n",
        encoding="utf-8",
    )
    return len(links)


def e(s: str) -> str:
    return html.escape(s, quote=True)


def size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def code_block(text: str) -> str:
    return (
        '<div class="code"><button class="copy" type="button" aria-label="コピー">コピー</button>'
        f"<pre><code>{e(text)}</code></pre></div>"
    )


def release_section(r: dict, latest: bool) -> str:
    tag = r["tag_name"]
    date = r["published_at"][:10]
    wheels = {a["name"]: a for a in r["assets"] if a["name"].endswith(".whl")}
    nupkgs = sorted((a for a in r["assets"] if a["name"].endswith(".nupkg")), key=lambda a: a["name"])

    rows = []
    for tag_suffix, label, note in PLATFORMS:
        a = next((w for n, w in wheels.items() if n.endswith(f"-{tag_suffix}.whl")), None)
        if a is None:
            continue
        rows.append(
            f'<tr><td class="plat">{e(label)}{f" <span class=muted>{e(note)}</span>" if note else ""}</td>'
            f'<td class="file"><a href="{e(a["browser_download_url"])}">{e(a["name"])}</a></td>'
            f'<td class="num">{size(a["size"])}</td></tr>'
        )
    for a in nupkgs:
        rows.append(
            f'<tr><td class="plat">.NET <span class=muted>{e(a["name"].removesuffix(".nupkg").rsplit(".", 3)[0])}</span></td>'
            f'<td class="file"><a href="{e(a["browser_download_url"])}">{e(a["name"])}</a></td>'
            f'<td class="num">{size(a["size"])}</td></tr>'
        )

    issue = KNOWN_ISSUES.get(tag)
    badge = '<span class="badge">最新</span>' if latest else ""
    return f"""
    <details class="release"{" open" if latest else ""}>
      <summary><span class="tag">{e(tag)}</span>{badge}<span class="muted">{date}</span></summary>
      {f'<p class="issue">{e(issue)}</p>' if issue else ""}
      <div class="table-wrap"><table>
        <thead><tr><th>対象</th><th>ファイル</th><th class="num">サイズ</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table></div>
      <p><a href="{e(r["html_url"])}">GitHub のリリースページ</a></p>
    </details>"""


def write_top_page(out_dir: Path, repo: str, base: str, rels: list[dict]) -> None:
    repo_url = f"https://github.com/{repo}"
    index_url = f"{base}simple"
    stable = [r for r in rels if not r["prerelease"]]
    latest = stable[0]["tag_name"] if stable else (rels[0]["tag_name"] if rels else None)
    version = latest.removeprefix("v") if latest else "0.0.0"

    py_install = (
        f"uv add pixelmatch-ffi --index {index_url}\n"
        f"# pip の場合\n"
        f"pip install pixelmatch-ffi --extra-index-url {index_url}"
    )
    py_usage = (
        "from PIL import Image\n"
        "from pixelmatch_ffi.pil import compare   # pixelmatch-ffi[pillow]\n\n"
        'r = compare(Image.open("a.png"), Image.open("b.png"), diff=True, threshold=0.1)\n'
        'print(r.mismatch)\nr.diff.save("diff.png")'
    )
    net_install = (
        f"gh release download {latest} -R {repo} -p '*.nupkg' -D packages\n"
        f"dotnet nuget add source ./packages -n pixelmatch-ffi\n"
        f"dotnet add package PixelmatchFfi --version {version}\n"
        f"dotnet add package PixelmatchFfi.SkiaSharp --version {version}   # 任意"
    )
    net_usage = (
        "using PixelmatchFfi;\nusing PixelmatchFfi.SkiaSharp;\n\n"
        "using var r = SkiaPixelmatch.Compare(bmp1, bmp2,\n"
        "    new PixelmatchOptions { Threshold = 0.1 }, createDiff: true);\n"
        "Console.WriteLine(r.Mismatch);   // r.Diff は SKBitmap"
    )
    releases_html = "".join(release_section(r, r["tag_name"] == latest) for r in rels) or "<p>まだリリースはありません。</p>"

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pixelmatch-ffi</title>
<meta name="description" content="mapbox/pixelmatch のピクセル単位の画像比較を Python と .NET から使うためのネイティブライブラリ">
<style>
  :root {{
    --bg: #fbfbfa; --fg: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0;
    --card: #ffffff; --code-bg: #f3f3f1; --accent: #c2185b; --accent-soft: #fce4ec;
    --warn-bg: #fff4e5; --warn-fg: #8a4b00;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #141416; --fg: #ececee; --muted: #9a9aa2; --line: #2c2c31;
      --card: #1b1b1f; --code-bg: #222227; --accent: #f06292; --accent-soft: #3a1d29;
      --warn-bg: #3a2a12; --warn-fg: #ffcf8a;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font: 16px/1.7 system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
  }}
  main {{ max-width: 860px; margin: 0 auto; padding: 48px 16px 64px; }}
  header h1 {{ font-size: 2.2rem; margin: 0 0 4px; letter-spacing: -0.02em; }}
  header h1 .dot {{ color: var(--accent); }}
  .lead {{ font-size: 1.1rem; color: var(--muted); margin: 0 0 20px; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; padding: 0; list-style: none; }}
  .chips li {{ border: 1px solid var(--line); border-radius: 999px; padding: 2px 12px; font-size: .85rem; color: var(--muted); }}
  .links a {{ margin-right: 16px; }}
  h2 {{ font-size: 1.35rem; margin: 48px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }}
  h3 {{ font-size: 1.05rem; margin: 24px 0 8px; }}
  a {{ color: var(--accent); text-underline-offset: 2px; }}
  .muted {{ color: var(--muted); font-size: .9em; }}
  /* 1fr の最小幅は中身（長いコード行）になり狭い画面で横にはみ出すため、minmax(0, 1fr) で縮められるようにする */
  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
  @media (max-width: 720px) {{ .grid {{ grid-template-columns: minmax(0, 1fr); }} }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 4px 18px 18px; min-width: 0; }}
  .code {{ position: relative; }}
  pre {{
    /* 上部の余白はコピーボタン用。ボタンがコードの 1 行目に重ならないようにする */
    margin: 0; background: var(--code-bg); border-radius: 8px; padding: 34px 14px 12px; overflow-x: auto;
    font: 13px/1.6 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  .copy {{
    position: absolute; top: 6px; right: 6px; font: 12px system-ui, sans-serif; cursor: pointer;
    border: 1px solid var(--line); background: var(--card); color: var(--muted); border-radius: 6px; padding: 2px 8px;
  }}
  .copy:hover {{ color: var(--fg); }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .92rem; margin: 8px 0; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  td a {{ word-break: break-all; }}
  th {{ font-weight: 600; color: var(--muted); font-size: .85rem; }}
  .num {{ text-align: right; white-space: nowrap; }}
  /* 狭い画面では 3 列だとファイル名が数文字ずつ折り返されるため、「対象・サイズ」と「ファイル名」の 2 段にする */
  @media (max-width: 600px) {{
    thead {{ display: none; }}
    tbody tr {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; border-bottom: 1px solid var(--line); padding: 6px 0; }}
    tbody td {{ border: 0; padding: 2px 8px; }}
    td.plat {{ grid-column: 1; grid-row: 1; }}
    td.num {{ grid-column: 2; grid-row: 1; }}
    td.file {{ grid-column: 1 / -1; font-size: .85rem; }}
  }}
  .release {{ border: 1px solid var(--line); border-radius: 10px; background: var(--card); margin: 12px 0; padding: 6px 16px; }}
  .release summary {{ cursor: pointer; display: flex; gap: 12px; align-items: baseline; padding: 6px 0; }}
  .tag {{ font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .badge {{ background: var(--accent-soft); color: var(--accent); border-radius: 999px; padding: 0 10px; font-size: .8rem; font-weight: 600; }}
  .issue {{ background: var(--warn-bg); color: var(--warn-fg); border-radius: 8px; padding: 8px 12px; font-size: .92rem; }}
  footer {{ margin-top: 56px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: .88rem; }}
</style>
</head>
<body>
<main>
  <header>
    <h1>pixelmatch<span class="dot">-</span>ffi</h1>
    <p class="lead">
      <a href="{e(UPSTREAM)}">mapbox/pixelmatch</a>（C++ 版）のピクセル単位の画像比較を、
      Python と .NET から使うためのネイティブライブラリ。JS 版 pixelmatch 8.x と同じ差分数・同じ diff 画像を返します。
    </p>
    <ul class="chips">
      <li>Linux x64 / arm64</li><li>Windows x64 / arm64</li><li>Python 3.11+</li><li>.NET 8+</li><li>ISC License</li>
    </ul>
    <p class="links"><a href="{e(repo_url)}">GitHub</a><a href="{e(repo_url)}/releases">Releases</a><a href="simple/">パッケージインデックス</a></p>
  </header>

  <h2>Python</h2>
  <div class="grid">
    <section class="card">
      <h3>インストール</h3>
      {code_block(py_install)}
      <p class="muted">Pillow / numpy アダプターは extras（<code>[pillow]</code> / <code>[numpy]</code>）で入ります。</p>
    </section>
    <section class="card">
      <h3>使い方</h3>
      {code_block(py_usage)}
    </section>
  </div>

  <h2>.NET</h2>
  <div class="grid">
    <section class="card">
      <h3>インストール</h3>
      {code_block(net_install)}
      <p class="muted">SkiaSharp 版を Linux で使う場合は <code>SkiaSharp.NativeAssets.Linux</code> も追加してください。System.Drawing 版（Windows 専用）は <code>PixelmatchFfi.SystemDrawing</code>。</p>
    </section>
    <section class="card">
      <h3>使い方</h3>
      {code_block(net_usage)}
    </section>
  </div>

  <h2>ダウンロード</h2>
  {releases_html}

  <footer>
    ISC License · © 2026 jumboly · 同梱する pixelmatch-cpp は © Mapbox（ISC）。
    第三者ライセンスは各パッケージ内の THIRD-PARTY-NOTICES.txt を参照してください。
  </footer>
</main>
<script>
  // コマンドをそのまま貼り付けられるよう、各コードブロックにコピー機能を付ける
  document.querySelectorAll(".copy").forEach((btn) => {{
    btn.addEventListener("click", async () => {{
      const text = btn.nextElementSibling.innerText;
      try {{
        await navigator.clipboard.writeText(text);
        btn.textContent = "コピーしました";
      }} catch {{
        btn.textContent = "コピーできません";
      }}
      setTimeout(() => (btn.textContent = "コピー"), 1500);
    }});
  }});
</script>
</body>
</html>
"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    out_dir = Path(sys.argv[1])
    repo = os.environ["GITHUB_REPOSITORY"]
    out_dir.mkdir(parents=True, exist_ok=True)

    rels = releases(repo)
    n = write_simple_index(out_dir, rels)
    write_top_page(out_dir, repo, site_url(repo), rels)
    # Jekyll がアンダースコア始まりのファイル等を除外しないよう無効化
    (out_dir / ".nojekyll").touch()
    print(f"{len(rels)} releases, {n} wheels indexed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
