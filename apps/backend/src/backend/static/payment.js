'use strict';
const root=document.querySelector('#payment');
const message=document.querySelector('#payment-notice');
let pending=false;
// A retry of an uncertain request reuses its key and decision, even after reload.
const storageKey='agil-payment-attempt:'+root.dataset.orderId;
let attempt=null;
try { attempt=JSON.parse(sessionStorage.getItem(storageKey)); } catch (_) {}
function show(text,error=false) {message.textContent=text;message.className='notice '+(error?'danger':'success');message.hidden=false;}
async function simulate(decision){if(pending)return; if(attempt && attempt.decision!==decision){show('Hay un intento pendiente de confirmar. Reintenta la misma decisión para conocer su resultado.',true);return;} attempt=attempt||{key:crypto.randomUUID(),decision};try{sessionStorage.setItem(storageKey,JSON.stringify(attempt));}catch(_){} pending=true;document.querySelectorAll('.payment-actions button').forEach(b=>b.disabled=true);show('Consultando el resultado con la central…');try{const response=await fetch('/api/payments/'+encodeURIComponent(root.dataset.orderId)+'/attempts',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json','Idempotency-Key':attempt.key},body:JSON.stringify({capability:root.dataset.token,decision:attempt.decision})});const data=await response.json().catch(()=>({message:'Respuesta no disponible. Reintenta para verificar este mismo intento.'}));if(!response.ok)throw new Error(data.message||'No se pudo confirmar el resultado. Reintenta este mismo intento.');if(data.status==='rejected'){attempt=null;try{sessionStorage.removeItem(storageKey);}catch(_){}show('Intento rechazado. El saldo no cambió. Puedes simular otro intento.');}else{const url=new URL('/p/'+encodeURIComponent(root.dataset.orderId)+'/receipt',location.origin);url.searchParams.set('token',root.dataset.token);location.assign(url.pathname+url.search);}}catch(error){show(error.message,true);}finally{pending=false;document.querySelectorAll('.payment-actions button').forEach(b=>b.disabled=false);}}
document.querySelector('#approve')?.addEventListener('click',()=>simulate('approved'));
document.querySelector('#reject')?.addEventListener('click',()=>simulate('rejected'));
document.querySelector('#print')?.addEventListener('click',()=>window.print());
