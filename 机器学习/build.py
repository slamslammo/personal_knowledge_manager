# -*- coding: utf-8 -*-
"""从 知识库/ 目录树生成 知识地图.html。
用法:python3 build.py
内容源头 = 知识库/ 下的所有 md(递归):多子点的分类拆成「子目录 + 每知识点一个 md」
(如 02-数学基础/01-微积分.md),单节点保持扁平 md(如 01-参考资料.md)。
每个 md 用 <!--# 节点id --> 标记其对应的 TREE 节点(按标记解析,文件名随意)。
公式用 $...$ / $$...$$(LaTeX,MathJax 渲染);图片就近写相对路径——
源 md 在子目录里用 ../../assets/x.png(Obsidian 能渲染),生成 html 时渲染器
会剥掉开头的 ../ 还原成 assets/x.png(见 inline())。改完内容跑此脚本即更新视图。
渲染器支持:标题/列表/引用/图片/链接/**加粗**/`行内代码`/代码块/GFM 表格(需含 |---| 分隔行)。
约束:公式 \\text{} 内勿放中文(tex-svg 无中文字体)。"""
import json, re, pathlib

BASE = pathlib.Path(__file__).parent
# 内容源头 = 知识库/ 递归读取所有 md(子目录 + 扁平文件混合);按 <!--# id --> 标记解析,顺序不影响内容映射
SRC = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((BASE / "知识库").rglob("*.md")))

TREE = [
  {"id":"map","label":"🧭 知识地图"},
  {"id":"refs","label":"📚 资料清单"},
  {"id":"framework","label":"🧩 基本框架","children":[
    {"id":"lossopt","label":"模型、损失与优化"},
    {"id":"generalization","label":"泛化与归纳偏好"},
  ]},
  {"id":"features","label":"🔎 数据与特征","children":[
    {"id":"data","label":"数据集、任务与特征"},
    {"id":"preprocess","label":"数据预处理"},
    {"id":"featureeng","label":"特征工程"},
  ]},
  {"id":"evaluation","label":"📏 模型评估","children":[
    {"id":"split","label":"训练集、验证集与测试集"},
    {"id":"metrics","label":"常用评价指标"},
    {"id":"overfit","label":"过拟合与欠拟合"},
    {"id":"cv","label":"交叉验证"},
    {"id":"leakage","label":"数据泄漏"},
  ]},
  {"id":"supervised","label":"🎯 监督学习","children":[
    {"id":"linreg","label":"线性回归"},
    {"id":"logreg","label":"逻辑回归与 softmax"},
    {"id":"regularization","label":"正则化"},
    {"id":"knn","label":"KNN"},
    {"id":"bayes","label":"朴素贝叶斯"},
    {"id":"tree","label":"决策树"},
    {"id":"ensemble","label":"随机森林与集成学习"},
    {"id":"svm","label":"SVM 与核方法"},
  ]},
  {"id":"unsupervised","label":"🧱 无监督学习","children":[
    {"id":"pca","label":"PCA"},
    {"id":"kmeans","label":"K-means"},
    {"id":"gmmem","label":"GMM 与 EM"},
    {"id":"hiercluster","label":"层次聚类"},
  ]},
  {"id":"practice","label":"🧪 实验实践","children":[
    {"id":"env","label":"实验环境"},
    {"id":"experiments","label":"实验路线"},
    {"id":"irisdata","label":"Iris 数据分析实验"},
    {"id":"sklearn","label":"sklearn 实践范式"},
    {"id":"pipeline","label":"Pipeline 与 GridSearchCV"},
    {"id":"mlpbridge","label":"MLPClassifier 连接深度学习"},
  ]},
  {"id":"bridge","label":"🌉 深度学习","href":"../深度学习/知识地图.html"},
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
<title>机器学习 知识梳理</title>
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
  main th:nth-child(1),main td:nth-child(1),main th:nth-child(2),main td:nth-child(2){white-space:nowrap}
  main tbody tr:nth-child(even) td{background:rgba(127,127,127,.06)}
  .atlas{margin:0 0 1.4em;padding:16px;border:1px solid var(--line);border-radius:10px;background:var(--panel);box-shadow:var(--shadow)}
  .atlas h2{margin:.1em 0 .25em;font-size:18px}
  .atlas .hint{margin:0 0 12px;color:var(--sub);font-size:13px}
  .flow{display:flex;align-items:center;gap:8px;flex-wrap:nowrap;overflow:visible;margin:12px 0 16px;padding-bottom:2px}
  .flow a{display:inline-flex;align-items:center;min-height:34px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);font-weight:600;text-decoration:none}
  .flow .arrow{color:var(--sub)}
  .atlasgrid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}
  @media(max-width:1180px){.flow{flex-wrap:wrap}.atlasgrid{grid-template-columns:repeat(3,minmax(0,1fr))}}
  @media(max-width:760px){.atlasgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
  @media(max-width:520px){.atlasgrid{grid-template-columns:1fr}}
  .atlascard{border:1px solid var(--line);border-radius:8px;background:var(--bg);padding:8px;min-height:0}
  .atlascard>a{display:block;font-weight:700;text-decoration:none;margin-bottom:6px;font-size:14px;line-height:1.25;white-space:nowrap}
  .chips{display:flex;flex-direction:column;align-items:flex-start;gap:3px}
  .chips a{font-size:11.5px;line-height:1.25;text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:3px 6px;background:var(--panel)}
  .featuremap{margin:0 0 1.4em;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
  .featureflow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr))}
  .featurestep{padding:3px 14px;border-left:1px solid var(--line)}
  .featurestep:first-child{border-left:none;padding-left:0}
  .featurestep:last-child{padding-right:0}
  .featurestep strong{display:block;color:var(--accent);font-size:13.5px;margin-bottom:4px}
  .featurestep span{display:block;color:var(--sub);font-size:12px;line-height:1.45}
  @media(max-width:900px){.featureflow{grid-template-columns:1fr 1fr}.featurestep{border-left:none;border-top:1px solid var(--line);padding:10px 0}.featurestep:first-child{border-top:none}}
  .todo{color:var(--todo)}
  mjx-container{overflow-x:auto;overflow-y:hidden}
