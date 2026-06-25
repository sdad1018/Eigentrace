/* EigenTrace universal side-nav — WCAG 2.1 AA + Flower-of-Life tab.
   Self-contained, scoped (etsn-). Add: <script src="/assets/sidenav.js" defer></script> */
(function () {
  "use strict";
  if (document.getElementById('etsn-root')) return;

  var SECTIONS = [
    { group: "Findings", links: [
      { href: "/llm-consensus-geometry-iran-2026", label: "The Iran Arc" },
      { href: "/consequence-atlas", label: "The Atlas of the Unsaid" },
      { href: "/anamnesis", label: "Anamnesis" },
      { href: "/summary-plus", label: "Summary Plus" },
      { href: "/boundary", label: "The Boundary" },
      { href: "/overview", label: "Overview" }
    ]},
    { group: "Live instruments", links: [
      { href: "/eigenching", label: "EigenChing" },
      { href: "/thoughts", label: "Reflections" },
      { href: "/deepseek", label: "Model Outliers" }
    ]},
    { group: "More", links: [
      { href: "/dynamics", label: "Bias or Dynamics?" },
      { href: "/sean-adams", label: "About" }
    ]},
    { group: "Watch & build", links: [
      { href: "https://www.youtube.com/@AINN24HourNews", label: "Live broadcast", ext: true },
      { href: "https://github.com/sdad1018/Eigentrace", label: "GitHub", ext: true }
    ]}
  ];

  // exact 19-circle Flower of Life (triangular lattice, r=26)
  var CIRCLES = [
    [0,0],[-13,-22.52],[13,-22.52],[26,0],[13,22.52],[-13,22.52],[-26,0],
    [-39,-22.52],[0,-45.03],[39,-22.52],[39,22.52],[0,45.03],[-39,22.52],
    [-26,-45.03],[26,-45.03],[52,0],[26,45.03],[-26,45.03],[-52,0]
  ];

  var css = `
  #etsn-root{position:fixed;z-index:2147483000;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  #etsn-toggle{position:fixed;top:50%;left:0;transform:translateY(-50%);
    min-width:56px;min-height:240px;padding:34px 14px;cursor:pointer;overflow:hidden;
    background:#141416;border:1px solid rgba(180,180,255,.18);border-left:none;
    border-radius:0 10px 10px 0;box-shadow:5px 0 22px rgba(0,0,0,.55);
    display:flex;align-items:center;justify-content:center;position:fixed;
    transition:background .5s ease,transform .5s ease,box-shadow .5s ease;}
  #etsn-toggle:hover{background:#1a1a20;transform:translateY(-50%) translateX(4px);
    box-shadow:8px 0 30px rgba(120,100,200,.28);}
  #etsn-toggle:focus-visible{outline:3px solid #b4b4ff;outline-offset:3px;}
  #etsn-geo{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    width:150px;height:300px;pointer-events:none;opacity:.55;
    transition:opacity .5s ease,filter .5s ease;filter:drop-shadow(0 0 2px transparent);}
  #etsn-toggle:hover #etsn-geo{opacity:1;filter:drop-shadow(0 0 5px rgba(180,180,255,.45));}
  .etsn-geo-path{fill:none;stroke:rgba(180,180,255,.20);stroke-width:.7;
    transition:stroke .5s ease,stroke-width .5s ease;
    stroke-dasharray:1;stroke-dashoffset:1;}
  #etsn-toggle:hover .etsn-geo-path{stroke:rgba(190,185,255,.85);stroke-width:1;}
  @media (prefers-reduced-motion: no-preference){
    .etsn-geo-path{animation:etsnDraw 2.8s cubic-bezier(.4,0,.2,1) forwards;}
    @keyframes etsnDraw{to{stroke-dashoffset:0;}}
  }
  @media (prefers-reduced-motion: reduce){.etsn-geo-path{stroke-dashoffset:0;}}
  #etsn-label{writing-mode:vertical-rl;text-orientation:mixed;transform:rotate(180deg);
    position:relative;z-index:2;pointer-events:none;color:#f0f0f5;
    font-size:14px;font-weight:600;letter-spacing:.1em;
    mix-blend-mode:exclusion;white-space:nowrap;}
  #etsn-panel{position:fixed;top:0;left:0;height:100%;width:300px;max-width:86vw;
    background:#1a1a1a;color:#f5f5f5;border-right:2px solid #ffffff;
    transform:translateX(-100%);transition:transform .3s cubic-bezier(.16,1,.3,1);
    overflow-y:auto;-webkit-overflow-scrolling:touch;box-shadow:8px 0 28px rgba(0,0,0,.5);padding:0 0 32px;}
  #etsn-root.open #etsn-panel{transform:translateX(0);}
  #etsn-head{display:flex;align-items:center;justify-content:space-between;padding:18px 20px;
    border-bottom:2px solid #3a3a3a;position:sticky;top:0;background:#1a1a1a;}
  #etsn-title{font-size:15px;font-weight:700;letter-spacing:.04em;color:#fff;}
  #etsn-close{min-width:44px;min-height:44px;background:transparent;border:2px solid #6a6a6a;
    border-radius:6px;color:#fff;font-size:22px;line-height:1;cursor:pointer;
    display:flex;align-items:center;justify-content:center;}
  #etsn-close:hover{border-color:#fff;background:#000;}
  #etsn-close:focus-visible{outline:3px solid #b4b4ff;outline-offset:2px;}
  .etsn-group{padding:14px 20px 4px;font-size:12px;font-weight:700;letter-spacing:.1em;
    text-transform:uppercase;color:#9a9a9a;}
  .etsn-link{display:block;padding:13px 20px;min-height:44px;color:#f5f5f5;
    text-decoration:underline;text-decoration-color:#6a6a6a;text-underline-offset:3px;
    font-size:16px;line-height:1.4;border-left:4px solid transparent;box-sizing:border-box;}
  .etsn-link:hover{background:#2a2a2a;text-decoration-color:#fff;}
  .etsn-link:focus-visible{outline:3px solid #b4b4ff;outline-offset:-3px;background:#2a2a2a;}
  .etsn-link[aria-current="page"]{border-left-color:#b4b4ff;background:#222;font-weight:700;text-decoration:none;}
  .etsn-ext{color:#bcbcbc;font-size:13px;margin-left:6px;}
  #etsn-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;
    pointer-events:none;transition:opacity .3s ease;z-index:-1;}
  #etsn-root.open #etsn-backdrop{opacity:1;pointer-events:auto;}
  @media (prefers-reduced-motion: reduce){#etsn-panel,#etsn-backdrop,#etsn-toggle{transition:none;}}
  `;
  var style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  var here = location.pathname.replace(/\/+$/, '') || '/';
  function isCurrent(href){
    if(/^https?:/.test(href)) return false;
    var h = href.replace(/\/+$/, '') || '/';
    return h === here || (h !== '/' && here.indexOf(h) === 0);
  }

  var root = document.createElement('div'); root.id='etsn-root';
  var backdrop = document.createElement('div'); backdrop.id='etsn-backdrop'; backdrop.setAttribute('tabindex','-1');

  // build the SVG geometry string from exact coords
  var svg = '<svg id="etsn-geo" viewBox="-80 -160 160 320" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><g>';
  CIRCLES.forEach(function(c){ svg += '<circle class="etsn-geo-path" pathLength="1" cx="'+c[0]+'" cy="'+c[1]+'" r="26"/>'; });
  svg += '<circle class="etsn-geo-path" pathLength="1" cx="0" cy="0" r="78" stroke-dasharray="0"/></g></svg>';

  var toggle = document.createElement('button');
  toggle.id='etsn-toggle'; toggle.type='button';
  toggle.setAttribute('aria-expanded','false'); toggle.setAttribute('aria-controls','etsn-panel');
  toggle.setAttribute('aria-label','Open site menu — see everything');
  toggle.innerHTML = svg + '<span id="etsn-label">click here to see everything</span>';

  var panel = document.createElement('nav'); panel.id='etsn-panel';
  panel.setAttribute('aria-label','Site sections'); panel.setAttribute('aria-hidden','true');
  var head = document.createElement('div'); head.id='etsn-head';
  var title = document.createElement('span'); title.id='etsn-title'; title.textContent='EigenTrace';
  var close = document.createElement('button'); close.id='etsn-close'; close.type='button';
  close.setAttribute('aria-label','Close menu'); close.innerHTML='&times;';
  head.appendChild(title); head.appendChild(close); panel.appendChild(head);

  SECTIONS.forEach(function(sec){
    var g=document.createElement('div'); g.className='etsn-group'; g.textContent=sec.group; panel.appendChild(g);
    sec.links.forEach(function(l){
      var a=document.createElement('a'); a.className='etsn-link'; a.href=l.href; a.textContent=l.label;
      if(l.ext){ a.target='_blank'; a.rel='noopener';
        var e=document.createElement('span'); e.className='etsn-ext'; e.setAttribute('aria-hidden','true'); e.textContent='↗';
        a.appendChild(document.createTextNode(' ')); a.appendChild(e);
        a.setAttribute('aria-label', l.label+' (opens in new tab)'); }
      if(isCurrent(l.href)) a.setAttribute('aria-current','page');
      panel.appendChild(a);
    });
  });

  root.appendChild(backdrop); root.appendChild(toggle); root.appendChild(panel);
  document.body.appendChild(root);

  var lastFocus=null;
  function openMenu(){ lastFocus=document.activeElement; root.classList.add('open');
    toggle.setAttribute('aria-expanded','true'); panel.setAttribute('aria-hidden','false');
    (panel.querySelector('.etsn-link')||close).focus(); document.addEventListener('keydown',onKey); }
  function closeMenu(){ root.classList.remove('open');
    toggle.setAttribute('aria-expanded','false'); panel.setAttribute('aria-hidden','true');
    document.removeEventListener('keydown',onKey); (lastFocus&&lastFocus.focus?lastFocus:toggle).focus(); }
  function onKey(e){
    if(e.key==='Escape'){ e.preventDefault(); closeMenu(); return; }
    if(e.key==='Tab'){ var f=panel.querySelectorAll('button,a[href]'); if(!f.length)return;
      var first=f[0], last=f[f.length-1];
      if(e.shiftKey&&document.activeElement===first){ e.preventDefault(); last.focus(); }
      else if(!e.shiftKey&&document.activeElement===last){ e.preventDefault(); first.focus(); } }
  }
  toggle.addEventListener('click',function(){ root.classList.contains('open')?closeMenu():openMenu(); });
  close.addEventListener('click',closeMenu);
  backdrop.addEventListener('click',closeMenu);
})();
