# -*- coding: utf-8 -*-
"""从 知识库/ 目录树生成 知识地图.html。
用法:python3 build.py
内容源头 = 知识库/ 下的所有 md(递归):多子点的分类拆成「子目录 + 每知识点一个 md」
(如 02-数学基础/01-微积分.md),单节点保持扁平 md(如 01-参考资料.md)。
每个 md 用 <!--# 节点id --> 标记其对应的 TREE 节点(按标记解析,文件名随意)。
公式用 $...$ / $$...$$(LaTeX,MathJax 渲染);图片就近写相对路径——
源 md 在子目录里用 ../../assets/x.png(Obsidian 能渲染),生成 html 时渲染器
会剥掉开头的 ../ 还原成 assets/x.png(见 inline())。改完内容跑此脚本即更新视图。
渲染器支持:标题/列表/引用/图片/链接/**加粗**/`行内代码`/GFM 表格(需含 |---| 分隔行)。
约束:不支持 ```代码块```;公式 \\text{} 内勿放中文(tex-svg 无中文字体)。"""
import json, re, pathlib

BASE = pathlib.Path(__file__).parent
# 内容源头 = 知识库/ 递归读取所有 md(子目录 + 扁平文件混合);按 <!--# id --> 标记解析,顺序不影响内容映射
SRC = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((BASE / "知识库").rglob("*.md")))

TREE = [
  {"id":"refs","label":"📚 参考资料"},
  {"id":"math","label":"🧮 数学基础","children":[
    {"id":"calc","label":"微积分:导数与梯度"},
    {"id":"prob","label":"概率基础"},
    {"id":"linalg","label":"线性代数"},
    {"id":"matcalc","label":"矩阵求导(按需)"},
  ]},
  {"id":"ml","label":"🤖 机器学习基础","children":[
    {"id":"mlwhat","label":"机器学习概述"},
    {"id":"linreg","label":"线性回归"},
    {"id":"softmax","label":"逻辑回归 / softmax 回归"},
  ]},
  {"id":"dl","label":"🧠 深度学习","children":[
    {"id":"mlp","label":"感知机 → 多层感知机","children":[
      {"id":"nonlinear","label":"MLP 引入非线性的作用"},
    ]},
    {"id":"backprop","label":"反向传播与计算图"},
    {"id":"cnn","label":"卷积神经网络 CNN"},
    {"id":"rnn","label":"循环神经网络 RNN"},
    {"id":"attn","label":"注意力 → Transformer"},
  ]},
  {"id":"lab","label":"🧪 实验"},
]

sections = {}
for m in re.finditer(r"<!--#\s*([A-Za-z0-9_]+)\s*-->\n?(.*?)(?=<!--#\s*[A-Za-z0-9_]+\s*-->|\Z)", SRC, re.S):
    sections[m.group(1)] = m.group(2).strip()

blocks = []
for nid, body in sections.items():
    safe = body.replace("</script>", "<\\/script>")
    blocks.append('<script type="text/markdown" data-node="%s">\n%s\n</script>' % (nid, safe))
BLOCKS = "\n".join(blocks)
TREE_JSON = json.dumps(TREE, ensure_ascii=False)

TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>深度学习 知识梳理</title>
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
  aside{width:310px;flex:none;border-right:1px solid var(--line);padding:12px 8px;overflow:auto}
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
  main .tw{overflow-x:auto;margin:.8em 0}
  main table{border-collapse:collapse;width:100%;font-size:13.5px}
  main th,main td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
  main thead th{background:var(--bg);font-weight:600;white-space:nowrap}
  main tbody tr:nth-child(even) td{background:rgba(127,127,127,.06)}
  .todo{color:var(--todo)}
  mjx-container{overflow-x:auto;overflow-y:hidden}
</style>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},svg:{fontCache:'global'}};</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
<header>
  <h1>深度学习 知识梳理</h1>
  <span class="note">左侧点开看结构 · 点知识点阅读</span>
  <span class="prog" id="prog"></span>
</header>
<div class="wrap">
  <aside id="tree"></aside>
  <main id="reader"></main>
