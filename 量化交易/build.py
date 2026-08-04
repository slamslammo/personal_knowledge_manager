# -*- coding: utf-8 -*-
"""从 知识库/ 目录树生成 知识地图.html。
用法:python3 build.py
内容源头 = 知识库/ 下的所有 md(递归):多子点的分类拆成「子目录 + 每知识点一个 md」
(如 06-回测与评估/01-信号时序与因果.md),单节点保持扁平 md(如 01-参考资料.md)。
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
  {"id":"map","label":"🧭 学习路线图"},
  {"id":"refs","label":"📚 资料清单","children":[
    {"id":"learningmainline","label":"当前学习主线"},
    {"id":"c365","label":"🎓 365 天量化课程","children":[
      {"id":"c365map","label":"课程大纲与本地映射","href":"../../pam-video-captures/365-days-quant-finance/knowledge-map.html"},
      {"id":"c365guide","label":"课程学习指引"},
      {"id":"c365p1","label":"P1 量化基础要点"},
      {"id":"c365p2","label":"P2 工具栈要点"},
      {"id":"c365data","label":"数据质量与清洗"},
      {"id":"c365adjust","label":"复权与数据对齐"},
      {"id":"c365lookahead","label":"未来函数与时点"},
    ]},
    {"id":"dwq","label":"🐣 Datawhale 量化入门","children":[
      {"id":"dwqrandomwalk","label":"随机游走与布朗运动"},
      {"id":"dwqkelly","label":"概率优势与凯利仓位"},
    ]},
    {"id":"coursecompare","label":"🔀 两门课程对照"},
    {"id":"mathrefs","label":"数学基础与量化"},
    {"id":"freefinance","label":"免费金融与量化阅读"},
    {"id":"opensourcetools","label":"开源系统与 GitHub 工具"},
    {"id":"infosystems","label":"数据与财经信息源"},
  ]},
  {"id":"framework","label":"🧩 量化研究框架","children":[
    {"id":"hypothesis","label":"研究问题与假设"},
    {"id":"researchloop","label":"从研究到交易的闭环"},
  ]},
  {"id":"market","label":"🏛️ 市场与交易基础","children":[
    {"id":"instruments","label":"市场与交易标的"},
    {"id":"orders","label":"价格、订单与成交"},
    {"id":"positionpnl","label":"仓位、资金与盈亏"},
  ]},
  {"id":"datareturns","label":"📊 数据与收益","children":[
    {"id":"ohlcv","label":"OHLCV 行情数据"},
    {"id":"returns","label":"收益率与净值"},
    {"id":"randomwalk","label":"随机游走与布朗运动"},
    {"id":"alignment","label":"复权、交易日历与数据对齐"},
    {"id":"databias","label":"数据质量与偏差"},
  ]},
  {"id":"strategy","label":"🎯 策略与信号","children":[
    {"id":"signalposition","label":"信号、仓位与调仓"},
    {"id":"movingaverage","label":"趋势与移动平均线"},
    {"id":"factorsignal","label":"因子与截面信号"},
  ]},
  {"id":"backtest","label":"🧪 回测与评估","children":[
    {"id":"timing","label":"信号时序与因果"},
    {"id":"costbenchmark","label":"交易成本与基准"},
    {"id":"metrics","label":"绩效指标"},
    {"id":"backtestbias","label":"回测偏差与过拟合"},
    {"id":"validation","label":"样本外与滚动验证"},
  ]},
  {"id":"riskportfolio","label":"🛡️ 风险与组合","children":[
    {"id":"volatility","label":"波动率"},
    {"id":"sharpebeta","label":"Sharpe 与 Beta"},
    {"id":"drawdownposition","label":"最大回撤与仓位管理"},
    {"id":"kellyposition","label":"概率优势与凯利仓位"},
    {"id":"correlation","label":"相关性与分散化"},
    {"id":"portfolio","label":"组合构建与再平衡"},
  ]},
  {"id":"execution","label":"⚙️ 执行与系统","children":[
    {"id":"transaction","label":"交易成本与流动性"},
    {"id":"paperlive","label":"从模拟盘到实盘"},
    {"id":"monitoring","label":"监控、日志与风控"},
  ]},
  {"id":"advanced","label":"🚀 进阶专题","children":[
    {"id":"multifactor","label":"因子与多因子"},
    {"id":"timeseries","label":"时间序列研究"},
    {"id":"mlquant","label":"机器学习量化"},
    {"id":"dlquant","label":"深度学习与 AI 量化"},
  ]},
  {"id":"practice","label":"🔬 实验实践","children":[
    {"id":"env","label":"实验环境"},
    {"id":"experiments","label":"实验路线"},
  ]},
]

sections = {}
for m in re.finditer(r"<!--#\s*([A-Za-z0-9_]+)\s*-->\n?(.*?)(?=<!--#\s*[A-Za-z0-9_]+\s*-->|\Z)", SRC, re.S):
    sections[m.group(1)] = m.group(2).strip()

# 知识网络元数据:交叉引用边从正文 [文字](node:id) 链接自动抽取;
# full=正文是否已成文(非空行数阈值),供首页网络图区分「已成文/提纲」。
EDGES = []
_seen_edges = set()
for _nid, _body in sections.items():
    for _mm in re.finditer(r"\]\(node:([A-Za-z0-9_]+)", _body):
        _tid = _mm.group(1)
        if _tid != _nid and _tid in sections and (_nid, _tid) not in _seen_edges:
            _seen_edges.add((_nid, _tid))
            EDGES.append([_nid, _tid])
META = {nid: {"full": sum(1 for ln in body.splitlines() if ln.strip()) >= 8}
        for nid, body in sections.items()}
EDGES_JSON = json.dumps(EDGES, ensure_ascii=False)
META_JSON = json.dumps(META, ensure_ascii=False)

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
<title>量化交易 知识地图</title>
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
  .netwrap{margin:0 0 1.4em;padding:16px;border:1px solid var(--line);border-radius:10px;background:var(--panel);box-shadow:var(--shadow)}
  .netwrap h2{margin:.1em 0 .25em;font-size:18px}
  .netwrap .hint{margin:0 0 10px;color:var(--sub);font-size:13px}
  .netscroll{overflow-x:auto}
  svg.net{display:block;min-width:940px;width:100%}
  .net .lyr{font-size:13px;font-weight:600;fill:var(--ink);cursor:pointer}
  .net .lyr:hover{fill:var(--accent)}
  .net .pill{cursor:pointer}
  .net .pill rect{fill:var(--bg);stroke:var(--line);transition:opacity .12s}
  .net .pill.full rect{fill:rgba(47,116,208,.10);stroke:var(--accent)}
  .net .pill.stub rect{stroke-dasharray:4 3}
  .net .pill text{font-size:12.5px;fill:var(--ink)}
  .net .pill .dk{fill:var(--ok);font-size:11px}
  .net .edge{fill:none;stroke:var(--accent);stroke-opacity:.32;stroke-width:1.5;transition:stroke-opacity .12s}
  .net.hl .edge{stroke-opacity:.05}
  .net.hl .edge.on{stroke-opacity:.9;stroke-width:2}
  .net.hl .pill{opacity:.22}
  .net.hl .pill.on{opacity:1}
  .net.hl .lyr{opacity:.35}
  .net .flowarr{stroke:var(--sub);stroke-opacity:.45;stroke-width:1.2;fill:none}
  .netlegend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--sub);margin-top:10px}
  .rel h3{margin:.8em 0 .4em}
  .relrow{display:flex;gap:10px;align-items:flex-start;margin:.4em 0}
  .relk{flex:none;color:var(--sub);font-size:12.5px;padding-top:4px;width:64px}
  .relchips{display:flex;flex-wrap:wrap;gap:6px}
  .relchips a{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:3px 8px;background:var(--bg);text-decoration:none}
  .relchips a:hover{border-color:var(--accent)}
  mjx-container{overflow-x:auto;overflow-y:hidden}
</style>
<script>window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},svg:{fontCache:'global'}};</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
<header>
  <h1>量化交易 知识地图</h1>
  <span class="prog" id="prog"></span>
</header>
<div class="wrap">
  <aside id="tree"></aside>
  <main id="reader"></main>
</div>
__BLOCKS__
<script>
const TREE=__TREE__;
const EDGES=__EDGES__;
const META=__META__;
const CONTENT={},LABEL={},PARENT={},HREF={},NODES={};
document.querySelectorAll('script[type="text/markdown"]').forEach(s=>CONTENT[s.dataset.node]=s.textContent);
(function walk(ns,parent){ns.forEach(n=>{LABEL[n.id]=n.label;NODES[n.id]=n;if(n.href)HREF[n.id]=n.href;if(parent)PARENT[n.id]=parent;if(n.children)walk(n.children,n.id)})})(TREE,"");
let done=JSON.parse(localStorage.getItem("quantkb_done")||"{}");
let currentRoute={id:"map",anchor:""};
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
  if(q.has("node")) return {id:q.get("node")||"map",anchor:q.get("anchor")||"",scroll:0};
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
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(m,txt,url){if(url.indexOf('node:')===0){var r=url.slice(5).split('#'),nid=r[0],an=r[1]||'';return '<a href="'+attr(routeUrl(nid,an))+'" class="xref" data-node="'+attr(nid)+'" data-anchor="'+attr(an)+'">'+txt+'</a>';}var external=/^(https?:|mailto:|#)/.test(url);var clean=url.replace(/^(?:\.\.\/)+/,'');var sibling=/^(?:\.\.\/)+(?:机器学习|深度学习)\//.test(url);var pam=/^(?:\.\.\/)+pam-video-captures\//.test(url);var out=external?url:(sibling?'../'+clean:(pam?'../../'+clean:clean));return '<a href="'+out+'" target="_blank" rel="noopener">'+txt+'</a>';});}
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
function pillW(s){var w=0;for(var i=0;i<s.length;i++){w+=s.charCodeAt(i)>255?13:7.2;}return Math.round(w)+26;}
function overviewHtml(){
  var order=["#\u8bfe\u7a0b\u5b66\u4e60\uff08\u8d44\u6599\u6e05\u5355\uff09","c365","dwq","#\u81ea\u6709\u91cf\u5316\u4f53\u7cfb\uff08\u6b63\u6587\u5f85\u6574\u7406\uff09","framework","market","datareturns","strategy","backtest","riskportfolio","execution","advanced","practice"];
  var W=1056,x0=200,xmax=1046,ph=30,y=16,pos={},layers=[],seps=[];
  order.forEach(function(gid){
    if(gid.charAt(0)==="#"){seps.push({y:y,label:gid.slice(1)});y+=30;return;}
    var g=NODES[gid];
    if(!g)return;
    var rowY=y,x=x0;
    layers.push({id:gid,y:rowY,label:g.label});
    (g.children||[]).forEach(function(c){
      var w=pillW((LABEL[c.id]||c.id)+(done[c.id]?" ✓":""));
      if(x+w>xmax){x=x0;rowY+=40;}
      pos[c.id]={x:x,y:rowY,w:w};x+=w+10;
    });
    y=rowY+ph+38;
  });
  var H=y-14;
  var s='<svg class="net" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';
  s+='<defs><marker id="na" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M2 1L8 5L2 9" fill="none" stroke="var(--sub)" stroke-width="1.5"/></marker></defs>';
  var drawn={};
  EDGES.forEach(function(e){
    var k=e[0]<e[1]?e[0]+"|"+e[1]:e[1]+"|"+e[0];
    if(drawn[k])return;drawn[k]=1;
    var a=pos[e[0]],b=pos[e[1]];if(!a||!b)return;
    var d;
    if(a.y===b.y){
      var ax=a.x+a.w/2,bx=b.x+b.w/2,yy=a.y+ph;
      d='M'+ax+' '+yy+' C'+ax+' '+(yy+22)+' '+bx+' '+(yy+22)+' '+bx+' '+yy;
    }else{
      var top=a.y<b.y?a:b,bot=a.y<b.y?b:a;
      var tx=top.x+top.w/2,bx2=bot.x+bot.w/2,dy=(bot.y-top.y-ph)*0.35;
      d='M'+tx+' '+(top.y+ph)+' C'+tx+' '+(top.y+ph+dy)+' '+bx2+' '+(bot.y-dy)+' '+bx2+' '+bot.y;
    }
    s+='<path class="edge" data-a="'+attr(e[0])+'" data-b="'+attr(e[1])+'" d="'+d+'"/>';
  });
  seps.forEach(function(sp){
    s+='<text class="sep" x="24" y="'+(sp.y+16)+'">'+sp.label+'</text>';
    s+='<line class="sepline" x1="24" y1="'+(sp.y+23)+'" x2="'+(W-16)+'" y2="'+(sp.y+23)+'"/>';
  });
  layers.forEach(function(l){
    s+='<text class="lyr" x="24" y="'+(l.y+19)+'" data-id="'+attr(l.id)+'">'+l.label+'</text>';
  });
  Object.keys(pos).forEach(function(id){
    var p=pos[id],full=META[id]&&META[id].full;
    s+='<g class="pill '+(full?'full':'stub')+'" data-id="'+attr(id)+'"><rect x="'+p.x+'" y="'+p.y+'" width="'+p.w+'" height="'+ph+'" rx="8"/><text x="'+(p.x+13)+'" y="'+(p.y+19)+'">'+(LABEL[id]||id)+(done[id]?'<tspan class="dk"> ✓</tspan>':'')+'</text></g>';
  });
  s+='</svg>';
  return '<section class="netwrap"><h2>知识网络</h2><p class="hint">上半是两条课程轨（已有笔记），下半是自有体系九章（正文待整理）。实心节点已成文，虚线节点只有边界说明；曲线是节点互引。悬停看关联，点击进入正文。</p><div class="netscroll">'+s+'</div><div class="netlegend"><span style="color:var(--accent)">▣ 已成文</span><span>▢ 待整理</span><span style="color:var(--ok)">✓ 已掌握</span><span style="color:var(--accent)">⌒ 交叉互引</span></div></section>';
}
function bindNet(){
  var svg=document.querySelector('#reader svg.net');if(!svg)return;
  function clear(){svg.classList.remove('hl');svg.querySelectorAll('.on').forEach(function(e){e.classList.remove('on');});}
  svg.querySelectorAll('.pill').forEach(function(p){
    var id=p.dataset.id;
    p.addEventListener('click',function(){navigateNode(id);});
    p.addEventListener('mouseenter',function(){
      clear();svg.classList.add('hl');p.classList.add('on');
      svg.querySelectorAll('.edge').forEach(function(ed){
        if(ed.dataset.a===id||ed.dataset.b===id){
          ed.classList.add('on');
          var other=ed.dataset.a===id?ed.dataset.b:ed.dataset.a;
          var op=svg.querySelector('.pill[data-id="'+other+'"]');if(op)op.classList.add('on');
        }
      });
    });
    p.addEventListener('mouseleave',clear);
  });
  svg.querySelectorAll('.lyr').forEach(function(t){
    t.addEventListener('click',function(){navigateNode(t.dataset.id);});
  });
}
function relatedHtml(id){
  if(id==="map")return '';
  var outs=[],ins=[];
  EDGES.forEach(function(e){
    if(e[0]===id&&outs.indexOf(e[1])<0)outs.push(e[1]);
    if(e[1]===id&&ins.indexOf(e[0])<0)ins.push(e[0]);
  });
  if(!outs.length&&!ins.length)return '';
  function chips(a){return a.map(function(n){return '<a class="xref" href="'+attr(routeUrl(n))+'" data-node="'+attr(n)+'">'+(LABEL[n]||n)+'</a>';}).join('');}
  var h='<hr><section class="rel"><h3>知识网络</h3>';
  if(outs.length)h+='<div class="relrow"><span class="relk">本文引用</span><span class="relchips">'+chips(outs)+'</span></div>';
  if(ins.length)h+='<div class="relrow"><span class="relk">被引用</span><span class="relchips">'+chips(ins)+'</span></div>';
  return h+'</section>';
}
function frameworkOverviewHtml(){
  const steps=[
    ["1. 理解市场","标的、订单、仓位","明确真实交易约束"],
    ["2. 准备数据","行情、收益、时点","保证证据可用"],
    ["3. 提出假设","现象、机制、规则","形成可证伪问题"],
    ["4. 回测评价","因果、成本、基准","检验是否稳健"],
    ["5. 风险执行","组合、风控、监控","进入下一轮复盘"],
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
  rd.classList.toggle("wide",["map","refs","c365","c365guide","c365p1","c365p2","coursecompare","dwq"].indexOf(id)>=0);
  rd.innerHTML='<div class="rdrhead"><button class="markbtn '+(isDone?'done':'')+'" onclick="toggleDone(\''+id+'\',this)">'+(isDone?'✓ 已掌握':'标记已掌握')+'</button></div>'+(id==="map"?overviewHtml():"")+(id==="framework"?frameworkOverviewHtml():"")+md(body)+relatedHtml(id);
  bindXrefs();
  if(id==="map")bindNet();
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
  localStorage.setItem("quantkb_done",JSON.stringify(done));
  buildTree();bind();updateProg();
  history.replaceState(st,"",location.href);
  renderNode(id,st.anchor,{scroll:st.scroll,restore:true});
}
function updateProg(){
  const groups=['map','refs','c365','dwq','framework','market','datareturns','strategy','backtest','riskportfolio','execution','advanced','practice'];
  const ids=Object.keys(LABEL).filter(i=>groups.indexOf(i)<0&&!HREF[i]);
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
  const st=e.state||routeFromHash()||{id:"map",anchor:"",scroll:0};
  renderNode(st.id,st.anchor||"",{scroll:st.scroll||0,restore:true});
});
window.addEventListener("scroll",rememberScroll,{passive:true});
document.getElementById("reader").addEventListener("scroll",rememberScroll,{passive:true});
buildTree();bind();updateProg();
const initial=routeFromHash()||{id:"map",anchor:"",scroll:0};
history.replaceState({id:initial.id,anchor:initial.anchor||"",scroll:0},"",location.href);
renderNode(initial.id,initial.anchor||"",{scroll:initial.scroll||0,restore:true});
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__BLOCKS__", BLOCKS).replace("__TREE__", TREE_JSON).replace("__EDGES__", EDGES_JSON).replace("__META__", META_JSON)
(BASE / "知识地图.html").write_text(html, encoding="utf-8")
full_n = sum(1 for v in META.values() if v["full"])
print("生成 知识地图.html ✓ ;知识点:", len(sections), ";已成文:", full_n, ";交叉引用边:", len(EDGES))
