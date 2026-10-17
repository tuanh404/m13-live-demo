import {request} from './transport.js';
const status=document.getElementById('asset-status'), retry=document.getElementById('asset-retry');
async function load(){
  retry.hidden=true;
  try{
    const result=await request('/web/submission');
    const list=document.getElementById('asset-links');list.replaceChildren();
    for(const [name,url] of Object.entries(result.assets)){
      const li=document.createElement('li'), link=document.createElement('a');
      link.href=url;link.textContent=name;li.append(link);list.append(li);
    }
    status.textContent='Video, slides và thumbnail công khai. Bộ hồ sơ chưa được nộp BTC.';
  }catch(e){status.textContent=e.message;retry.hidden=false;}
}
retry.onclick=load;load();
