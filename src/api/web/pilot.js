import {request} from './transport.js';
const $=id=>document.getElementById(id);
async function load(){
  try{
    const status=await request('/pilot/status');
    $('pilot-status').textContent=status.message+(status.configured?` · ${status.n_images}ảnh · lượt ${status.order}.`:'');
    $('pilot-submit').disabled=!status.eligible||!!status.session;
    $('pilot-resume').hidden=!status.session;
    $('pilot-register').hidden=!!status.session;
  }catch(e){$('pilot-status').textContent=e.message;}
}
$('pilot-register').addEventListener('submit',async event=>{
  event.preventDefault();$('pilot-submit').disabled=true;$('pilot-status').textContent='Đang xác minh và freeze phiên…';
  try{
    let requestId=localStorage.getItem('m13.pilot.registration.request.v1');
    if(!requestId){requestId=crypto.randomUUID();localStorage.setItem('m13.pilot.registration.request.v1',requestId);}
    const result=await request('/pilot/register',{timeoutMs:120000,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,
      reviewer:$('pilot-name').value,is_human:$('human').checked,unseen_batch:$('unseen').checked,follow_protocol:$('protocol').checked})});
    localStorage.setItem('m13.pilot.access.v1',result.token);location.assign(result.url);
  }catch(e){$('pilot-status').textContent=e.message;$('pilot-submit').disabled=false;}
});load();
