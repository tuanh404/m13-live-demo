import {request} from './transport.js';
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const identity = {cvat_origin:params.get('cvat_origin'),task_id:Number(params.get('task_id')),job_id:Number(params.get('job_id'))};
const key = `m13.intake.${identity.cvat_origin}.${identity.task_id}.${identity.job_id}`;
let pending = localStorage.getItem(key), busy = false;
$('job-title').textContent = `Task ${identity.task_id} · Job ${identity.job_id}`;
function show(operation) {
  $('intake-status').textContent = operation.message || operation.status;
  const progress=operation.progress || [0,0];
  $('intake-progress').hidden=!progress[1];
  $('intake-progress').max=progress[1] || 1;$('intake-progress').value=progress[0];
  if(operation.result?.review_url){$('review-job').href=operation.result.review_url;$('review-job').hidden=false;}
}
async function poll() {
  if(!pending)return;
  try {
    const operation=await request(`/intake/requests/${encodeURIComponent(pending)}`);show(operation);
    if(['partial','completed'].includes(operation.status)){
      localStorage.removeItem(key);pending=null;busy=false;$('check-job').disabled=false;return;
    }
    if(operation.status==='failed'){busy=false;$('check-job').disabled=false;$('check-job').textContent='Thử kiểm tra lại';return;}
    busy=true;$('check-job').disabled=true;setTimeout(poll,1000);
  }catch(e){busy=false;$('intake-status').textContent=e.message;$('check-job').disabled=false;}
}
async function boot() {
  try {
    const data=await request('/intake/status?'+new URLSearchParams(identity));
    $('intake-scope').textContent=data.scope;
    $('intake-status').textContent=data.needs_check?'Chưa kiểm hoặc nhãn đã Save thay đổi. Bấm kiểm tra khi sẵn sàng.':'Đã có kết quả phù hợp với nhãn đã Save.';
    if(data.review_url){$('review-job').href=data.review_url;$('review-job').hidden=false;}
    $('check-job').disabled=false;
    if(data.operation&&!pending&&!['partial','completed','failed'].includes(data.operation.status)){
      pending=data.operation.request_id;localStorage.setItem(key,pending);
    }
    if(pending)poll();
  }catch(e){$('intake-status').textContent=e.message;}
}
$('check-job').onclick=async()=>{
  if(busy)return;busy=true;$('check-job').disabled=true;
  pending ||= crypto.randomUUID();localStorage.setItem(key,pending);
  try{show(await request('/intake/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...identity,request_id:pending})}));poll();}
  catch(e){$('intake-status').textContent=e.message;busy=false;$('check-job').disabled=false;}
};
boot();
