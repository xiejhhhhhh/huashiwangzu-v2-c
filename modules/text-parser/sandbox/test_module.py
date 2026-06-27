"""Sandbox test for text-parser module."""
import sys
from pathlib import Path
SDIR = Path(__file__).resolve().parent / "samples"
ALLOWED_ENCS = ["utf-8","utf-8-sig","gbk","gb2312","latin-1"]


def parse_text(path):
    raw = path.read_bytes()
    content = None
    for enc in ALLOWED_ENCS:
        try: content = raw.decode(enc); break
        except: continue
    if content is None: content = raw.decode("utf-8", errors="replace")
    content = content.replace("\r\n","\n").replace("\r","\n")
    lines = content.splitlines(keepends=False)
    blocks, ext = [], path.suffix.lstrip(".").lower()
    is_md = ext in ("md","markdown")

    if is_md:
        pl, in_code = [], False
        for line in lines:
            if line.startswith("```"):
                if pl:
                    t = "\n".join(pl).strip()
                    if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})
                pl = []
                in_code = not in_code
                blocks.append({"type":"段落","text":line,"page":None,"resource_ref":None})
                continue
            if in_code:
                blocks.append({"type":"段落","text":line,"page":None,"resource_ref":None})
                continue
            if line.startswith("#"):
                if pl:
                    t = "\n".join(pl).strip()
                    if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})
                pl = []
                blocks.append({"type":"标题","text":line.lstrip("#").strip(),"page":None,"resource_ref":None})
                continue
            if line.strip() == "":
                if pl:
                    t = "\n".join(pl).strip()
                    if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})
                pl = []
                continue
            pl.append(line)
        if pl:
            t = "\n".join(pl).strip()
            if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})
    else:
        pl = []
        for line in lines:
            if line.strip() == "":
                if pl:
                    t = "\n".join(pl).strip()
                    if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})
                pl = []
                continue
            pl.append(line)
        if pl:
            t = "\n".join(pl).strip()
            if t: blocks.append({"type":"段落","text":t,"page":None,"resource_ref":None})

    return {"file_id":0,"format":ext,"blocks":blocks,"resources":[]}


def validate(result, label):
    assert all(k in result for k in ("file_id","blocks","resources"))
    for b in result["blocks"]: assert all(k in b for k in ("type","text","page","resource_ref"))
    print("  [%s] Validation PASS (%d blocks)" % (label, len(result["blocks"])))


def main():
    print("="*60); print("text-parser sandbox test"); print("="*60)
    for fn in ("sample.txt","sample.md"):
        f = SDIR / fn
        if f.exists():
            result = parse_text(f)
            for b in result["blocks"]:
                print("  [%s] %s" % (b["type"], b["text"][:60]))
            validate(result, fn)
    print("PASS: text-parser sandbox test")

if __name__ == "__main__": main()
