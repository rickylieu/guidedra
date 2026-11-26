"""Add a guide page and build it: python add.py <slug> <url> [--en NAME] [--jp NAME]"""
import argparse, json, re, shutil, subprocess, sys, time, webbrowser
from pathlib import Path

HOSTS = {"appmedia.jp": "appmedia", "game8.jp": "game8",
         "altema.jp": "altema", "gamewith.jp": "gamewith"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("url")
    ap.add_argument("--en")
    ap.add_argument("--jp")
    args = ap.parse_args()

    source = next((s for host, s in HOSTS.items() if host in args.url), None)
    if source is None:
        sys.exit(f"Don't know which site this is: {args.url}")

    target = Path("raw") / args.slug / f"{source}.html"
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        started = time.time()
        webbrowser.open(args.url)
        print(f"Save the page as HTML Only (Downloads is fine). Waiting for {target} ...")
        downloads = Path.home() / "Downloads"
        while not target.exists():
            new = [f for f in downloads.iterdir()
                   if f.suffix.lower() in (".html", ".htm") and f.stat().st_mtime > started]
            if new:
                time.sleep(1)
                shutil.move(max(new, key=lambda f: f.stat().st_mtime), target)
            else:
                time.sleep(1)

    manifest_path = Path("dungeons.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((d for d in manifest if d["slug"] == args.slug), None)
    if entry is None:
        html = target.read_text(encoding="utf-8", errors="ignore")
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
        jp = ""
        if title:
            jp = re.sub(r"の攻略.*", "", title.group(1).replace("【パズドラ】", ""), flags=re.S).strip()
        entry = {"slug": args.slug, "name_en": args.slug, "name_jp": jp, "sources": {}}
        manifest.append(entry)
    if args.en:
        entry["name_en"] = args.en
    if args.jp:
        entry["name_jp"] = args.jp
    entry["sources"][source] = args.url
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    subprocess.run([sys.executable, "build.py", "--debug", args.slug, source], check=True)
    subprocess.run([sys.executable, "build.py", args.slug], check=True)
    print("Built. Read report.md. Preview: http://localhost:8000 (Ctrl+C to stop)")
    subprocess.run([sys.executable, "-m", "http.server", "-d", "site", "8000"])


if __name__ == "__main__":
    main()