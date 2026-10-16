const $ = id => document.getElementById(id);
let cfg, items = [], selected = null, loading = false, saving = false, pending = null;
let cursor = 0, generation = 0, selectionGeneration = 0;
let savedSnapshot = null, recheckPending = null, lastRecheck = null, health = null;
const embedded = new URL(location.href).searchParams.get("embedded") === "1";
function hostMessage(type, extra={}) {
  if(embedded) parent.postMessage({type,...extra}, "*");
}
$("identity-toggle").onclick = () => {
  $("identity").hidden=!$("identity").hidden;
  if(!$("identity").hidden) { $("identity").scrollIntoView({block:"start"}); $("reviewer").focus(); }
};
document.addEventListener("pointerdown",()=>hostMessage("QC_FOCUS",{focused:true}));
document.addEventListener("focusin",()=>hostMessage("QC_FOCUS",{focused:true}));
window.addEventListener("message",event=>{
  if(event.source!==parent || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(event.origin))return;
  if(event.data?.type==="QC_VISIBILITY") {
    document.body.inert=!event.data.visible;
    if(!event.data.visible)hostMessage("QC_FOCUS",{focused:false});
  }
});
hostMessage("QC_READY");
async function worker(message) {
  if (embedded) message = {...message, sourceTabId:Number(new URL(location.href).searchParams.get('tabId'))};
  const reply = await chrome.runtime.sendMessage(message);
  if (!reply?.ok) throw new Error(reply?.error || "Service worker không phản hồi.");
  return reply.value;
}
$("open-guideline").onclick = async () => {
  $("open-guideline").disabled = true;
  try { await worker({type: "OPEN_GUIDELINE"}); error(""); }
  catch (err) { error(err.message); }
  finally { $("open-guideline").disabled = false; }
};
function error(message) {
  $("error").hidden = !message;
  $("error").textContent = /^HTTP \d+:/.test(message || "")
    ? "Chưa thực hiện được thao tác. Bấm thử lại; nếu vẫn lỗi, nhờ người phụ trách kiểm tra dịch vụ."
    : message || "";
}
function reasonNode(reason) {
  const li = document.createElement("li");
  const parts = reason.split(/(\[[RV]\d+\])/g);
  for (const part of parts) {
    if (/^\[[RV]\d+\]$/.test(part)) { const strong = document.createElement("strong"); strong.textContent = part; li.append(strong); }
    else li.append(document.createTextNode(part));
  }
  return li;
}
function query(offset = 0) {
  const params = new URLSearchParams({limit: "50", offset: String(offset), reviewer: cfg.reviewer,
    session_id: cfg.sessionId, order: cfg.order});
  if (cfg.batch) params.set("batch", cfg.batch);
  return params;
}
function actions() {
  $("identity-toggle").disabled = saving || !!pending || !!recheckPending;
  $("new-review").disabled = !cfg?.reviewer || saving || !!pending || !!recheckPending;
  $("review-footer").hidden = !selected;
  document.querySelectorAll("[data-verdict]").forEach(button => button.disabled = saving || !selected || !!pending || !!recheckPending);
  $("retry").hidden = !pending;
  $("retry").disabled = saving;
  $("read-saved").disabled = saving || !selected || !!pending || !!recheckPending;
  $("recheck").disabled = saving || !selected || !!pending || (!recheckPending && !savedSnapshot?.backend_ready);
  $("recheck").textContent = recheckPending ? "Thử kiểm tra lại" : "Kiểm tra nhãn vừa đọc";
  $("run-qc").disabled = saving || !selected || !!pending;
  $("run-qc").textContent = saving ? "Đang xử lý…" : recheckPending ? "Thử lại yêu cầu QC đang chờ" : "▶ Kiểm tra nhãn đã lưu";
  const at=items.findIndex(row=>row.image_id===selected?.image_id);
  $("previous").disabled=saving||!!pending||!!recheckPending||at<=0;
  $("next").disabled=saving||!!pending||!!recheckPending||at<0||at>=items.length-1;
}
function renderQueue() {
  $("queue").replaceChildren();
  for (const row of items) {
    const li = document.createElement("li"), button = document.createElement("button");
    button.className = `row${selected?.image_id === row.image_id ? " active" : ""}`;
    button.dataset.imageId = row.image_id;
    button.disabled = saving || !!pending || !!recheckPending;
    const title = document.createElement("span");
    const score = row.model_version?.startsWith("manual-unscored-")
      ? "Chưa chấm QC" : `${Number(row.risk_score).toFixed(1)} điểm`;
    title.className = "rank"; title.textContent = `#${row.rank} · ${score} · ${row.image_id}`;
    button.append(title);
    const reasons = document.createElement("ul");
    (row.display_reasons || row.reasons || []).slice(0, 3).forEach(reason => reasons.append(reasonNode(reason)));
    button.append(reasons); button.addEventListener("click", () => selectImage(row));
    li.append(button); $("queue").append(li);
  }
}
async function loadQueue(append = false) {
  if (loading) return;
  loading = true; const mine = ++generation;
  $("status").textContent = "Đang tải hàng đợi…"; error("");
  try {
    const intake=await worker({type:'INTAKE_STATUS'});
    $("check-job").hidden=!intake.enabled;
    $("check-job").disabled=!!pending||!!recheckPending;
    $("job-check-status").hidden=!intake.enabled;
    if(intake.enabled)$("job-check-status").textContent=intake.needs_check
      ?'Job chưa kiểm hoặc nhãn đã Save thay đổi. Bấm Kiểm tra job này khi sẵn sàng.':intake.scope;
    const result = await worker({type: "API", path: `/queue?${query(append ? cursor : 0)}`});
    if (mine !== generation) return;
    items = append ? [...items, ...result.items] : result.items;
    cursor = items.length;
    $("count").textContent = `${result.reviewed}/${result.total} ảnh đã xem`;
    $("queue-section").querySelector("summary").textContent=cfg.order==="file"?"Hàng đợi theo tên file":"Hàng đợi ưu tiên";
    try {health=await worker({type:"API",path:`/health${cfg.batch?`?batch=${encodeURIComponent(cfg.batch)}`:""}`});}catch {health=null;}
    $("data-kind").hidden=health?.data_purpose!=="development" && !result.model_version?.includes("fixture");
    $("data-kind").textContent="Bộ ảnh thử nghiệm · chưa dùng để đánh giá chất lượng thực tế";
    const context = await worker({type:'CVAT_CONTEXT'});
    $("job-context").textContent = context ? `Task ${context.taskId} · Job ${context.jobId}` : "Hàng đợi đã được chuẩn bị";
    $("data-kind").hidden ||= result.total===0;
    $("status").textContent = context && !result.total ? "Job này chưa có hàng đợi QC được chuẩn bị. Nhờ người phụ trách liên kết bộ ảnh; không sử dụng fixture thay thế." :
      result.warnings?.length ? "Một số dữ liệu chưa sẵn sàng. Nhờ người phụ trách kiểm tra bộ ảnh." :
      result.remaining ? "Chọn một ảnh để xem nghi vấn." : "Bạn đã xem hết ảnh trong lượt này.";
    $("more").hidden = cursor >= result.remaining;
    renderQueue(); actions();
    await loadStats();
  } catch (err) {
    if (!append) {items=[];cursor=0;$("count").textContent='';$("more").hidden=true;renderQueue();}
    error(err.message); $("status").textContent = "Chưa tải được hàng đợi của job này.";
  }
  finally { loading = false; }
}
$("check-job").onclick=async()=>{
  if(saving||pending||recheckPending)return;
  saving=true;$("check-job").disabled=true;actions();
  try{
    let operation=await worker({type:'CHECK_JOB'});
    while(true){
      $("job-check-status").hidden=false;
      $("job-check-status").textContent=operation.message+(operation.progress?.[1]?` (${operation.progress[0]}/${operation.progress[1]} ảnh)`:"");
      if(['partial','completed','failed'].includes(operation.status))break;
      await new Promise(resolve=>setTimeout(resolve,1000));
      operation=await worker({type:'INTAKE_PROGRESS'});
    }
    if(operation.status==='failed')throw new Error(operation.message);
    selected=null;$("selected").hidden=true;await loadQueue();
  }catch(e){error(e.message);}
  finally{saving=false;$("check-job").disabled=false;actions();renderQueue();}
};
async function loadStats() {
  const params = query(); params.delete("offset"); params.delete("limit");
  const result = await worker({type: "API", path: `/stats?${params}`});
  const rate = result.latest.error_rate === null ? "chưa có" : `${(100 * result.latest.error_rate).toFixed(1)}%`;
  $("stats").textContent = `${result.reviewed_images} ảnh · ${result.review_events} lượt · lỗi thật ${rate} · ${result.history.seconds_spent.toFixed(1)} giây`;
}
async function showDetail(detail) {
  selected = detail; $("selected").hidden = false;
  $("image-title").textContent = `Ảnh #${detail.rank} · ${detail.image_id}`;
  const unscored=detail.model_version?.startsWith("manual-unscored-");
  $("risk-score").textContent=unscored?"Chưa chấm":`${Number(detail.risk_score).toFixed(1)}/100`;
  $("result").dataset.level=unscored?"unscored":detail.risk_score>0?"warning":"clear";
  $("result-summary").textContent=unscored?"Chưa có kết quả kiểm tra":detail.risk_score>0?"Có dấu hiệu cần đối chiếu với ảnh":"Chưa có cảnh báo từ các phép kiểm đang bật";
  if(lastRecheck?.queue_id===detail.queue_id) $("result-summary").textContent +=
    ` · Vừa kiểm tra: ${lastRecheck.risk_before.toFixed(1)} → ${lastRecheck.risk_after.toFixed(1)} điểm.`;
  $("reasons").replaceChildren(...(detail.display_reasons || detail.reasons).slice(0, 3).map(reasonNode));
  $("evidence").replaceChildren();
  $("evidence-count").textContent=`(${(detail.evidence || []).length})`;
  $("evidence-details").hidden=!(detail.evidence || []).length;
  for (const [index, box] of (detail.evidence || []).entries()) {
    const li = document.createElement("li");
    const check = document.createElement("input"); check.type = "checkbox"; check.value = box.obj_id || "";
    check.style.width = "auto"; check.dataset.objId = "true";
    check.disabled = !box.obj_id;
    const savedBox=savedSnapshot?.boxes.find(b=>String(b.obj_id)===String(box.obj_id));
    const number=savedBox?savedSnapshot.boxes.indexOf(savedBox)+1:null;
    const label=document.createElement("label");
    const chip=document.createElement("span"); chip.className=`chip ${box.severity==="error"?"error":"review"}`;
    chip.textContent=`${index+1}`; chip.title=box.severity==="error"?"Nghi vấn ưu tiên cao":"Cần review";
    label.append(check,chip,document.createTextNode(`${number?`Box ${number} · ${savedBox.category}`:"Nghi vấn"} · ${detail.display_issues?.[index] || box.issue || box.note || "Vùng cần đối chiếu"}`));
    const view=document.createElement("button"); view.type="button"; view.className="view-box"; view.textContent="Xem";
    view.title="Hiện box này trên CVAT"; view.hidden=!embedded;
    view.onclick=()=>hostMessage("QC_FOCUS_BOX",{index});
    li.append(label,view);
    $("evidence").append(li);
  }
  $("image").hidden = true; $("boxes").hidden = true; $("image-error").hidden = true;
  if (detail.image_available) {
    const data = await worker({type: "API", path: detail.image_url});
    if (selected?.image_id !== detail.image_id) return;
    const img = $("image");
    img.onload = () => {
      if (selected?.image_id !== detail.image_id) return;
      img.hidden = false;
      const canvas = $("boxes"); canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      canvas.hidden = false;
      const ctx = canvas.getContext("2d");
      ctx.lineWidth = Math.max(2, img.naturalWidth / 350); ctx.font = `${Math.max(14, img.naturalWidth / 70)}px sans-serif`;
      for (const [index, evidence] of (detail.evidence || []).entries()) {
        const [x1, y1, x2, y2] = evidence.box;
        ctx.strokeStyle = ctx.fillStyle = evidence.severity === "error" ? "#ff1f1f" : "#ffd000";
        ctx.setLineDash(evidence.obj_id == null ? [9, 5] : []);
        ctx.strokeRect(x1, y1, x2-x1, y2-y1);
        ctx.fillText(String(index + 1), x1 + 2, Math.max(14, y1 - 4));
      }
    };
    img.onerror = () => { $("image-error").hidden = false; $("image-error").textContent = "Không đọc được nội dung ảnh."; };
    img.src = data;
  } else { $("image-error").hidden = false; $("image-error").textContent = "Ảnh chưa có trong images_dir; xem ảnh trong CVAT."; }
  actions(); renderQueue();
}
async function selectImage(row) {
  if (saving || pending || recheckPending) return;
  error(""); const mine = ++selectionGeneration;
  try {
    const clock = await worker({type: "OPEN_IMAGE", imageId: row.image_id, queueId: row.queue_id});
    if (mine !== selectionGeneration) return;
    pending = clock.pending; lastRecheck=clock.lastRecheck; $("note").value = "";
    savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending;
    showSaved();
    await showDetail(clock.detail);
    $("selected").scrollIntoView({block:"start"});
    await updateClock();
  } catch (err) { error(err.message); }
}
async function updateClock() {
  try {
    const clock = await worker({type: "CLOCK"});
    if (!clock.active) {
      pending = null; selected = null; savedSnapshot = null; recheckPending = null; $("selected").hidden = true; actions();
      return;
    }
    pending = clock.pending;
    savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending;
    lastRecheck=clock.lastRecheck;
    if(selected?.image_id!==clock.detail.image_id || selected?.queue_id!==clock.detail.queue_id) await showDetail(clock.detail);
    $("timer").textContent = `${clock.seconds.toFixed(1)} giây · ${pending ? "chờ lưu verdict" : recheckPending ? "chờ kiểm tra lại" : clock.running ? "đang xem CVAT" : "tạm dừng (CVAT mất focus / đổi frame)"}`;
    actions();
  } catch (err) { error(err.message); }
}
function showSaved() {
  $("saved-labels").replaceChildren();
  if (!savedSnapshot) {
    $("saved-status").textContent = lastRecheck?.queue_id===selected?.queue_id
      ? "Đã kiểm tra nhãn được CVAT lưu. Nếu sửa tiếp: Save → Kiểm tra nhãn đã lưu."
      : "Kết quả hiện tại chưa bao gồm thay đổi vừa sửa. Save trong CVAT rồi bấm Kiểm tra nhãn đã lưu.";
    return;
  }
  const readiness = lastRecheck?.queue_id===selected?.queue_id
    ? "Đã kiểm tra. Nếu sửa tiếp, Save rồi bấm Kiểm tra nhãn đã lưu."
    : savedSnapshot.backend_ready ? "Có thể kiểm tra lại lỗi."
    : "Chưa thể kiểm tra lại. Điểm chưa thay đổi; nhờ người phụ trách kiểm tra dịch vụ.";
  $("saved-status").textContent = `Đã đọc ${savedSnapshot.box_count} box được lưu trong CVAT. ${readiness}`;
  for (const [index, box] of savedSnapshot.boxes.entries()) {
    const li = document.createElement("li");
    li.textContent = `Box ${index + 1} · ${box.category} · [${box.box.map(n => Number(n).toFixed(1)).join(", ")}]`;
    $("saved-labels").append(li);
  }
}
$("read-saved").addEventListener("click", async () => {
  saving = true; actions(); error("");
  try { savedSnapshot = await worker({type: "READ_SAVED"}); showSaved(); }
  catch (err) { error(err.message); }
  finally { saving = false; actions(); }
});
async function runCheck(combined) {
  if(saving) return;
  saving = true; actions(); renderQueue(); error("");
  try {
    const result = await worker({type: combined?"RUN_QC":"RECHECK"});
    lastRecheck=result.result;
    savedSnapshot = result.savedSnapshot; recheckPending = null;
    await loadQueue(); await showDetail(result.detail); showSaved();
    $("status").textContent = `Đã kiểm tra nhãn đã lưu: ${result.result.risk_before.toFixed(1)} → ${result.result.risk_after.toFixed(1)} điểm.`;
  } catch (err) { error(err.message); await updateClock(); showSaved(); }
  finally { saving = false; actions(); renderQueue(); }
}
$("recheck").addEventListener("click",()=>runCheck(false));
$("run-qc").addEventListener("click",()=>runCheck(true));
$("previous").onclick=()=>navigate(-1);
$("next").onclick=()=>navigate(1);
function navigate(delta) {
  const at=items.findIndex(row=>row.image_id===selected?.image_id);
  if(at>=0 && items[at+delta])selectImage(items[at+delta]);
}
async function submit(verdict) {
  if (saving || !selected || recheckPending) return;
  saving = true; actions(); renderQueue(); error("");
  try {
    const objIds = [...document.querySelectorAll("[data-obj-id]:checked")].map(el => el.value);
    await worker({type: "SAVE_VERDICT", verdict, note: $("note").value, objIds});
    pending = null; selected = null; $("selected").hidden = true;
    await loadQueue();
    $("status").textContent = "Đã lưu kết luận. Chọn ảnh tiếp theo trong danh sách.";
  } catch (err) { error(err.message); await updateClock(); }
  finally { saving = false; actions(); renderQueue(); }
}
$("refresh").addEventListener("click", () => loadQueue());
$("more").addEventListener("click", () => loadQueue(true));
$("retry").addEventListener("click", () => submit(pending?.verdict));
document.querySelectorAll("[data-verdict]").forEach(button => button.addEventListener("click", () => submit(button.dataset.verdict)));
document.addEventListener("keydown", event => {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
  const verdict = {"1": "error", "2": "false_alarm", "3": "skip"}[event.key];
  if (verdict && selected && !saving && !pending) { event.preventDefault(); submit(verdict); }
});
async function startReview(reviewer, fresh = false) {
  if (saving || pending || recheckPending) return;
  error(""); saving = true; actions(); renderQueue();
  const button = $("identity-form").querySelector("button");
  button.disabled = true; button.textContent = "Đang bắt đầu…";
  try {
    const next = await worker({type: "START_REVIEW", reviewer, fresh});
    if (next.reviewer !== cfg?.reviewer || next.sessionId !== cfg?.sessionId) {
      selected = null; pending = null; savedSnapshot = null; recheckPending = null; lastRecheck = null;
      $("selected").hidden = true;
    }
    cfg = next;
    $("identity").hidden = true; $("reviewer-name").textContent = `Người review: ${cfg.reviewer}`;
    await loadQueue();
  } catch (err) { error(err.message); }
  finally { saving = false; actions(); renderQueue(); button.disabled = false; button.textContent = "Bắt đầu"; }
}
$("identity-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (cfg?.reviewer && cfg.reviewer !== $("reviewer").value.trim() &&
      !confirm("Đổi người review? Kết quả của người trước vẫn được giữ.")) return;
  await startReview($("reviewer").value.trim());
});
$("new-review").addEventListener("click", async () => {
  if (confirm("Bắt đầu lượt mới? Kết quả lượt trước vẫn được giữ.")) await startReview(cfg.reviewer, true);
});
(async () => {
  try {
    cfg = await worker({type: "SETTINGS"});
    $("reviewer").value = cfg.reviewer;
    $("identity").hidden = !!cfg.reviewer;
    $("reviewer-name").textContent = cfg.reviewer ? `Người review: ${cfg.reviewer}` : "Đối chiếu nghi vấn · xác nhận kết quả";
    if (cfg.reviewer) await loadQueue();
    else $("status").textContent = "Nhập tên của bạn rồi bấm Bắt đầu. Không cần cấu hình thêm.";
    const clock = await worker({type: "CLOCK"});
    if (clock.active) {
      pending = clock.pending; savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending; lastRecheck=clock.lastRecheck;
      await showDetail(clock.detail); showSaved();
    }
    await updateClock(); setInterval(updateClock, 1000);
  } catch (err) { error(err.message); }
})();
