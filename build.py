# -*- coding: utf-8 -*-
"""从 总览.md 与各板块目录生成项目总入口 index.html。
用法:python3 build.py（在仓库根目录运行）
内容源头 = 总览.md:「## 板块」表格定义板块清单(板块 | 目录 | 状态 | 定位),
表格之前的段落作为页首说明,之后的章节作为页尾说明。
板块的节点数、一级分区、附加页面与最近更新时间在生成时自动读取,不在 md 中重复维护:
  节点数  = 该板块 知识库/ 下所有 md 中 <!--# id --> 标记的数量
  一级分区 = 该板块 build.py 中 TREE 的顶层条目(跳过纯跳转条目)
改完 总览.md 或任一板块后重跑此脚本即可更新总入口。"""
import ast, json, re, pathlib, subprocess

BASE = pathlib.Path(__file__).parent
SRC = (BASE / "总览.md").read_text(encoding="utf-8")
STATUS_CLASS = {"进行中": "ok", "打磨中": "todo", "已完成": "done"}

m = re.search(r"^## 板块[ \t]*\n(.*?)(?=^## )", SRC, re.S | re.M)
if not m:
    raise SystemExit("总览.md 缺少「## 板块」表格")
intro_md = re.sub(r"^#\s+.*\n", "", SRC[:m.start()], count=1).strip()
tail_md = SRC[m.end():].strip()

rows = [l.strip() for l in m.group(1).splitlines() if l.strip().startswith("|")]
boards = []
for row in rows[2:]:
    cells = [c.strip() for c in row.strip("|").split("|")]
    boards.append({"name": cells[0], "dir": cells[1], "status": cells[2], "blurb": cells[3]})