</div>
__BLOCKS__
<script>
const TREE=__TREE__;
const CONTENT={},LABEL={};
document.querySelectorAll('script[type="text/markdown"]').forEach(s=>CONTENT[s.dataset.node]=s.textContent);
(function walk(ns){ns.forEach(n=>{LABEL[n.id]=n.label;if(n.children)walk(n.children)})})(TREE);
let done=JSON.parse(localStorage.getItem("dlkb_done")||"{}");
function inline(t){return t
  .replace(/!\[([^\]]*)\]\(([^)]+)\)/g,function(m,alt,src){return '<img src="'+src.replace(/^(?:\.\.\/)+/,'')+'" alt="'+alt+'">'})
  .replace(/`([^`]+)`/g,'<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(m,txt,url){if(url.indexOf('node:')===0){var r=url.slice(5).split('#'),nid=r[0],an=r[1]||'';return '<a href="#" class="xref" onclick="openNode(\''+nid+'\''+(an?',\''+an+'\'':'')+');return false">'+txt+'</a>';}if(!/^(?:[a-z]+:|#)/i.test(url)){url=url.replace(/^(?:\.\.\/)+/,'').replace(/^\.\/+/,'');}return '<a href="'+url+'" target="_blank" rel="noopener">'+txt+'</a>';});}
function md(src){
  src=src.replace(/\r/g,'');
  var M=[];
  src=src.replace(/\$\$([\s\S]+?)\$\$/g,function(_,x){M.push('$$'+x+'$$');return '@@M'+(M.length-1)+'@@';}).replace(/\$([^\$\n]+?)\$/g,function(_,x){M.push('$'+x+'$');return '@@M'+(M.length-1)+'@@';});
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const out=[];let list=false,olist=false,quote=false,para=[];
  const fp=()=>{if(para.length){out.push('<p>'+inline(esc(para.join(' ')))+'</p>');para=[]}};
  const cl=()=>{if(list){out.push('</ul>');list=false}if(olist){out.push('</ol>');olist=false}};const cq=()=>{if(quote){out.push('</blockquote>');quote=false}};
  const cells=s=>s.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());
  const L=src.split('\n');
  for(let i=0;i<L.length;i++){
    const t=L[i].trim();let m;
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
  fp();cl();cq();
  var html=out.join('\n');
  html=html.replace(/@@M(\d+)@@/g,function(_,i){return M[+i];});
  return html;
}
function typeset(){if(window.MathJax&&MathJax.typesetPromise){MathJax.typesetPromise([document.getElementById("reader")]).catch(function(){});}}
function tnode(n,lvl){
  const kids=n.children&&n.children.length;
  let h='<div class="tnode lvl'+lvl+'" data-id="'+n.id+'"><span class="cv">'+(kids?'▸':'·')+'</span><span class="lbl">'+n.label+'</span><span class="chk">'+(done[n.id]?'✓':'')+'</span></div>';
  if(kids){h+='<div class="kids" data-kids="'+n.id+'" style="display:none">'+n.children.map(c=>tnode(c,lvl+1)).join('')+'</div>';}
  return h;
}
function buildTree(){document.getElementById("tree").innerHTML=TREE.map(n=>tnode(n,0)).join('');}
function openNode(id,anchor){
  let body=CONTENT[id];
  if(!body) body="# "+(LABEL[id]||id)+"\n\n> 🚧 本知识点待编写。";
  const isDone=!!done[id];
  const rd=document.getElementById("reader");
  rd.innerHTML='<div class="rdrhead"><button class="markbtn '+(isDone?'done':'')+'" onclick="toggleDone(\''+id+'\',this)">'+(isDone?'✓ 已掌握':'标记已掌握')+'</button></div>'+md(body);
  typeset();
  document.querySelectorAll('.tnode').forEach(e=>e.classList.toggle('sel',e.dataset.id===id));
  if(anchor){setTimeout(function(){var hs=rd.querySelectorAll('h1,h2,h3,h4');for(var i=0;i<hs.length;i++){if(hs[i].textContent.indexOf(anchor)>=0){hs[i].scrollIntoView({behavior:'smooth',block:'start'});return;}}},80);}
  else{rd.scrollTop=0;}
}
function toggleDone(id,btn){
  done[id]=!done[id]; if(!done[id])delete done[id];
  localStorage.setItem("dlkb_done",JSON.stringify(done));
  buildTree();bind();updateProg();
  openNode(id);
}
function updateProg(){
  const ids=Object.keys(LABEL).filter(i=>['math','ml','dl'].indexOf(i)<0);
  const d=ids.filter(i=>done[i]).length;
  document.getElementById("prog").textContent='已掌握 '+d+'/'+ids.length;
}
function bind(){
  document.querySelectorAll('.tnode').forEach(el=>{
    el.onclick=function(e){e.stopPropagation();const id=el.dataset.id;
      const kidsBox=document.querySelector('[data-kids="'+id+'"]');
      if(kidsBox){const showing=kidsBox.style.display!=='none';kidsBox.style.display=showing?'none':'';el.querySelector('.cv').classList.toggle('open',!showing);}
      openNode(id);
    };
  });
}
buildTree();bind();updateProg();openNode("root");
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__BLOCKS__", BLOCKS).replace("__TREE__", TREE_JSON)
(BASE / "知识地图.html").write_text(html, encoding="utf-8")
print("生成 知识地图.html ✓ ;知识点:", sorted(sections.keys()))
