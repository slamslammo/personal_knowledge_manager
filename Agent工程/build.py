# -*- coding: utf-8 -*-
"""从 知识库/ 目录树生成 知识地图.html。
用法:python3 build.py
内容源头 = 知识库/ 下的所有 md(递归):每个部分一个子目录,部分节点为目录下的 00-*.md,
知识点正文发布后在同一目录新增 md;每个 md 用 <!--# 节点id --> 标记其对应的 TREE 节点。
首页知识图谱的唯一数据源 = 各部分节点中「## 知识点」表格:第 1 列为知识点名称
(已发布时写成 [名称](node:id)),最后 1 列为状态(已发布 / 编写中 / 未展开 / 读者前提)。
总览正文中单独一行 <!--atlas--> 的位置渲染图谱。
渲染器支持:标题/列表/引用/图片/链接/**加粗**/`行内代码`/代码块/GFM 表格(需含 |---| 分隔行)。
约束:公式 \\text{} 内勿放中文(tex-svg 无中文字体)。"""
import json, re, pathlib

BASE = pathlib.Path(__file__).parent
# 内容源头 = 知识库/ 递归读取所有 md;按 <!--# id --> 标记解析,文件顺序不影响内容映射
SRC = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((BASE / "知识库").rglob("*.md")))

# 一级节点 = 七个部分 + 参考资料;知识点发布后登记为对应部分的 children
PARTS = ["intro", "mechanism", "action", "information", "build", "evaluation", "applications"]
TREE = [
  {"id":"intro","label":"🧭 智能体是什么","children":[
    {"id":"agentdef","label":"智能体的定义与构成"},
    {"id":"agenttypes","label":"智能体的类型"},
    {"id":"history","label":"从符号主义到大模型驱动"},
    {"id":"llmcore","label":"大语言模型作为决策核心"},
  ]},
  {"id":"mechanism","label":"🔁 运行机制","children":[
    {"id":"stopcond","label":"停止条件设计"},
    {"id":"terminate","label":"终止判定的漏判"},
  ]},
  {"id":"action","label":"🛠️ 工具与协议","children":[
    {"id":"toolresult","label":"工具结果处理"},
  ]},
  {"id":"information","label":"🧠 上下文、记忆与检索","children":[
    {"id":"taskstate","label":"任务状态"},
  ]},
  {"id":"build","label":"🏗️ 框架与多智能体","children":[
    {"id":"responsibility","label":"模型与框架的职责边界"},
  ]},
  {"id":"evaluation","label":"📏 评估与训练","children":[
    {"id":"taskeval","label":"任务评估","children":[
      {"id":"evaldesign","label":"评估设计四要素"},
      {"id":"outputtrajectory","label":"评输出与评轨迹"},
      {"id":"regression","label":"失败集与回归"},
    ]},
  ]},
  {"id":"applications","label":"🧩 应用形态"},
  {"id":"refs","label":"📚 参考资料"},
]
STATUS = {"已发布":"published", "编写中":"writing", "未展开":"pending", "读者前提":"prereq"}

sections = {}
for m in re.finditer(r"<!--#\s*([A-Za-z0-9_]+)\s*-->\n?(.*?)(?=<!--#\s*[A-Za-z0-9_]+\s*-->|\Z)", SRC, re.S):
    sections[m.group(1)] = m.group(2).strip()


def tree_ids(nodes):
    for n in nodes:
        yield n["id"]
        yield from tree_ids(n.get("children", []))