def git_date(path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", path],
                             cwd=BASE, capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def stats(d):
    kb = BASE / d / "知识库"
    nodes = 0
    if kb.exists():
        for p in kb.rglob("*.md"):
            nodes += len(re.findall(r"<!--#\s*[A-Za-z0-9_]+\s*-->", p.read_text(encoding="utf-8")))
    parts = []
    bp = BASE / d / "build.py"
    if bp.exists():
        mm = re.search(r"^TREE\s*=\s*(\[.*?^\])", bp.read_text(encoding="utf-8"), re.S | re.M)
        if mm:
            try:
                parts = [n["label"] for n in ast.literal_eval(mm.group(1)) if not n.get("href")]
            except Exception:
                parts = []
    extra = sorted(p.name for p in (BASE / d).glob("*.html") if p.name != "知识地图.html")
    return nodes, parts, extra


problems = []
for b in boards:
    d = BASE / b["dir"]
    if not d.exists():
        problems.append("板块目录不存在: " + b["dir"])
        b.update(nodes=0, parts=[], extra=[], updated="", map_ok=False, log=None)
        continue
    b["nodes"], b["parts"], b["extra"] = stats(b["dir"])
    b["updated"] = git_date(b["dir"])
    b["map_ok"] = (d / "知识地图.html").exists()
    b["log"] = "项目管理/01-迭代记录.md" if (d / "项目管理/01-迭代记录.md").exists() else None
    if not b["map_ok"]:
        problems.append("缺少知识地图: " + b["dir"])
    if b["status"] not in STATUS_CLASS:
        problems.append("未知状态「%s」: %s" % (b["status"], b["name"]))


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


cards = []
for b in boards:
    chips = "".join('<span class="chip">%s</span>' % esc(p) for p in b["parts"])
    links = ['<a class="btn" href="%s/知识地图.html">打开知识地图</a>' % esc(b["dir"])] if b["map_ok"] else []
    links.append('<a class="lnk" href="%s/README.md">板块说明</a>' % esc(b["dir"]))
    if b["log"]:
        links.append('<a class="lnk" href="%s/%s">迭代记录</a>' % (esc(b["dir"]), esc(b["log"])))
    for x in b["extra"]:
        links.append('<a class="lnk" href="%s/%s">%s</a>' % (esc(b["dir"]), esc(x), esc(x.replace(".html", ""))))
    meta = ["%d 个知识节点" % b["nodes"]]
    if b["parts"]:
        meta.append("%d 个一级分区" % len(b["parts"]))
    if b["updated"]:
        meta.append("最近更新 " + b["updated"])
    cards.append(
        '<article class="card">'
        '<div class="cardhead"><h3>%s</h3><span class="pill %s">%s</span></div>'
        '<p class="blurb">%s</p>'
        '<p class="meta">%s</p>'
        '<div class="chips">%s</div>'
        '<div class="actions">%s</div>'
        '</article>' % (esc(b["name"]), STATUS_CLASS.get(b["status"], "sub"), esc(b["status"]),
                        esc(b["blurb"]), esc(" · ".join(meta)), chips, "".join(links)))

TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人知识梳理 · 总入口</title>
<style>
  :root{--bg:#f7f7f4;--panel:#fff;--ink:#23211c;--sub:#6b6860;--line:#e3e0d8;--accent:#2f74d0;--ok:#1d9e75;--todo:#b9791a;--shadow:0 1px 3px rgba(0,0,0,.06)}
  @media (prefers-color-scheme:dark){:root{--bg:#1c1b18;--panel:#26241f;--ink:#ece9e1;--sub:#a39e93;--line:#3a372f;--shadow:0 1px 3px rgba(0,0,0,.3)}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
  header{padding:14px 24px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
  header h1{margin:0;font-size:19px;font-weight:600}
  header .note{font-size:12.5px;color:var(--sub)}
  header .total{margin-left:auto;font-size:12.5px;color:var(--sub)}
  main{max-width:1080px;margin:0 auto;padding:26px 24px 60px}
  section.md h2{font-size:17px;margin:1.6em 0 .4em}
  section.md p{margin:.6em 0}
  section.md ul{margin:.4em 0;padding-left:1.4em}
  section.md li{margin:.3em 0}
  section.md code{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:.92em}
  section.md strong{font-weight:600}
  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:18px 0 8px}
  @media(max-width:820px){.grid{grid-template-columns:1fr}}
  .card{border:1px solid var(--line);border-radius:12px;background:var(--panel);box-shadow:var(--shadow);padding:16px 18px;display:flex;flex-direction:column}
  .cardhead{display:flex;align-items:center;gap:10px}
  .card h3{margin:0;font-size:16px}
  .pill{font-size:11.5px;border:1px solid var(--line);border-radius:999px;padding:2px 9px;color:var(--sub)}
  .pill.ok{color:var(--ok);border-color:var(--ok);background:rgba(29,158,117,.08)}
  .pill.todo{color:var(--todo);border-color:var(--todo);background:rgba(185,121,26,.08)}
  .blurb{margin:.6em 0 .2em;font-size:14px}
  .meta{margin:.2em 0 .6em;font-size:12.5px;color:var(--sub)}
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:14px}
  .chip{font-size:11.5px;line-height:1.3;border:1px solid var(--line);border-radius:6px;padding:3px 7px;background:var(--bg);color:var(--sub)}
  .actions{margin-top:auto;display:flex;flex-wrap:wrap;align-items:center;gap:12px}
  .btn{display:inline-flex;align-items:center;font-size:13.5px;font-weight:600;text-decoration:none;color:#fff;background:var(--accent);border-radius:8px;padding:7px 14px}
  .lnk{font-size:12.5px;color:var(--sub);text-decoration:none;border-bottom:1px dotted var(--line)}
  .lnk:hover,.btn:hover{opacity:.88}
  footer{border-top:1px solid var(--line);margin-top:30px;padding-top:14px;font-size:12.5px;color:var(--sub);display:flex;flex-wrap:wrap;gap:14px}
  footer a{color:var(--sub)}
</style>
</head>
<body>
<header>
  <h1>个人知识梳理</h1>
  <span class="note">personal_knowledge_manager</span>
  <span class="total">__TOTAL__</span>
</header>
<main>
  <section class="md" id="intro"></section>
  <div class="grid">__CARDS__</div>
  <section class="md" id="tail"></section>
  <footer>
    <a href="项目管理/02-迭代记录.md">项目迭代记录</a>
    <a href="项目管理/01-项目维护指南.md">维护指南</a>
    <a href="工具轨backlog.md">工具轨 backlog</a>
    <a href="README.md">README</a>
  </footer>
</main>
<script type="text/markdown" id="intro-src">__INTRO__</script>
<script type="text/markdown" id="tail-src">__TAIL__</script>
<script>
function inline(t){return t
  .replace(/`([^`]+)`/g,'<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2">$1</a>');}
function md(src){
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const out=[];let list=false,para=[];
  const fp=()=>{if(para.length){out.push('<p>'+inline(esc(para.join(' ')))+'</p>');para=[]}};
  const cl=()=>{if(list){out.push('</ul>');list=false}};
  src.replace(/\r/g,'').split('\n').forEach(function(line){
    const t=line.trim();let m;
    if(t===''){fp();cl();return;}
    if(m=t.match(/^(#{2,4})\s+(.*)/)){fp();cl();out.push('<h'+m[1].length+'>'+inline(esc(m[2]))+'</h'+m[1].length+'>');return;}
    if(m=t.match(/^[-*]\s+(.*)/)){fp();if(!list){out.push('<ul>');list=true}out.push('<li>'+inline(esc(m[1]))+'</li>');return;}
    para.push(t);
  });
  fp();cl();
  return out.join('\n');
}
document.getElementById('intro').innerHTML=md(document.getElementById('intro-src').textContent);
document.getElementById('tail').innerHTML=md(document.getElementById('tail-src').textContent);
</script>
</body>
</html>
"""

total = "%d 个板块 · %d 个知识节点" % (len(boards), sum(b["nodes"] for b in boards))
html = (TEMPLATE.replace("__TOTAL__", esc(total))
        .replace("__CARDS__", "".join(cards))
        .replace("__INTRO__", intro_md.replace("</script>", "<\\/script>"))
        .replace("__TAIL__", tail_md.replace("</script>", "<\\/script>")))
(BASE / "index.html").write_text(html, encoding="utf-8")
print("生成 index.html ✓")
for b in boards:
    print("  %-10s %2d 节点 · %d 分区 · %s" % (b["name"], b["nodes"], len(b["parts"]), b["updated"] or "未提交"))
if problems:
    print("提示:")
    for p in problems:
        print("  -", p)
