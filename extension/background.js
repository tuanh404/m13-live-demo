/* All HTTP calls and the focus-aware review clock live in the MV3 worker. */
// Only the installer sets the connection. Batch/order/guideline live on the server.
const DEFAULTS = {reviewer: "", batch: "", sessionId: "default", order: "priority"};
const connection = fetch(chrome.runtime.getURL("connection.json")).then(reply => reply.json());
let operations = Promise.resolve();
let uiOperations = Promise.resolve();
const panelFocus = new Map();
const serial = (fn) => {
  const next = operations.then(fn, fn);
  operations = next.catch(() => {});
  return next;
};

function localUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["localhost", "127.0.0.1"].includes(url.hostname) || url.username || url.password) {
    throw new Error("Chỉ dùng địa chỉ HTTP localhost hoặc 127.0.0.1 cho API/CVAT local.");
  }
  return url;
}
async function settings() {
  const installed = await connection;
  const stored = (await chrome.storage.local.get("settings")).settings || {};
  const current = await state();
  // Older releases kept the API URL in browser storage. It must no longer shadow
  // the installer-owned connection, but an uncertain write must stay on its origin.
  if (current && !current.apiOrigin && stored.apiUrl) {
    current.apiOrigin = localUrl(stored.apiUrl).origin;
    await persist(current);
  }
  const pinned = (current?.pending || current?.recheckPending) && current.apiOrigin;
  return {...DEFAULTS, ...stored, ...installed, ...(pinned ? {apiUrl: pinned} : {})};
}
async function openGuideline() {
  const workspace = await api("/review/workspace");
  if (!workspace.guideline_url) throw new Error("Chưa có hướng dẫn được người phụ trách thiết lập.");
  const url = localUrl(workspace.guideline_url);
  const tabs = await chrome.tabs.query({url: `${url.origin}/*`});
  const existing = tabs.find(tab => tab.url === url.href);
  if (existing) {
    await chrome.windows.update(existing.windowId, {focused: true});
    await chrome.tabs.update(existing.id, {active: true});
  } else await chrome.tabs.create({url: url.href});
  return {opened: true};
}
async function api(path, method = "GET", body, scope = "") {
  if (!/^\/(intake\/(status|check|requests\/[A-Za-z0-9-]+)|review\/(workspace|start)|health|queue|stats|model|image\/[^/?]+(?:\/(file|saved|recheck))?|rechecks\/[A-Za-z0-9-]+|verdict)(?:\?|$)/.test(path) || path.includes("..")) {
    throw new Error("API path không được phép.");
  }
  if(scope && !/^\/jobs\/[a-f0-9]{32}$/.test(scope))throw new Error("Phạm vi job không hợp lệ.");
  const cfg = await settings();
  const base = localUrl(cfg.apiUrl);
  const target = new URL(scope + path, base.origin);
  if (target.origin !== base.origin) throw new Error("API origin không hợp lệ.");
  let response;
  try {
    response = await fetch(target.href, {method, headers: {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000)});
  } catch {
    const installed = await connection;
    if (base.origin !== localUrl(installed.apiUrl).origin) {
      throw new Error("Còn kết quả đang chờ ở dịch vụ cũ chưa kết nối được. Kết quả vẫn được giữ; nhờ người phụ trách bật lại dịch vụ cũ để xác nhận, không gửi sang dịch vụ khác.");
    }
    throw new Error("Chưa kết nối được dịch vụ kiểm nhãn. Bấm Tải lại; nếu vẫn lỗi, nhờ người phụ trách kiểm tra dịch vụ.");
  }
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { detail = "Không đọc được phản hồi"; }
    const failure = new Error(`HTTP ${response.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    failure.status = response.status;
    throw failure;
  }
  if (path.split("?")[0].endsWith("/file")) {
    const data = new Uint8Array(await response.arrayBuffer());
    if (data.length > 20 * 1024 * 1024) throw new Error("Ảnh lớn hơn 20 MB.");
    let text = "";
    for (let i = 0; i < data.length; i += 8192) text += String.fromCharCode(...data.subarray(i, i + 8192));
    return `data:${response.headers.get("content-type") || "image/jpeg"};base64,${btoa(text)}`;
  }
  return response.json();
}
async function state() { return (await chrome.storage.local.get("review")).review || null; }
async function persist(value) { await chrome.storage.local.set({review: value}); }
function accrue(value) {
  if (value.runningSince !== null) {
    value.elapsedMs = Math.min(86400000, value.elapsedMs + Math.max(0, Date.now() - value.runningSince));
    value.runningSince = null;
  }
}
function frameNumber(url) {
  const raw = url.searchParams.get("frame");
  // CVAT's default frame is zero; the UI removes ?frame=0 after navigation.
  if (raw === null) return 0;
  if (!/^\d+$/.test(raw)) return null;
  const frame = Number(raw);
  return Number.isSafeInteger(frame) ? frame : null;
}
async function refreshClock() {
  const value = await state();
  if (!value) return null;
  accrue(value);
  if (!value.pending && !value.recheckPending) {
    try {
      const [tab, win] = await Promise.all([chrome.tabs.get(value.tabId), chrome.windows.get(value.windowId)]);
      // Frame changes and another focused tab pause the clock even in the same CVAT job.
      const actual = new URL(tab.url), expected = new URL(value.cvatUrl);
      const actualFrame = frameNumber(actual);
      const sameFrame = actual.origin === expected.origin && actual.pathname === expected.pathname &&
        actualFrame !== null && actualFrame === frameNumber(expected);
      if (tab.active && win.focused && tab.status === "complete" && sameFrame && !panelFocus.get(tab.id)) {
        value.runningSince = Date.now();
      }
    } catch { /* Closed CVAT tab: clock remains paused. */ }
  }
  await persist(value);
  return value;
}
function publicClock(value) {
  if (!value) return {active: false};
  return {active: true, imageId: value.detail.image_id, running: value.runningSince !== null,
    seconds: value.elapsedMs / 1000, pending: value.pending, detail: value.detail,
    savedSnapshot: value.savedSnapshot || value.lastSavedSnapshot || null, recheckPending: value.recheckPending || null,
    lastRecheck: value.lastRecheck || null};
}
async function ensureConnection(value) {
  const cfg = await settings();
  const origin = value.apiOrigin || (await state())?.apiOrigin;
  if (origin && localUrl(cfg.apiUrl).origin !== origin) {
    throw new Error("Dịch vụ đã được cập nhật. Chọn lại ảnh trong danh sách trước khi ghi kết quả hoặc kiểm tra nhãn.");
  }
  return cfg;
}
async function jobContext(message, sender) {
  const embedded = new URL(sender.url || chrome.runtime.getURL('')).searchParams.get('embedded') === '1';
  if (!embedded && message.sourceTabId === undefined) return null;
  const id = sender.tab?.id ?? message.sourceTabId;
  if (!Number.isInteger(id)) throw new Error("Chưa nhận diện được job CVAT. Tải lại tab CVAT rồi mở QC.");
  const tab = await chrome.tabs.get(id);
  const url = localUrl(tab.url);
  const match = url.pathname.match(/^\/tasks\/(\d+)\/jobs\/(\d+)\/?$/);
  if (!match) throw new Error("Mở một job CVAT để xem hàng đợi của job đó.");
  return {tabId:id, origin:url.origin, taskId:Number(match[1]), jobId:Number(match[2]), frame:frameNumber(url)};
}
function sameJob(detail, context) {
  if (!context) return true;
  if (!detail?.cvat_url || !detail.cvat) return false;
  return localUrl(detail.cvat_url).origin === context.origin &&
    detail.cvat.task_id === context.taskId && detail.cvat.job_id === context.jobId;
}
async function ensureJob(context) {
  const current = await state();
  if (context && (!sameJob(current?.detail, context) || current?.tabId !== context.tabId)) {
    throw new Error("Chọn ảnh thuộc job đang mở trước khi ghi kết quả hoặc kiểm tra nhãn.");
  }
}
const jobScopes = new Map();
const contextKey = context => `${context.origin}|${context.taskId}|${context.jobId}`;
function intakeQuery(context) {
  return {cvat_origin:context.origin,task_id:context.taskId,job_id:context.jobId};
}
async function intakeStatus(context, fresh=false) {
  if(!context)return {enabled:false};
  const key=contextKey(context), cached=jobScopes.get(key);
  if(!fresh && cached && Date.now()-cached.at<10000)return cached.value;
  try {
    const value={enabled:true,...await api('/intake/status?'+new URLSearchParams(intakeQuery(context)))};
    jobScopes.set(key,{value,at:Date.now()});return value;
  }catch(e){if(e.status===404)return {enabled:false};throw e;}
}
async function scopeFor(context) {
  return (await intakeStatus(context)).api_prefix || '';
}
async function openImage(message, sender) {
  const old = await refreshClock();
  if (old?.pending) throw new Error("Còn verdict chưa xác nhận. Thử gửi lại trước khi đổi ảnh.");
  if (old?.recheckPending) throw new Error("Còn yêu cầu kiểm tra lại chưa xác nhận. Thử lại trước khi đổi ảnh.");
  const cfg = await settings();
  if (!cfg.reviewer.trim()) throw new Error("Nhập tên của bạn rồi bấm Bắt đầu.");
  const context = await jobContext(message, sender);
  const scope = await scopeFor(context);
  const query = new URLSearchParams({queue_id: message.queueId});
  if (cfg.batch && !scope) query.set("batch", cfg.batch);
  const detail = await api(`/image/${encodeURIComponent(message.imageId)}?${query}`, "GET", undefined, scope);
  if (!sameJob(detail, context)) throw new Error("Ảnh không thuộc job đang mở; không chuyển sang task khác.");
  if (!detail.cvat_url) throw new Error("Ảnh chưa được liên kết với CVAT. Nhờ người phụ trách chuẩn bị bộ ảnh.");
  const target = localUrl(detail.cvat_url);
  if (!/^\/tasks\/\d+\/jobs\/\d+$/.test(target.pathname) || !/^\d+$/.test(target.searchParams.get("frame"))) {
    throw new Error("CVAT URL thiếu task/job/frame hợp lệ.");
  }
  const tabs = await chrome.tabs.query({});
  const compatible = tab => {
    try { return new URL(tab.url).origin === target.origin && tab.url.includes("/tasks/"); }
    catch { return false; }
  };
  const matchingJob = tab => compatible(tab) && new URL(tab.url).pathname === target.pathname;
  const existing = tabs.find(tab => tab.id === (context?.tabId ?? sender.tab?.id) && compatible(tab)) ||
    tabs.find(tab => tab.active && matchingJob(tab)) || tabs.find(matchingJob) || tabs.find(compatible);
  const same = existing && new URL(existing.url).pathname === target.pathname && frameNumber(new URL(existing.url)) === frameNumber(target);
  const tab = existing ? await chrome.tabs.update(existing.id, {...(same ? {} : {url: target.href}), active: true}) :
    await chrome.tabs.create({url: target.href, active: true});
  await chrome.windows.update(tab.windowId, {focused: true});
  await persist({tabId: tab.id, windowId: tab.windowId, cvatUrl: target.href, detail,
    apiOrigin: localUrl(cfg.apiUrl).origin, apiScope: scope,
    reviewer: cfg.reviewer.trim(), sessionId: cfg.sessionId, order: cfg.order,
    elapsedMs: 0, runningSince: null, pending: null});
  return publicClock(await refreshClock());
}
async function saveVerdict(message) {
  const value = await refreshClock();
  if (!value) throw new Error("Chọn ảnh và mở CVAT trước khi ghi verdict.");
  await ensureConnection(value);
  if (value.recheckPending) throw new Error("Xác nhận kết quả kiểm tra lại trước khi gửi verdict.");
  if (!value.pending) {
    if (!["error", "false_alarm", "skip"].includes(message.verdict)) throw new Error("Verdict không hợp lệ.");
    accrue(value);
    const d = value.detail;
    value.pending = {request_id: crypto.randomUUID(), image_id: d.image_id, verdict: message.verdict,
      reviewer: value.reviewer, seconds_spent: value.elapsedMs / 1000, note: message.note || null,
      obj_ids: message.objIds || [], batch_id: d.batch_id, queue_id: d.queue_id,
      model_version: d.model_version, rank: d.rank, session_id: value.sessionId, review_order: value.order};
    await persist(value); // Durable retry key BEFORE network: worker suspension cannot duplicate a vote.
  }
  let result;
  try { result = await api("/verdict", "POST", value.pending, value.apiScope || ""); }
  catch (failure) {
    // These responses explicitly reject this immutable submission. A network/5xx
    // failure is uncertain and MUST keep the retry key.
    if ([400, 404, 409, 422].includes(failure.status)) await persist(null);
    throw failure;
  }
  if (result.status !== "saved") throw new Error("API chưa xác nhận đã lưu verdict.");
  await persist(null);
  return result;
}
async function readSaved() {
  const value = await refreshClock();
  if (!value || value.pending || value.recheckPending) throw new Error("Chọn ảnh, xử lý yêu cầu đang chờ trước khi đọc nhãn.");
  const cfg = await ensureConnection(value);
  const query = new URLSearchParams({queue_id: value.detail.queue_id});
  if (cfg.batch && !value.apiScope) query.set("batch", cfg.batch);
  const saved = await api(`/image/${encodeURIComponent(value.detail.image_id)}/saved?${query}`, "GET", undefined, value.apiScope || "");
  value.savedSnapshot = saved;
  await persist(value);
  return saved;
}
async function recheckImage() {
  const value = await refreshClock();
  if (!value || value.pending) throw new Error("Chọn ảnh và xử lý verdict đang chờ trước khi kiểm tra lại.");
  await ensureConnection(value);
  if (!value.recheckPending) {
    if (!value.savedSnapshot?.backend_ready) throw new Error("Đọc nhãn đã Save trước; backend QC cần sẵn sàng.");
    accrue(value);
    value.recheckPending = {request_id: crypto.randomUUID(), queue_id: value.detail.queue_id,
      snapshot_id: value.savedSnapshot.snapshot_id};
    await persist(value);
  }
  let result;
  try { result = await api(`/image/${encodeURIComponent(value.detail.image_id)}/recheck`, "POST", value.recheckPending, value.apiScope || ""); }
  catch (failure) {
    let status;
    try { status = await api(`/rechecks/${value.recheckPending.request_id}`, "GET", undefined, value.apiScope || ""); }
    catch (checkFailure) {
      if (checkFailure.status === 404) { value.recheckPending = null; await persist(value); }
      throw failure;
    }
    if (status.status === "completed") result = status.result;
    else if (status.status === "failed") { value.recheckPending = null; await persist(value); throw failure; }
    else throw failure; // Running/unknown: retain the durable request ID.
  }
  const cfg = await settings();
  const query = new URLSearchParams();
  if (cfg.batch && !value.apiScope) query.set("batch", cfg.batch);
  value.detail = await api(`/image/${encodeURIComponent(value.detail.image_id)}?${query}`, "GET", undefined, value.apiScope || "");
  value.lastRecheck = result;
  value.lastSavedSnapshot = {...value.savedSnapshot, backend_ready:false,
    backend_message:"Snapshot này đã được kiểm tra. Bấm nút QC để đọc nhãn mới nếu bạn sửa tiếp."};
  value.recheckPending = null; value.savedSnapshot = null;
  await persist(value);
  return {result, detail: value.detail, savedSnapshot:value.lastSavedSnapshot};
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  const extensionPage = sender.url?.startsWith(chrome.runtime.getURL(''));
  if (!extensionPage && !["UI_GET", "UI_SET", "PANEL_FOCUS"].includes(message.type)) return false;
  if (["UI_GET", "UI_SET"].includes(message.type)) {
    const task=uiOperations.then(async()=>{
      if(!sender.tab)throw new Error("Thiếu tab CVAT");
      const key=`qc-ui:${sender.tab.id}`;
      if(message.type==='UI_GET')return {...((await chrome.storage.local.get(key))[key]||{open:false,width:420}),tabId:sender.tab.id};
      const value={open:message.value?.open===true,width:Math.max(340,Math.min(650,Number(message.value?.width)||420))};
      await chrome.storage.local.set({[key]:value});return value;
    });
    uiOperations=task.catch(()=>{});
    task.then(value=>sendResponse({ok:true,value}),error=>sendResponse({ok:false,error:error.message}));
    return true;
  }
  serial(async () => {
    switch (message.type) {
      case "PANEL_FOCUS": {
        if (!sender.tab) throw new Error("Thiếu tab CVAT");
        const value=await state();
        if(value?.tabId===sender.tab.id) {accrue(value);await persist(value);}
        panelFocus.set(sender.tab.id,message.focused===true);
        return publicClock(await refreshClock());
      }
      case "SETTINGS": return settings();
      case "START_REVIEW": {
        const current = await state();
        if (current?.pending || current?.recheckPending) throw new Error("Thử gửi lại kết quả đang chờ trước khi đổi người.");
        const cfg = await settings();
        const reviewer = String(message.reviewer || "").trim();
        if (!reviewer || reviewer.length > 100) throw new Error("Nhập tên của bạn (tối đa 100 ký tự).");
        // Keep existing sessions/progress, including legacy installations, when the name is unchanged.
        if (reviewer === cfg.reviewer && !message.fresh) return cfg;
        let attempt = (await chrome.storage.local.get("startAttempt")).startAttempt;
        if (attempt?.reviewer !== reviewer) {
          attempt = {reviewer, request_id: crypto.randomUUID()};
          await chrome.storage.local.set({startAttempt: attempt});
        }
        const session = await api("/review/start", "POST", attempt);
        const next = {...cfg, reviewer: session.reviewer, sessionId: session.session_id,
          batch: session.batch, order: session.order};
        await persist(null);
        await chrome.storage.local.set({settings: next});
        await chrome.storage.local.remove("startAttempt");
        return next;
      }
      case "CVAT_CONTEXT": return jobContext(message, sender);
      case "INTAKE_STATUS": return intakeStatus(await jobContext(message,sender),true);
      case "CHECK_JOB": {
        const context=await jobContext(message,sender);
        if(!context)throw new Error("Mở job CVAT trước khi kiểm tra.");
        const current=await state();
        if(current?.pending||current?.recheckPending)throw new Error("Xác nhận yêu cầu đang chờ trước khi kiểm tra job.");
        const key='intake-attempt:'+contextKey(context);
        let request_id=(await chrome.storage.local.get(key))[key];
        if(!request_id){request_id=crypto.randomUUID();await chrome.storage.local.set({[key]:request_id});}
        const result=await api('/intake/check','POST',{...intakeQuery(context),request_id});
        if(['partial','completed'].includes(result.status)){
          await chrome.storage.local.remove(key);jobScopes.delete(contextKey(context));
        }
        return result;
      }
      case "INTAKE_PROGRESS": {
        const context=await jobContext(message,sender);
        if(!context)throw new Error("Job đã thay đổi.");
        const key='intake-attempt:'+contextKey(context);
        const request_id=(await chrome.storage.local.get(key))[key];
        if(!request_id)throw new Error("Không có yêu cầu của job này.");
        const result=await api('/intake/requests/'+request_id);
        if(['partial','completed'].includes(result.status)){
          await chrome.storage.local.remove(key);jobScopes.delete(contextKey(context));
        }
        return result;
      }
      case "API": {
        const context = await jobContext(message, sender);
        const scope = await scopeFor(context);
        const url = new URL(message.path, 'http://localhost');
        if(scope)url.searchParams.delete('batch');
        if (context && ['/queue','/stats'].includes(url.pathname)) {
          url.searchParams.set('cvat_task_id', context.taskId);
          url.searchParams.set('cvat_job_id', context.jobId);
          url.searchParams.set('cvat_origin', context.origin);
        }
        const result = await api(url.pathname + url.search, "GET", undefined, scope);
        // Older APIs may ignore unknown query parameters: fail closed instead of showing other jobs.
        if (context && url.pathname === '/queue' && result.items.some(row => !sameJob(row, context))) {
          throw new Error("Job này chưa có hàng đợi QC phù hợp. Không dùng dữ liệu từ task khác.");
        }
        return result;
      }
      case "OPEN_GUIDELINE": return openGuideline();
      case "OPEN_IMAGE": return openImage(message, sender);
      case "CLOCK": {
        const value = await refreshClock(), context = await jobContext(message, sender);
        return context && (!sameJob(value?.detail, context) || value?.tabId !== context.tabId)
          ? {active:false} : publicClock(value);
      }
      case "SAVE_VERDICT": await ensureJob(await jobContext(message, sender)); return saveVerdict(message);
      case "READ_SAVED": await ensureJob(await jobContext(message, sender)); return readSaved();
      case "RECHECK": await ensureJob(await jobContext(message, sender)); return recheckImage();
      case "RUN_QC": {
        await ensureJob(await jobContext(message, sender));
        const current=await state();
        if (!current?.recheckPending) {
          const saved=await readSaved();
          if(!saved.backend_ready) throw new Error("Chưa thể kiểm tra lại. Điểm chưa thay đổi; nhờ người phụ trách kiểm tra dịch vụ.");
        }
        return recheckImage();
      }
      default: throw new Error("Thao tác không hỗ trợ.");
    }
  }).then(value => sendResponse({ok: true, value}), error => sendResponse({ok: false, error: error.message}));
  return true;
});
const refresh = () => serial(refreshClock).catch(() => {});
chrome.tabs.onActivated.addListener(refresh);
chrome.tabs.onUpdated.addListener(refresh);
chrome.tabs.onRemoved.addListener(id => {panelFocus.delete(id);chrome.storage.local.remove(`qc-ui:${id}`);refresh();});
chrome.windows.onFocusChanged.addListener(refresh);
chrome.runtime.onStartup.addListener(() => serial(async () => {
  const value = await state();
  if (value) { value.runningSince = null; await persist(value); }
}));
async function toggleFromToolbar(tab) {
  if (!tab.id) return;
  await chrome.tabs.sendMessage(tab.id,{type:'QC_TOGGLE'}).then(reply=>{
    if(!reply?.ok)throw new Error('Không phải job CVAT');
    chrome.action.setBadgeText({tabId:tab.id,text:''});
    chrome.action.setTitle({tabId:tab.id,title:'Mở/đóng QC'});
  }).catch(() => {
    chrome.action.setBadgeText({tabId:tab.id,text:'!'});
    chrome.action.setTitle({tabId:tab.id,title:'Mở một job CVAT rồi bấm QC; reload trang sau khi reload extension.'});
  });
}
chrome.action.onClicked.addListener(toggleFromToolbar);
