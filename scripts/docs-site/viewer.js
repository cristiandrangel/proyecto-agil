(() => {
  const $ = (s,root=document) => root.querySelector(s);
  const dialog=$('#diagram-viewer'), viewport=$('.viewport',dialog), canvas=$('.canvas',dialog);
  let scale=1,x=0,y=0,width=1,height=1,active=null,previousFocus=null;
  function paint(){canvas.style.transform=`translate(${x}px,${y}px) scale(${scale})`;$('#zoom-value').textContent=Math.round(scale*100)+'%';}
  function fit(){scale=Math.min((viewport.clientWidth-48)/width,(viewport.clientHeight-48)/height);x=(viewport.clientWidth-width*scale)/2;y=(viewport.clientHeight-height*scale)/2;paint();}
  function zoom(factor,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){const next=Math.max(.03,Math.min(12,scale*factor));x=cx-(cx-x)*next/scale;y=cy-(cy-y)*next/scale;scale=next;paint();}
  function open(figure){active=figure;previousFocus=document.activeElement;canvas.replaceChildren($('.diagram-preview svg',figure).cloneNode(true));const svg=$('svg',canvas),vb=svg.viewBox.baseVal;width=vb.width;height=vb.height;svg.setAttribute('width',width);svg.setAttribute('height',height);svg.style.width=width+'px';svg.style.height=height+'px';$('#viewer-title').textContent=$('strong',figure).textContent;dialog.showModal();document.body.classList.add('modal-open');requestAnimationFrame(fit);}
  document.querySelectorAll('.diagram').forEach(figure=>{figure.querySelectorAll('[data-expand]').forEach(el=>el.addEventListener('click',()=>open(figure)));});
  $('#close-viewer').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{document.body.classList.remove('modal-open');previousFocus?.focus();});
  $('#zoom-in').onclick=()=>zoom(1.25);$('#zoom-out').onclick=()=>zoom(.8);$('#fit').onclick=fit;
  $('#actual-size').onclick=()=>{scale=1;x=(viewport.clientWidth-width)/2;y=(viewport.clientHeight-height)/2;paint();};
  viewport.addEventListener('wheel',e=>{e.preventDefault();const r=viewport.getBoundingClientRect();zoom(Math.exp(-e.deltaY*.002),e.clientX-r.left,e.clientY-r.top);},{passive:false});
  const pointers=new Map();let last=null;
  function measure(){const a=[...pointers.values()];return {x:a.reduce((s,p)=>s+p.x,0)/a.length,y:a.reduce((s,p)=>s+p.y,0)/a.length,d:a.length===2?Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y):0};}
  viewport.addEventListener('pointerdown',e=>{viewport.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});last=measure();});
  viewport.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});const now=measure();x+=now.x-last.x;y+=now.y-last.y;if(now.d&&last.d){const r=viewport.getBoundingClientRect();zoom(now.d/last.d,now.x-r.left,now.y-r.top);}else paint();last=now;});
  ['pointerup','pointercancel','lostpointercapture'].forEach(event=>viewport.addEventListener(event,e=>{pointers.delete(e.pointerId);last=pointers.size?measure():null;}));
  dialog.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){zoom(1.25);e.preventDefault();}if(e.key==='-'){zoom(.8);e.preventDefault();}if(e.key==='0')fit();});
  $('#download-svg').onclick=()=>{const svg=$('svg',canvas).cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download=active.id+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  document.querySelectorAll('[data-download-html]').forEach(button=>{button.onclick=()=>{const copy=document.documentElement.cloneNode(true);copy.querySelector('#diagram-viewer').removeAttribute('open');copy.querySelector('.canvas').replaceChildren();copy.querySelector('body').classList.remove('modal-open');const url=URL.createObjectURL(new Blob(['<!doctype html>\n',copy.outerHTML],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=button.dataset.downloadHtml;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};});
  window.addEventListener('resize',()=>{if(dialog.open)fit();});
  document.querySelectorAll('[data-print]').forEach(b=>b.onclick=()=>window.print());
  $('.mobile-index').onchange=e=>{if(e.target.value)location.hash=e.target.value;};
  const headings=[...document.querySelectorAll('article h2,article h3')];
  function progress(){const max=document.documentElement.scrollHeight-innerHeight;$('.progress').style.width=(max>0?scrollY/max*100:0)+'%';let id=headings[0]?.id;for(const h of headings){if(h.getBoundingClientRect().top<160)id=h.id;else break;}document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.toggle('current',a.getAttribute('href')==='#'+id));}
  window.addEventListener('scroll',progress,{passive:true});progress();
})();