def parse_points(body):
    """读取部分节点「## 知识点」表格,返回 [{label, node, status}]。"""
    m = re.search(r"^## 知识点[ \t]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    if not m:
        return []
    rows = [l.strip() for l in m.group(1).splitlines() if l.strip().startswith("|")]
    points = []
    for row in rows[2:]:  # 跳过表头与分隔行
        cells = [c.strip() for c in row.strip("|").split("|")]
        link = re.fullmatch(r"\[([^\]]+)\]\(node:([A-Za-z0-9_]+)\)", cells[0])
        points.append({"label": link.group(1) if link else cells[0],
                       "node": link.group(2) if link else "",
                       "status": cells[-1]})
    return points


ATLAS = [{"id": pid, "points": parse_points(sections.get(pid, ""))} for pid in PARTS]

# 一致性检查:只提示,不中断生成
ids = set(tree_ids(TREE))
problems = ["TREE 节点缺少正文: " + i for i in sorted(ids - sections.keys())]
problems += ["正文未登记到 TREE: " + i for i in sorted(sections.keys() - ids - {"root"})]
for part in ATLAS:
    if not part["points"]:
        problems.append("部分缺少知识点表格: " + part["id"])
    for p in part["points"]:
        where = part["id"] + " / " + p["label"]
        if p["status"] not in STATUS:
            problems.append("未知状态「%s」: %s" % (p["status"], where))
        if (p["status"] == "已发布") != bool(p["node"]):
            problems.append("「已发布」与 node 链接不一致: " + where)
for nid in sorted(set(re.findall(r"\]\(node:([A-Za-z0-9_]+)", SRC))):
    if nid not in sections:
        problems.append("内链指向不存在的节点: node:" + nid)

blocks = []
for nid, body in sections.items():
    safe = body.replace("</script>", "<\\/script>")
    blocks.append('<script type="text/markdown" data-node="%s">\n%s\n</script>' % (nid, safe))
BLOCKS = "\n".join(blocks)


def js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent 工程 知识梳理</title>
<style>
  :root{--bg:#f7f7f4;--panel:#fff;--ink:#23211c;--sub:#6b6860;--line:#e3e0d8;--accent:#2f74d0;--ok:#1d9e75;--todo:#b9791a;--shadow:0 1px 3px rgba(0,0,0,.06)}
  @media (prefers-color-scheme:dark){:root{--bg:#1c1b18;--panel:#26241f;--ink:#ece9e1;--sub:#a39e93;--line:#3a372f;--shadow:0 1px 3px rgba(0,0,0,.3)}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
  header{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
  header h1{margin:0;font-size:18px;font-weight:600}
  header .note{font-size:12.5px;color:var(--sub)}
  header .prog{margin-left:auto;font-size:12px;color:var(--sub)}
  .wrap{display:flex;align-items:stretch;min-height:calc(100vh - 50px)}
  aside{width:290px;flex:none;border-right:1px solid var(--line);padding:12px 8px;overflow:auto}
  @media(max-width:760px){.wrap{flex-direction:column}aside{width:auto;border-right:none;border-bottom:1px solid var(--line)}}
  .tnode{display:flex;align-items:center;gap:6px;padding:7px 9px;margin:3px 4px;border:1px solid transparent;border-radius:8px;cursor:pointer;font-size:14px}
  .tnode:hover{background:var(--bg)}
  .tnode.sel{background:var(--panel);border-color:var(--line);box-shadow:var(--shadow);font-weight:600}
  .tnode .cv{width:14px;color:var(--sub);font-size:11px;flex:none;transition:transform .15s}
  .tnode .cv.open{transform:rotate(90deg)}
  .tnode .lbl{flex:1}
  .tnode .chk{font-size:12px;color:var(--ok)}
  .tnode.lvl0{font-weight:600;font-size:14.5px}
  .kids{margin-left:6px;border-left:1px dashed var(--line)}
  main{flex:1;overflow:auto;padding:22px 30px;max-width:880px}
  main.wide{max-width:1180px}
  .rdrhead{display:flex;align-items:center;gap:12px;margin-bottom:4px}
  .rdrhead .markbtn{margin-left:auto;font:12.5px/1 inherit;border:1px solid var(--line);background:var(--panel);color:var(--sub);border-radius:999px;padding:6px 12px;cursor:pointer}
  .rdrhead .markbtn.done{color:var(--ok);border-color:var(--ok);background:rgba(29,158,117,.08)}
  main h1{font-size:22px;margin:.2em 0 .5em} main h2{font-size:17px;margin:1.3em 0 .4em} main h3{font-size:15px;margin:1em 0 .3em;color:var(--sub)}
  main p{margin:.5em 0} main ul,main ol{margin:.4em 0;padding-left:1.4em} main li{margin:.25em 0}
  main code{background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:.92em}
  main blockquote{margin:.6em 0;padding:.5em .9em;border-left:3px solid var(--accent);background:var(--bg);border-radius:0 8px 8px 0;color:var(--sub)}
  main hr{border:none;border-top:1px solid var(--line);margin:1.4em 0}
  main a{color:var(--accent)}
  main img{max-width:100%;display:block;margin:.8em auto;border:1px solid var(--line);border-radius:8px;background:#fff}
  main pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow:auto}
  main .tw{overflow-x:auto;margin:.8em 0}
  main table{border-collapse:collapse;width:100%;font-size:13.5px}
  main th,main td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
  main thead th{background:var(--bg);font-weight:600;white-space:nowrap}
  main th:nth-child(1),main td:nth-child(1){white-space:nowrap}
  main tbody tr:nth-child(even) td{background:rgba(127,127,127,.06)}
  .atlas{margin:1em 0 1.4em;padding:16px;border:1px solid var(--line);border-radius:10px;background:var(--panel);box-shadow:var(--shadow)}
  .atlas h2{margin:.1em 0 .25em;font-size:18px}
  .atlas .hint{margin:0 0 10px;color:var(--sub);font-size:13px}
  .flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0}
  .flow a{display:inline-flex;align-items:center;min-height:32px;padding:5px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);font-weight:600;font-size:13.5px;text-decoration:none}
  .flow .arrow{color:var(--sub)}
  .legend{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
  .atlasgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
  @media(max-width:1180px){.atlasgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
  @media(max-width:620px){.atlasgrid{grid-template-columns:1fr}}
  .atlascard{border:1px solid var(--line);border-radius:8px;background:var(--bg);padding:10px}
  .atlascard>a{display:block;font-weight:700;text-decoration:none;margin-bottom:8px;font-size:14px;line-height:1.3}
  .chips{display:flex;flex-direction:column;gap:4px}
  .chip{display:flex;align-items:baseline;justify-content:space-between;gap:8px;font-size:12px;line-height:1.35;border:1px solid var(--line);border-radius:6px;padding:4px 7px;background:var(--panel);color:var(--ink);text-decoration:none}
  .legend .chip{display:inline-flex}
  .chip .st{flex:none;font-size:11px;color:var(--sub)}
  .chip.published{border-color:var(--ok)} .chip.published .st{color:var(--ok)}
  .chip.writing{border-color:var(--accent)} .chip.writing .st{color:var(--accent)}
  .chip.pending{border-style:dashed;color:var(--sub)}
  .chip.prereq{background:transparent;border-style:dotted;color:var(--sub)}
  .todo{color:var(--todo)}
  mjx-container{overflow-x:auto;overflow-y:hidden}
</style>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},svg:{fontCache:'global'}};</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
<header>
  <h1>Agent 工程 知识梳理</h1>
  <span class="note">核心材料：Datawhale Hello-Agents</span>
  <span class="prog" id="prog"></span>
</header>
<div class="wrap">
  <aside id="tree"></aside>
  <main id="reader"></main>
</div>
__BLOCKS__
<script>
const TREE=__TREE__;
const ATLAS=__ATLAS__;
const STATUS=__STATUS__;
const PARTS=ATLAS.map(function(p){return p.id;});
const CONTENT={},LABEL={},PARENT={},HREF={};
document.querySelectorAll('script[type="text/markdown"]').forEach(s=>CONTENT[s.dataset.node]=s.textContent);
(function walk(ns,parent){ns.forEach(n=>{LABEL[n.id]=n.label;if(n.href)HREF[n.id]=n.href;if(parent)PARENT[n.id]=parent;if(n.children)walk(n.children,n.id)})})(TREE,"");
let done={};
try{done=JSON.parse(localStorage.getItem("agentkb_done")||"{}");}catch(e){}
let currentRoute={id:"root",anchor:""};
if("scrollRestoration" in history){history.scrollRestoration="manual";}
function isOverview(id){return id==="root"||id==="refs"||PARTS.indexOf(id)>=0;}
function attr(s){return String(s||"").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function routeUrl(id,anchor){
  let h="#node="+encodeURIComponent(id);
  if(anchor) h+="&anchor="+encodeURIComponent(anchor);
  return h;
}
function routeFromHash(){
  if(!location.hash) return null;
  const raw=location.hash.slice(1);
  const q=new URLSearchParams(raw);
  if(q.has("node")) return {id:q.get("node")||"root",anchor:q.get("anchor")||"",scroll:0};
  const old=decodeURIComponent(raw);
  if(CONTENT[old]||LABEL[old]) return {id:old,anchor:"",scroll:0};
  return null;
}
function getScrollY(){
  const rd=document.getElementById("reader");
  return Math.max(rd?rd.scrollTop:0,window.pageYOffset||document.documentElement.scrollTop||document.body.scrollTop||0);
}
function setScrollY(y){
  const rd=document.getElementById("reader");
  if(rd) rd.scrollTop=y||0;
  window.scrollTo(0,y||0);
}
function currentState(){return {id:currentRoute.id,anchor:currentRoute.anchor||"",scroll:getScrollY()};}
function saveCurrentState(){try{history.replaceState(currentState(),"",location.href);}catch(e){}}
let scrollTimer=null;
function rememberScroll(){clearTimeout(scrollTimer);scrollTimer=setTimeout(saveCurrentState,80);}
function inline(t){return t
  .replace(/!\[([^\]]*)\]\(([^)]+)\)/g,function(m,alt,src){return '<img src="'+src.replace(/^(?:\.\.\/)+/,'')+'" alt="'+alt+'">'})
  .replace(/`([^`]+)`/g,'<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(m,txt,url){if(url.indexOf('node:')===0){var r=url.slice(5).split('#'),nid=r[0],an=r[1]||'';return '<a href="'+attr(routeUrl(nid,an))+'" class="xref" data-node="'+attr(nid)+'" data-anchor="'+attr(an)+'">'+txt+'</a>';}var cross=/^\.\.\/(资料|深度学习|机器学习)\//.test(url);var out=/^(https?:|mailto:|#)/.test(url)?url:(cross?url:url.replace(/^(?:\.\.\/)+/,''));return '<a href="'+out+'" target="_blank" rel="noopener">'+txt+'</a>';});}
function md(src){
  src=src.replace(/\r/g,'');
  var M=[];
  src=src.replace(/\$\$([\s\S]+?)\$\$/g,function(_,x){M.push('$$'+x+'$$');return '@@M'+(M.length-1)+'@@';}).replace(/\$([^\$\n]+?)\$/g,function(_,x){M.push('$'+x+'$');return '@@M'+(M.length-1)+'@@';});
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const out=[];let list=false,olist=false,quote=false,code=false,para=[],codebuf=[];
  const fp=()=>{if(para.length){out.push('<p>'+inline(esc(para.join(' ')))+'</p>');para=[]}};
  const cl=()=>{if(list){out.push('</ul>');list=false}if(olist){out.push('</ol>');olist=false}};const cq=()=>{if(quote){out.push('</blockquote>');quote=false}};
  const fc=()=>{if(code){out.push('<pre><code>'+esc(codebuf.join('\n'))+'</code></pre>');code=false;codebuf=[]}};
  const cells=s=>s.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());
  const L=src.split('\n');
  for(let i=0;i<L.length;i++){
    const t=L[i].trim();let m;
    if(/^```/.test(t)){if(code){fc();}else{fp();cl();cq();code=true;codebuf=[];}continue;}
    if(code){codebuf.push(L[i]);continue;}
    if(/^\|.*\|$/.test(t)&&i+1<L.length&&/^\|[\s:|-]+\|$/.test(L[i+1].trim())){
      fp();cl();cq();
      var hd=cells(t),bd=[],j=i+2;
      while(j<L.length&&/^\|.*\|$/.test(L[j].trim())){bd.push(cells(L[j].trim()));j++;}
      var tb='<div class="tw"><table><thead><tr>';
      hd.forEach(c=>{tb+='<th>'+inline(esc(c))+'</th>';});tb+='</tr></thead><tbody>';
      bd.forEach(r=>{tb+='<tr>';r.forEach(c=>{tb+='<td>'+inline(esc(c))+'</td>';});tb+='</tr>';});
      out.push(tb+'</tbody></table></div>');i=j-1;continue;
    }
    if(t===''){fp();cl();cq();continue;}
    if(m=t.match(/^(#{1,4})\s+(.*)/)){fp();cl();cq();out.push('<h'+m[1].length+'>'+inline(esc(m[2]))+'</h'+m[1].length+'>');continue;}
    if(t==='---'){fp();cl();cq();out.push('<hr>');continue;}
    if(m=t.match(/^[-*]\s+(.*)/)){fp();cq();if(olist){out.push('</ol>');olist=false}if(!list){out.push('<ul>');list=true}out.push('<li>'+inline(esc(m[1]))+'</li>');continue;}
    if(m=t.match(/^\d+\.\s+(.*)/)){fp();cq();if(list){out.push('</ul>');list=false}if(!olist){out.push('<ol>');olist=true}out.push('<li>'+inline(esc(m[1]))+'</li>');continue;}
    if(m=t.match(/^>\s?(.*)/)){fp();cl();if(!quote){out.push('<blockquote>');quote=true}out.push(inline(esc(m[1]))+'<br>');continue;}
    para.push(t);
  }
  fc();
  fp();cl();cq();
  var html=out.join('\n');
  html=html.replace(/@@M(\d+)@@/g,function(_,i){return M[+i];});
  return html;
}
function typeset(cb){
  if(window.MathJax&&MathJax.typesetPromise){
    MathJax.typesetPromise([document.getElementById("reader")]).catch(function(){}).then(function(){if(cb)cb();});
  }else if(cb){cb();}
}
function tnode(n,lvl){
  const kids=n.children&&n.children.length;
  const href=n.href?' data-href="'+attr(n.href)+'"':'';
  let h='<div class="tnode lvl'+lvl+'" data-id="'+n.id+'"'+href+'><span class="cv">'+(kids?'▸':(n.href?'↗':'·'))+'</span><span class="lbl">'+n.label+'</span><span class="chk">'+(!n.href&&done[n.id]?'✓':'')+'</span></div>';
  if(kids){h+='<div class="kids" data-kids="'+n.id+'" style="display:none">'+n.children.map(c=>tnode(c,lvl+1)).join('')+'</div>';}
  return h;
}
function buildTree(){document.getElementById("tree").innerHTML=TREE.map(n=>tnode(n,0)).join('');}
function revealNode(id){
  let p=PARENT[id];
  while(p){
    const box=document.querySelector('[data-kids="'+p+'"]');
    const t=document.querySelector('.tnode[data-id="'+p+'"]');
    if(box) box.style.display="";
    if(t){const cv=t.querySelector(".cv");if(cv)cv.classList.add("open");}
    p=PARENT[p];
  }
}
function bindXrefs(){
  document.querySelectorAll("#reader a.xref").forEach(a=>{
    a.onclick=function(e){
      if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey) return;
      e.preventDefault();
      navigateNode(a.dataset.node,a.dataset.anchor||"");
    };
  });
}
function overviewHtml(){
  const flow='<div class="flow">'+PARTS.map(function(id,i){
    return (i?'<span class="arrow">→</span>':'')+'<a href="'+attr(routeUrl(id))+'" class="xref" data-node="'+attr(id)+'">'+(LABEL[id]||id)+'</a>';
  }).join('')+'</div>';
  const legend='<div class="legend">'+Object.keys(STATUS).map(function(s){return '<span class="chip '+STATUS[s]+'">'+s+'</span>';}).join('')+'</div>';
  const cards=ATLAS.map(function(part){
    const chips=part.points.map(function(p){
      const cls='chip '+(STATUS[p.status]||'pending');
      const inner='<span>'+attr(p.label)+'</span><span class="st">'+attr(p.status)+'</span>';
      return p.node?'<a class="'+cls+' xref" href="'+attr(routeUrl(p.node))+'" data-node="'+attr(p.node)+'">'+inner+'</a>':'<span class="'+cls+'">'+inner+'</span>';
    }).join('');
    return '<article class="atlascard"><a class="xref" href="'+attr(routeUrl(part.id))+'" data-node="'+attr(part.id)+'">'+(LABEL[part.id]||part.id)+'</a><div class="chips">'+chips+'</div></article>';
  }).join('');
  return '<section class="atlas"><h2>Agent 知识图谱</h2><p class="hint">七个部分按知识逻辑排列；卡片内是各部分的知识点，右侧标签表示状态。</p>'+flow+legend+'<div class="atlasgrid">'+cards+'</div></section>';
}
function scrollToAnchor(anchor,smooth){
  const rd=document.getElementById("reader");
  const hs=rd.querySelectorAll("h1,h2,h3,h4");
  for(let i=0;i<hs.length;i++){
    if(hs[i].textContent.indexOf(anchor)>=0){hs[i].scrollIntoView({behavior:smooth?"smooth":"auto",block:"start"});return true;}
  }
  return false;
}
function finishScroll(anchor,opts){
  const y=opts&&typeof opts.scroll==="number"?opts.scroll:null;
  const restore=!!(opts&&opts.restore);
  const run=function(){
    if(anchor){if(!scrollToAnchor(anchor,!restore))setScrollY(0);}
    else if(y!==null){setScrollY(y);}
    else{setScrollY(0);}
  };
  run();setTimeout(run,80);setTimeout(run,250);
}
function renderNode(id,anchor,opts){
  let body=CONTENT[id];
  if(!body) body="# "+(LABEL[id]||id)+"\n\n> 🚧 本知识点待编写。";
  currentRoute={id:id,anchor:anchor||""};
  const rd=document.getElementById("reader");
  const overview=isOverview(id);
  rd.classList.toggle("wide",overview);
  const isDone=!!done[id];
  const head=overview?'':'<div class="rdrhead"><button class="markbtn '+(isDone?'done':'')+'" onclick="toggleDone(\''+id+'\',this)">'+(isDone?'✓ 已掌握':'标记已掌握')+'</button></div>';
  let html=md(body);
  if(id==="root") html=html.replace('<p>&lt;!--atlas--&gt;</p>',overviewHtml());
  rd.innerHTML=head+html;
  bindXrefs();
  typeset(function(){finishScroll(anchor,opts||{});});
  revealNode(id);
  document.querySelectorAll('.tnode').forEach(e=>e.classList.toggle('sel',e.dataset.id===id));
}
function navigateNode(id,anchor){
  saveCurrentState();
  const st={id:id,anchor:anchor||"",scroll:0};
  history.pushState(st,"",routeUrl(id,anchor));
  renderNode(id,anchor);
}
function toggleDone(id,btn){
  const st=currentState();
  done[id]=!done[id]; if(!done[id])delete done[id];
  try{localStorage.setItem("agentkb_done",JSON.stringify(done));}catch(e){}
  buildTree();bind();updateProg();
  history.replaceState(st,"",location.href);
  renderNode(id,st.anchor,{scroll:st.scroll,restore:true});
}
function updateProg(){
  const ids=Object.keys(LABEL).filter(i=>!isOverview(i)&&!HREF[i]);
  const el=document.getElementById("prog");
  el.textContent=ids.length?'已掌握 '+ids.filter(i=>done[i]).length+'/'+ids.length:'';
}
function bind(){
  document.querySelectorAll('.tnode').forEach(el=>{
    el.onclick=function(e){e.stopPropagation();const id=el.dataset.id;
      if(el.dataset.href){location.href=el.dataset.href;return;}
      const kidsBox=document.querySelector('[data-kids="'+id+'"]');
      if(kidsBox){const showing=kidsBox.style.display!=='none';kidsBox.style.display=showing?'none':'';el.querySelector('.cv').classList.toggle('open',!showing);}
      navigateNode(id);
    };
  });
}
window.addEventListener("popstate",function(e){
  const st=e.state||routeFromHash()||{id:"root",anchor:"",scroll:0};
  renderNode(st.id,st.anchor||"",{scroll:st.scroll||0,restore:true});
});
window.addEventListener("scroll",rememberScroll,{passive:true});
document.getElementById("reader").addEventListener("scroll",rememberScroll,{passive:true});
buildTree();bind();updateProg();
const initial=routeFromHash()||{id:"root",anchor:"",scroll:0};
history.replaceState({id:initial.id,anchor:initial.anchor||"",scroll:0},"",location.href);
renderNode(initial.id,initial.anchor||"",{scroll:initial.scroll||0,restore:true});
</script>
</body>
</html>
"""

# 先填入 JSON,最后填入正文块,避免正文中的占位符文字被误替换
html = (TEMPLATE.replace("__TREE__", js_json(TREE))
        .replace("__ATLAS__", js_json(ATLAS))
        .replace("__STATUS__", js_json(STATUS))
        .replace("__BLOCKS__", BLOCKS))
(BASE / "知识地图.html").write_text(html, encoding="utf-8")
print("生成 知识地图.html ✓;节点:", ", ".join(sorted(sections.keys())))
print("图谱:", ", ".join("%s %d" % (p["id"], len(p["points"])) for p in ATLAS))
if problems:
    print("一致性提示:")
    for msg in problems:
        print("  -", msg)