</style>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},svg:{fontCache:'global'}};</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
<header>
  <h1>机器学习 知识梳理</h1>
  <span class="prog" id="prog"></span>
</header>
<div class="wrap">
  <aside id="tree"></aside>
  <main id="reader"></main>
</div>
__BLOCKS__
<script>
const TREE=__TREE__;
const CONTENT={},LABEL={},PARENT={},HREF={};
document.querySelectorAll('script[type="text/markdown"]').forEach(s=>CONTENT[s.dataset.node]=s.textContent);
(function walk(ns,parent){ns.forEach(n=>{LABEL[n.id]=n.label;if(n.href)HREF[n.id]=n.href;if(parent)PARENT[n.id]=parent;if(n.children)walk(n.children,n.id)})})(TREE,"");
let done=JSON.parse(localStorage.getItem("mlkb_done")||"{}");
let currentRoute={id:"root",anchor:""};
if("scrollRestoration" in history){history.scrollRestoration="manual";}
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
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(m,txt,url){if(url.indexOf('node:')===0){var r=url.slice(5).split('#'),nid=r[0],an=r[1]||'';return '<a href="'+attr(routeUrl(nid,an))+'" class="xref" data-node="'+attr(nid)+'" data-anchor="'+attr(an)+'">'+txt+'</a>';}var cross=url.indexOf('../资料/')===0||url.indexOf('../深度学习/')===0;var out=/^(https?:|mailto:|#)/.test(url)?url:(cross?url:url.replace(/^(?:\.\.\/)+/,''));return '<a href="'+out+'" target="_blank" rel="noopener">'+txt+'</a>';});}
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
  const flowIds=["framework","features","evaluation","supervised","unsupervised","practice","bridge"];
  const flow='<div class="flow">'+flowIds.map(function(id,i){
    const href=HREF[id]||routeUrl(id);
    const cls=HREF[id]?'':' class="xref" data-node="'+attr(id)+'"';
    return (i?'<span class="arrow">→</span>':'')+'<a href="'+attr(href)+'"'+cls+'>'+(LABEL[id]||id)+'</a>';
  }).join('')+'</div>';
  const cards=TREE.filter(function(n){return ["map","refs","bridge"].indexOf(n.id)<0;}).map(function(n){
    const kids=(n.children||[]).map(function(c){
      return '<a class="xref" href="'+attr(routeUrl(c.id))+'" data-node="'+attr(c.id)+'">'+(LABEL[c.id]||c.id)+'</a>';
    }).join('');
    const href=HREF[n.id]||routeUrl(n.id);
    const cls=HREF[n.id]?'':' class="xref" data-node="'+attr(n.id)+'"';
    return '<article class="atlascard"><a href="'+attr(href)+'"'+cls+'>'+n.label+'</a><div class="chips">'+kids+'</div></article>';
  }).join('');
  return '<section class="atlas"><h2>机器学习路线图</h2>'+flow+'<div class="atlasgrid">'+cards+'</div></section>';
}
function featureOverviewHtml(){
  const steps=[
    ["1. 定义数据","样本、特征、标签","明确要学习什么"],
    ["2. 诊断数据","分布、缺失、异常、关系","判断数据有什么问题"],
    ["3. 预处理","清洗、编码、缩放","形成稳定一致的输入"],
    ["4. 特征工程","选择、构造、压缩","改进模型看到的表达"],
    ["5. 进入建模","划分、训练、评估","验证处理是否真正有效"],
  ];
  return '<section class="featuremap"><div class="featureflow">'+steps.map(function(s){return '<div class="featurestep"><strong>'+s[0]+'</strong><span>'+s[1]+'</span><span>'+s[2]+'</span></div>';}).join('')+'</div></section>';
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
  const isDone=!!done[id];
  const rd=document.getElementById("reader");
  rd.classList.toggle("wide",["root","map","refs","features","data","preprocess","featureeng","irisdata"].indexOf(id)>=0);
  rd.innerHTML='<div class="rdrhead"><button class="markbtn '+(isDone?'done':'')+'" onclick="toggleDone(\''+id+'\',this)">'+(isDone?'✓ 已掌握':'标记已掌握')+'</button></div>'+((id==="root"||id==="map")?overviewHtml():"")+(id==="features"?featureOverviewHtml():"")+md(body);
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
function openNode(id,anchor){
  navigateNode(id,anchor);
}
function toggleDone(id,btn){
  const st=currentState();
  done[id]=!done[id]; if(!done[id])delete done[id];
  localStorage.setItem("mlkb_done",JSON.stringify(done));
  buildTree();bind();updateProg();
  history.replaceState(st,"",location.href);
  renderNode(id,st.anchor,{scroll:st.scroll,restore:true});
}
function updateProg(){
  const groups=['map','refs','framework','features','evaluation','supervised','unsupervised','practice','bridge'];
  const ids=Object.keys(LABEL).filter(i=>groups.indexOf(i)<0);
  const d=ids.filter(i=>done[i]).length;
  document.getElementById("prog").textContent='已掌握 '+d+'/'+ids.length;
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

html = TEMPLATE.replace("__BLOCKS__", BLOCKS).replace("__TREE__", TREE_JSON)
(BASE / "知识地图.html").write_text(html, encoding="utf-8")
print("生成 知识地图.html ✓ ;知识点:", sorted(sections.keys()))
