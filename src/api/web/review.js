import {apiPath, request, scopePrefix, submit} from './transport.js';
import {cvatTools} from './cvat.js';

const $ = id => document.getElementById(id);
const storageKey = scopePrefix ? `m13.web.review.v1:${scopePrefix}` :
  location.pathname === '/pilot/review' ? 'm13.web.pilot.review.v1' : 'm13.web.review.v1';
let saved = {};
try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch { /* recover invalid storage */ }
if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
const state = {
  session: typeof saved.session === 'string' ? saved.session : `demo-${crypto.randomUUID()}`,
  reviewer: typeof saved.reviewer === 'string' ? saved.reviewer : `web-${crypto.randomUUID().slice(0, 8)}`,
  pending: saved.pending || null, current: null, ready: false, busy: false,
  toolBusy: false, editing: false, lastImage: saved.lastImage || null,
  order:'priority', pilot:false, live:false, canCvat:false,
  queue: null, context: null, token: 0, elapsed: 0, running: null, selectedBox: null, picture: null, pictureUrl:null,
};
let retryAction = null;
function persist() {
  localStorage.setItem(storageKey, JSON.stringify({session: state.session, reviewer: state.reviewer,
    pending: state.pending, lastImage: state.lastImage}));
}
function notice(message, tone = '', retry = null) {
  $('notice').textContent = message; $('notice').dataset.tone = tone;
  retryAction = retry; $('retry').hidden = !retry;
  $('discard-rejected').hidden = true;
}
function clock() {
  if (state.running !== null) state.elapsed += (performance.now() - state.running) / 1000;
  state.running = state.ready && !state.busy && !state.toolBusy && !state.editing && !state.pending && !document.hidden && document.hasFocus()
    ? performance.now() : null;
}
function controls() {
  $('verdicts').disabled = !state.ready || state.busy || state.toolBusy || !!state.pending;
  $('note').disabled = state.busy || state.toolBusy || !!state.pending;
  $('new-session').disabled = state.busy || state.toolBusy || !!state.pending;
  $('more').disabled = state.busy || state.toolBusy || !!state.pending || !state.queue;
  if (state.pending || state.busy) {
    for (const id of ['connect-cvat','read-saved','recheck']) $(id).disabled = true;
    $('open-cvat').hidden = true;
  }
  for (const button of $('queue').querySelectorAll('button')) button.disabled = state.busy || state.toolBusy || !!state.pending;
  clock();
}
const cvat = cvatTools({
  lock: value => { state.toolBusy = value; controls(); },
  pause: value => { state.editing = value; clock(); },
  reload: async image => {
    state.lastImage = image; history.replaceState(null, '', `?image=${encodeURIComponent(image)}`);
    await load();
  },
});
function text(tag, value, className) {
  const el = document.createElement(tag); el.textContent = value;
  if (className) el.className = className;
  return el;
}
function reason(value) {
  // Same rule-ID emphasis as the existing side panel, without interpreting source text as HTML.
  const li = document.createElement('li');
  String(value).split(/(\[R\d+\])/g).forEach(part => li.append(text(/^\[R\d+\]$/.test(part) ? 'strong' : 'span', part)));
  return li;
}
function readableReason(value, labels) {
  // The pipeline's "car #26" uses object IDs, not the box number in this image.
  const escape = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  let result = value;
  for (const lb of labels) {
    const pattern = new RegExp(`${escape(lb.category)} #${escape(lb.obj_id)}(?![\\w.-])`, 'g');
    result = result.replace(pattern, () => `Box ${lb.number} · ${lb.category}`);
  }
  return result;
}
function query() {
  return new URLSearchParams({reviewer: state.reviewer, session_id: state.session, order: state.order});
}
function renderQueue() {
  $('queue').replaceChildren();
  for (const item of state.queue.items) {
    const button = document.createElement('button'); button.type = 'button';
    button.dataset.image = item.image_id;
    button.setAttribute('aria-current', String(item.image_id === state.current?.image_id));
    button.append(text('span', `#${item.rank}`), text('span', `${item.risk_score}/100`, 'queue-score'),
      text('span', item.image_id, 'queue-name'));
    button.addEventListener('click', () => {
      if (state.current?.image_id === item.image_id) return;
      if ($('note').value && !confirm('Đổi ảnh sẽ bỏ ghi chú chưa lưu. Tiếp tục?')) return;
      select(item);
    });
    $('queue').append(button);
  }
  $('more').hidden = state.queue.items.length >= state.queue.remaining;
  $('progress').textContent = `${state.queue.reviewed}/${state.queue.total} ảnh đã kết luận · ${state.queue.remaining} còn lại`;
  $('progress-bar').max = state.queue.total || 1; $('progress-bar').value = state.queue.reviewed;
  controls();
}
function renderStats(stats) {
  const v = stats.latest.verdicts;
  $('stats').textContent = `${v.error} lỗi thật · ${v.false_alarm} bot nhầm · ${v.skip} bỏ qua. ` +
    (stats.latest.error_rate === null ? 'Chưa có kết luận đủ để tính tỷ lệ.' :
      `Tỷ lệ lỗi trong kết luận hợp lệ: ${(stats.latest.error_rate * 100).toFixed(0)}%.`);
}
function draw() {
  const canvas = $('overlay'), img = state.picture || $('photo');
  const ctx = canvas.getContext('2d');
  canvas.width = img.naturalWidth || 1280; canvas.height = img.naturalHeight || 720;
  if (!state.ready || $('photo').hidden || !state.current) return;
  const labels = state.current.annotations;
  function box(coords, title, color, dashed = false, width = 3) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dashed ? [10, 7] : []);
    ctx.strokeRect(coords[0], coords[1], coords[2] - coords[0], coords[3] - coords[1]);
    if (!title) return;
    ctx.setLineDash([]); ctx.font = '18px system-ui';
    const y = Math.max(22, coords[1] - 5), x = Math.max(0, coords[0]);
    ctx.fillStyle = color; ctx.fillRect(x, y - 21, ctx.measureText(title).width + 12, 25);
    ctx.fillStyle = 'white'; ctx.fillText(title, x + 6, y - 2);
  }
  if ($('show-labels').checked) for (const lb of labels) {
    const title = $('show-box-names').checked || state.selectedBox === lb.number
      ? `Box ${lb.number} · ${lb.category}` : '';
    box(lb.box, title, '#1667bb', false, state.selectedBox === lb.number ? 7 : 3);
  }
  if ($('show-evidence').checked) state.current.evidence.forEach((b, i) => {
    const title = !b.secondary && i < 3 ? `Nghi vấn ${i + 1}` : '';
    box(b.box, title, '#b64b08', !!b.secondary, 4);
  });
}
async function select(item) {
  const token = ++state.token;
  state.ready = false; clock(); state.current = null; state.elapsed = 0; state.selectedBox = null;
  state.picture = null;
  if(state.pictureUrl){URL.revokeObjectURL(state.pictureUrl);state.pictureUrl=null;}
  state.editing = false;
  state.lastImage = item.image_id; persist();
  history.replaceState(null, '', `?image=${encodeURIComponent(item.image_id)}`);
  cvat.reset(null);
  $('note').value = ''; $('photo').hidden = true; $('photo').removeAttribute('src');
  $('image-placeholder').hidden = false; $('image-placeholder').textContent = 'Đang tải ảnh và snapshot nhãn…';
  $('image-title').textContent = item.image_id; $('position').textContent = `Hạng ${item.rank}`;
  $('risk').textContent = '—'; $('reasons').replaceChildren(); $('evidence-list').replaceChildren();
  $('label-list').replaceChildren(); draw(); controls();
  notice('Đang tải ảnh và nghi vấn…');
  try {
    const detail = await request(`/web/review/${encodeURIComponent(item.image_id)}?queue_id=${state.queue.queue_id}`);
    if (token !== state.token) return;
    state.current = detail;
    $('cvat-tools').hidden=!state.canCvat||!detail.cvat_mapped;
    $('risk').textContent = detail.model_version.startsWith('manual-unscored') ? 'Chưa chấm' : detail.risk_score;
    const reasons = detail.reasons.length ? detail.display_reasons || detail.reasons :
      ['Chưa có cảnh báo từ các phép kiểm đang bật. Điều này không bảo đảm nhãn đúng.'];
    $('reasons').replaceChildren(...reasons.map(value => reason(readableReason(value, detail.annotations))));
    detail.evidence.forEach((b, index) => {
      const match = detail.annotations.find(lb => lb.obj_id === b.obj_id);
      const label = b.secondary ? 'Detector tham chiếu' : match ? `Box ${match.number} · ${match.category}` : 'Vùng nghi vấn';
      $('evidence-list').append(text('li', `${index + 1}. ${label}: ${detail.display_issues?.[index] || b.note || b.issue || 'Cần đối chiếu ảnh'}`));
    });
    $('evidence-details').hidden=!detail.evidence.length;
    $('evidence-details').open=false;
    detail.annotations.forEach(lb => {
      const li = document.createElement('li'), button = document.createElement('button');
      button.textContent = `Box ${lb.number} · ${lb.category} (${lb.box.map(n => Math.round(n)).join(', ')})`;
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => {
        state.selectedBox = lb.number;
        for (const b of $('label-list').querySelectorAll('button')) b.setAttribute('aria-pressed', String(b === button));
        draw();
      });
      li.append(button); $('label-list').append(li);
    });
    if (!detail.annotations.length) $('label-list').append(text('li', detail.labels_verified ?
      'Snapshot không có box 2D.' : 'Chưa có snapshot nhãn được xác minh.'));
    $('warnings').textContent = detail.warnings.join(' · ');
    $('image-caption').textContent = 'Nhãn của lần kiểm tra này. ' +
      (state.canCvat&&detail.cvat_mapped?'Thay đổi trong CVAT chỉ được cập nhật sau Save và kiểm tra lại. ':'')+
      (detail.evidence.length ? 'Màu cam là nghi vấn tự động, chưa phải lỗi được xác nhận.' : 'Chưa có box nghi vấn.');
    // A protected pilot image needs the same session header as API requests.
    const objectURL=state.pilot?URL.createObjectURL(await request(detail.image_url,{responseType:'blob'})):null;
    const picture = await new Promise((resolve, reject) => {
      const img = new Image();
      const timeout = setTimeout(() => {
        img.onload = img.onerror = null; img.src = '';
        reject(new Error('Ảnh tải quá lâu. Kiểm kết nối rồi thử lại.'));
      }, 20000);
      img.onload = () => { clearTimeout(timeout); resolve(img); };
      img.onerror = () => { clearTimeout(timeout); reject(new Error('Không tải được ảnh. Kiểm thư mục ảnh rồi thử lại.')); };
      img.src = objectURL || apiPath(detail.image_url);
    }).catch(error=>{if(objectURL)URL.revokeObjectURL(objectURL);throw error;});
    if (token !== state.token) {if(objectURL)URL.revokeObjectURL(objectURL);return;}
    state.pictureUrl=objectURL;
    state.picture = picture; $('photo').src = picture.src;
    $('photo').alt = `Ảnh ${detail.image_id}; nhãn snapshot màu xanh, vùng nghi vấn màu cam.`;
    $('photo').hidden = false; $('image-placeholder').hidden = true;
    $('image-stage').style.aspectRatio = `${picture.naturalWidth}/${picture.naturalHeight}`;
    state.ready = true; renderQueue(); draw();
    cvat.reset(detail);
    notice('Đối chiếu ảnh và nghi vấn, rồi chọn một kết luận (phím 1 / 2 / 3).');
  } catch (error) {
    if (token !== state.token) return;
    state.ready = false; controls(); $('image-placeholder').textContent = 'Chưa tải được dữ liệu để review.';
    notice(error.message, 'error', () => select(item));
  }
}
async function load(message = '') {
  state.ready = false; ++state.token; state.current = null; controls();
  $('more').disabled = true;
  $('photo').hidden = true; draw(); $('image-placeholder').hidden = false;
  $('image-placeholder').textContent = 'Đang tải hàng đợi…';
  try {
    const context = await request('/web/context');
    const params = query();
    const [queue, stats] = await Promise.all([
      request(`/queue?${params}&limit=50`), request(`/stats?${params}&queue_id=${context.queue_id}`),
    ]);
    if (context.queue_id !== queue.queue_id || context.queue_id !== stats.queue_id) {
      throw new Error('Snapshot vừa thay đổi. Tải lại để xem dữ liệu đồng nhất.');
    }
    state.context = context; state.queue = queue;
    $('more').disabled = false;
    $('connection').textContent = 'Sẵn sàng';
    $('data-kind').textContent = scopePrefix.startsWith('/batches/') ? 'Ảnh của bạn · Kiểm một phần' : context.fixture ? 'FIXTURE · Ảnh tổng hợp, không phải BDD thật' :
      context.data_purpose === 'development' ? 'Dữ liệu phát triển · kiểm các tín hiệu được cấu hình' : 'Ảnh BDD100K · lượt trải nghiệm';
    $('data-attribution').hidden=context.fixture||context.data_purpose!=='real';
    renderStats(stats); renderQueue();
    $('pilot-feedback').hidden = !state.pilot || queue.remaining !== 0;
    if (queue.items.length) {
      const requested = new URLSearchParams(location.search).get('image') || state.lastImage;
      await select(queue.items.find(item => item.image_id === requested) || queue.items[0]);
    }
    else {
      $('image-title').textContent = queue.total ? 'Đã hoàn thành lượt review' : 'Chưa có batch để review';
      $('image-placeholder').textContent = queue.total ? 'Tất cả ảnh trong snapshot này đã có kết luận.' : 'Người vận hành cần cấu hình batch demo.';
      $('risk').textContent = '—'; $('reasons').replaceChildren(); $('evidence-list').replaceChildren();
      $('label-list').replaceChildren(); $('note').value = ''; $('position').textContent = '';
      notice(queue.total ? 'Đã hoàn thành! Xem thống kê lượt này ở bên phải.' : 'Batch hiện chưa có ảnh.', 'success');
    }
    if (message) notice(message + (queue.remaining ? ' Đang xem ảnh tiếp theo.' : ' Đã hoàn thành lượt review.'), 'success');
  } catch (error) {
    $('connection').textContent = 'Chưa tải được dữ liệu'; controls();
    notice(error.message, 'error', () => load());
  }
}
async function sendPending() {
  if (state.busy || !state.pending) return;
  state.busy = true; controls(); notice('Đang lưu kết luận… Không cần bấm lại.');
  try {
    await submit(state.pending);
    state.pending = null; persist(); state.busy = false;
    await load('Đã lưu kết luận vào lịch sử.');
  } catch (error) {
    state.busy = false; state.ready = false; controls();
    notice(`Chưa nhận xác nhận lưu: ${error.message}. Thử lại giữ nguyên mã gửi để tránh lưu trùng.`, 'error', sendPending);
    if ([409, 422].includes(error.status)) {
      notice(`API từ chối lần gửi này: ${error.message}. Bạn có thể tải queue mới để đối chiếu lại.`, 'error', sendPending);
      $('discard-rejected').hidden = false;
    }
  }
}
function verdict(value) {
  if (!state.ready || state.busy || state.toolBusy || state.pending) return;
  clock();
  const item = state.current;
  state.pending = {request_id: crypto.randomUUID(), image_id: item.image_id, verdict: value,
    reviewer: state.reviewer, session_id: state.session, review_order: state.order,
    queue_id: item.queue_id, model_version: item.model_version, rank: item.rank,
    seconds_spent: Math.min(86400, Math.max(0, state.elapsed)), note: $('note').value || null,
    obj_ids: [...new Set(item.evidence.filter(b => !b.secondary && b.obj_id).map(b => b.obj_id))]};
  try { persist(); } catch {
    state.pending = null;
    notice('Trình duyệt không lưu được mã gửi. Cho phép lưu dữ liệu trang rồi thử lại.', 'error'); return;
  }
  sendPending();
}
$('retry').addEventListener('click', () => retryAction?.());
$('discard-rejected').addEventListener('click', () => {
  if (state.pending && confirm('API đã từ chối lần gửi này. Bỏ yêu cầu bị từ chối và đối chiếu queue mới?')) {
    state.pending = null; persist(); load();
  }
});
for (const id of ['show-labels', 'show-evidence', 'show-box-names']) $(id).addEventListener('change', draw);
for (const button of document.querySelectorAll('[data-verdict]')) {
  button.addEventListener('click', () => verdict(button.dataset.verdict));
}
document.addEventListener('keydown', event => {
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
      event.target.closest('input,textarea,select,[contenteditable=true]')) return;
  const value = {'1': 'error', '2': 'false_alarm', '3': 'skip'}[event.key];
  if (value) { event.preventDefault(); verdict(value); }
});
for (const target of ['focus', 'blur']) window.addEventListener(target, clock);
document.addEventListener('visibilitychange', clock);
$('more').addEventListener('click', async () => {
  const queue = state.queue;
  $('more').disabled = true;
  try {
    const page = await request(`/queue?${query()}&offset=${queue.items.length}&limit=50`);
    if (state.queue !== queue) return;
    if (page.queue_id !== queue.queue_id) throw new Error('Queue đã đổi. Tải lại trang.');
    state.queue.items.push(...page.items); renderQueue();
  } catch (error) { notice(error.message, 'error', () => load()); }
  finally { $('more').disabled = false; }
});
$('new-session').addEventListener('click', async () => {
  if(state.live){
    try{await request('/auth/new-review',{method:'POST'});state.pending=null;persist();location.reload();}
    catch(e){notice(e.message,'error');}return;
  }
  if (confirm('Bắt đầu lượt demo mới? Lịch sử lượt trước vẫn được giữ.')) {
    state.session = `demo-${crypto.randomUUID()}`; state.lastImage = null;
    history.replaceState(null, '', location.pathname); persist(); load();
  }
});
async function boot() {
  try {
    if(scopePrefix){
      document.querySelector('.brand').href=location.pathname;
      for(const link of document.querySelectorAll('a[href="/results"],a[href="/pilot"]'))link.hidden=true;
    }
    const auth=await request('/auth/session'+(scopePrefix.startsWith('/batches/')?'?upload_batch='+scopePrefix.split('/')[2]:''));
    if(auth.uploads_enabled){
      const link=document.createElement('a');link.href='/my-batches';link.textContent='Bộ ảnh của tôi';
      if(!document.querySelector('a[data-upload-nav]')){link.dataset.uploadNav='true';document.querySelector('.topbar').append(link);}
    }
    if(scopePrefix.startsWith('/batches/')){
      $('upload-review-scope').hidden=false;$('new-session').hidden=true;
    }
    state.canCvat=!auth.enabled||auth.identity?.role==='admin';
    if(auth.enabled){
      if(!auth.authenticated){location.replace('/login');return;}
      const identity=auth.identity;
      if(state.session!==identity.session_id){state.pending=null;state.lastImage=null;}
      state.reviewer=identity.reviewer;state.session=identity.session_id;state.live=true;
      $('logout').hidden=false;
      if(identity.role==='demo'){
        $('cvat-tools').hidden=true;
        for(const link of document.querySelectorAll('a[href="/pilot"]'))link.hidden=true;
      }
    }
    const mode=auth.enabled&&auth.identity.role==='demo'?{configured:false}:await request('/pilot/status');
    $('pilot-link').hidden=!!scopePrefix||!mode.configured;
    if(!scopePrefix)request('/web/results').then(()=>{$('results-link').hidden=false;}).catch(()=>{});
    request('/web/submission').then(()=>{$('submission-link').hidden=false;}).catch(()=>{});
    if (mode.configured && !mode.session) { location.replace('/pilot');return; }
    if (mode.configured) {
      if (location.pathname !== '/pilot/review') { location.replace('/pilot/review');return; }
      state.reviewer=mode.session.reviewer;state.session=mode.session.session_id;
      state.order=mode.session.order;state.pilot=true;state.canCvat=false;
      $('pilot-instructions').hidden=false;$('new-session').hidden=true;$('cvat-tools').hidden=true;
      document.querySelector('.queue-pane h1').textContent=state.order==='file'?'Thứ tự file':'Hàng đợi ưu tiên';
    }
    persist();
    if (state.pending) {
      controls();notice('Có kết luận chưa nhận xác nhận ở lần trước. Bấm thử lại để hoàn tất, không tạo bản ghi trùng.','error',sendPending);
    }else load();
  } catch(e){notice(e.message,'error',boot);}
}
$('logout').addEventListener('click',async()=>{
  try{await request('/auth/logout',{method:'POST'});localStorage.removeItem(storageKey);location.assign('/login');}
  catch(e){notice(e.message,'error');}
});
let feedbackRequest=null;
$('pilot-feedback').addEventListener('submit',async event=>{
  event.preventDefault();
  if (!$('feedback-clarity').value) { $('feedback-status').textContent='Chọn mức độ rõ1–5.';return; }
  feedbackRequest ||= crypto.randomUUID();$('feedback-send').disabled=true;
  try{
    await request('/pilot/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      request_id:feedbackRequest,clarity:Number($('feedback-clarity').value),confusing:$('feedback-text').value})});
    $('feedback-status').textContent='Đã lưu phản hồi. Cảm ơn bạn đã hoàn thành lượt pilot.';
  }catch(e){$('feedback-status').textContent=e.message;$('feedback-send').disabled=false;}
});
try {
  persist();
  boot();
} catch {
  notice('Cần cho phép lưu dữ liệu trang (localStorage) để giữ phiên và retry an toàn.', 'error');
}
