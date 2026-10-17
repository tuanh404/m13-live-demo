const $=id=>document.getElementById(id);
const form=$('login-form'),button=$('sign-in'),guest=$('guest-demo'),status=$('login-status');
let authenticated=false;
function message(value,error=false){status.textContent=value;status.dataset.tone=error?'error':'';}
async function responseJSON(response){
  const body=await response.json();
  if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Dịch vụ chưa sẵn sàng. Hãy thử lại.');
  return body;
}
async function connect(){
  $('entry-retry').hidden=true;message('Đang kết nối…');
  try{
    const session=await responseJSON(await fetch('/auth/session'));
    authenticated=!!session.authenticated;
    $('upload-entry').hidden=!session.uploads_enabled||(!authenticated&&!session.guest_demo);
    if(!session.enabled){location.replace('/');return;}
    const guestMode=!!session.guest_demo;
    $('guest-intro').hidden=!guestMode;form.hidden=guestMode;
    $('account-toggle').hidden=!guestMode;
    $('entry-description').textContent=guestMode?'Thử một lượt kiểm nhãn, từ ảnh đầu tiên đến thống kê kết quả.':'Dùng tài khoản được cấp để vào không gian review của bạn.';
    message('');
  }catch{
    message('Chưa kết nối được dịch vụ. Bấm thử lại sau một chút.',true);
    $('entry-retry').hidden=false;
  }
}
$('entry-retry').onclick=connect;
$('account-toggle').onclick=()=>{
  form.hidden=!form.hidden;
  $('account-toggle').setAttribute('aria-expanded',String(!form.hidden));
  $('account-toggle').textContent=form.hidden?'Đăng nhập bằng tài khoản được cấp':'Đóng phần đăng nhập';
  if(!form.hidden)$('username').focus();
};
guest.onclick=async()=>{
  guest.disabled=true;message('Đang mở lượt demo…');
  try{
    if(!authenticated)await responseJSON(await fetch('/auth/demo',{method:'POST'}));location.replace('/');
  }catch{
    message('Chưa mở được lượt demo. Bấm Trải nghiệm demo để thử lại.',true);guest.disabled=false;
  }
};
$('my-images').onclick=async()=>{
  $('my-images').disabled=true;message('Đang mở bộ ảnh của bạn…');
  try{
    if(!authenticated)await responseJSON(await fetch('/auth/demo',{method:'POST'}));
    location.assign('/my-batches');
  }catch{message('Chưa mở được phiên. Hãy thử lại.',true);$('my-images').disabled=false;}
};
form.addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;guest.disabled=true;message('Đang đăng nhập…');
  try{
    await responseJSON(await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:$('username').value,password:$('password').value})}));
    $('password').value='';location.replace('/');
  }catch(e){message(e.message,true);button.disabled=false;guest.disabled=false;}
});
// Only offer presentation links when this server has actually published the assets.
fetch('/web/submission').then(responseJSON).then(body=>{
  if(Object.keys(body.assets||{}).length)for(const link of document.querySelectorAll('.entry-resources'))link.hidden=false;
}).catch(()=>{});
connect();
