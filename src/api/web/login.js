const form=document.getElementById('login-form'),button=document.getElementById('sign-in');
const guest=document.getElementById('guest-demo');
fetch('/auth/session').then(r=>r.json()).then(session=>{
  document.getElementById('guest-intro').hidden=!session.guest_demo;
  if(session.guest_demo)form.hidden=true;
}).catch(()=>{});
guest.onclick=async()=>{
  guest.disabled=true;
  try{
    const response=await fetch('/auth/demo',{method:'POST'}),body=await response.json();
    if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa mở được demo.');
    location.replace('/');
  }catch(e){form.hidden=false;document.getElementById('login-status').textContent=e.message;guest.disabled=false;}
};
form.addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;document.getElementById('login-status').textContent='Đang đăng nhập…';
  try{
    const response=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:document.getElementById('username').value,password:document.getElementById('password').value})});
    const body=await response.json();
    if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Không đăng nhập được.');
    document.getElementById('password').value='';location.replace('/');
  }catch(e){document.getElementById('login-status').textContent=e.message;button.disabled=false;}
});
