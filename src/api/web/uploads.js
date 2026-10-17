import {request} from './transport.js';
const $=id=>document.getElementById(id);
let pending=null;
async function list(){
  $('list-retry').hidden=true;
  try{
    const result=await request('/my-batches/list');
    $('batch-list').replaceChildren();
    for(const item of result.items){
      const li=document.createElement('li'),link=document.createElement('a');
      link.href=item.review_url;link.textContent=`Review bộ ${item.images} ảnh · ${new Date(item.created_at).toLocaleString('vi-VN')}`;
      li.append(link);$('batch-list').append(li);
    }
    $('list-status').textContent=result.items.length?'Mở lại bộ ảnh để tiếp tục; kết luận đã lưu vẫn được giữ.':'Chưa có bộ ảnh nào trong phiên này.';
  }catch(e){$('list-status').textContent=e.message;$('list-retry').hidden=false;}
}
$('list-retry').onclick=list;
$('upload-form').onsubmit=async event=>{
  event.preventDefault();
  const file=$('archive').files[0];
  if(!file)return;
  if(file.size>5242880){$('upload-status').textContent='ZIP vượt5MB. Hãy chọn gói nhỏ hơn.';return;}
  $('upload-check').disabled=true;$('archive').disabled=true;$('uploaded-review').hidden=true;
  $('upload-status').textContent='Đang tải ZIP → đọc ảnh và nhãn → tính nghi vấn và tạo hàng đợi…';
  try{
    pending=await request('/my-batches/upload',{method:'POST',headers:{'Content-Type':'application/zip'},body:file,timeoutMs:120000});
    $('upload-status').textContent=`Đã kiểm một phần ${pending.images} ảnh. ${pending.reused?'Đã mở lại bộ có sẵn; tiến độ được giữ.':'Hàng đợi và nghi vấn đã sẵn sàng.'}`;
    $('uploaded-review').href=pending.review_url;$('uploaded-review').hidden=false;
    await list();
  }catch(e){$('upload-status').textContent=e.message+' Bạn có thể bấm Kiểm tra lại cùng ZIP; không tạo bộ trùng.';}
  finally{$('upload-check').disabled=false;$('archive').disabled=false;}
};
list();
