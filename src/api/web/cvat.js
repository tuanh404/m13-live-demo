// Optional CVAT transport. Canvas edits are never treated as saved annotation inputs.
import {request, scopePrefix} from './transport.js';
const $ = id => document.getElementById(id);
export function cvatTools({lock, pause, reload}) {
  let current = null, captured = null, pending = null, busy = false;
  const key = 'm13.web.recheck.v1' + scopePrefix;
  try { pending = JSON.parse(localStorage.getItem(key) || 'null'); } catch { /* corrupt storage */ }
  const remember = () => localStorage.setItem(key, JSON.stringify(pending));
  function controls() {
    lock(busy || !!pending);
    $('connect-cvat').disabled = !current || busy || !!pending;
    $('read-saved').disabled = !current || busy || !!pending;
    $('show-history').disabled = !current || busy;
    $('recheck').disabled = !captured?.backend_ready || busy || !!pending;
    $('retry-recheck').hidden = !pending;
    $('retry-recheck').disabled = busy;
    if (busy || pending) $('open-cvat').hidden = true;
  }
  async function perform(action) {
    if (busy) return;
    busy = true; controls();
    try { await action(); } catch (e) {
      $('recheck-status').textContent = e.message;
      $('cvat-status').textContent = `Thao tác chưa thành công: ${e.message}`;
    }
    finally { busy = false; controls(); }
  }
  $('connect-cvat').addEventListener('click', () => perform(async () => {
    $('cvat-status').textContent = 'Đang kiểm tra job/frame và quyền đọc CVAT…';
    const value = await request(`/web/cvat/${encodeURIComponent(current.image_id)}?queue_id=${current.queue_id}`);
    $('cvat-status').textContent = value.message;
    $('open-cvat').hidden = !value.available;
    if (value.available) $('open-cvat').href = value.url;
  }));
  $('open-cvat').addEventListener('click', () => {
    pause(true);
    $('cvat-status').textContent = 'Đang sửa bên CVAT? Bấm Save ở đó, quay về đây rồi đọc nhãn đã lưu. Web chưa biết canvas đã Save chưa.';
  });
  $('read-saved').addEventListener('click', () => perform(async () => {
    $('saved-status').textContent = 'Đang đọc nhãn đã lưu từ CVAT…';
    captured = null; $('saved-boxes').replaceChildren();
    captured = await request(`/image/${encodeURIComponent(current.image_id)}/saved?queue_id=${current.queue_id}`);
    pause(false);
    $('saved-status').textContent = `Đã đọc CVAT version ${captured.annotation_version} lúc ${captured.captured_at}. ` +
      `${captured.box_count} box. Điểm và overlay vẫn là snapshot queue cũ cho tới khi chấm lại thành công. ${captured.backend_message}`;
    captured.boxes.forEach((b, i) => {
      const li = document.createElement('li');
      li.textContent = `Box ${i + 1} · ${b.category} (${b.box.join(', ')})`; $('saved-boxes').append(li);
    });
  }));
  async function finished(result) {
    pending = null; remember();
    const image = result.image_id;
    await reload(image);
    $('cvat-tools').open = true;
    $('recheck-status').textContent = `Đã chấm lại từ nhãn đã Save: ${result.risk_before} → ${result.risk_after}. ` +
      `${result.score_changed ? 'Điểm thay đổi do phép kiểm trên dữ liệu mới.' : 'Điểm không đổi; đã tạo snapshot mới.'} ` +
      'Queue/verdict trước vẫn được giữ. Có thể xem lịch sử trước / sau.';
    pause(false);
  }
  async function post() {
    try {
      const result = await request(`/image/${encodeURIComponent(pending.image_id)}/recheck`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(pending.value),
      });
      await finished(result);
    } catch (e) {
      $('recheck-status').textContent = `Chưa xác nhận chấm lại: ${e.message}. Kiểm tra trạng thái trước khi gửi yêu cầu mới.`;
      // A recorded failed transaction cannot activate later; allow a fresh capture/request.
      try {
        const status = await request(`/rechecks/${pending.value.request_id}`);
        if (status.status === 'completed') return finished(status.result);
        if (status.status === 'failed') {
          pending = null; remember(); captured = null;
          $('recheck-status').textContent = 'Chấm lại thất bại; queue cũ giữ nguyên. Đọc nhãn lại để thử yêu cầu mới.';
        }
      } catch (statusError) {
        if (statusError.status === 404 && [409, 422, 503].includes(e.status)) {
          pending = null; remember(); captured = null;
          $('recheck-status').textContent = `Yêu cầu chưa chạy: ${e.message}. Đọc nhãn đã Save lại trước khi thử.`;
        }
      }
    }
  }
  $('recheck').addEventListener('click', () => perform(async () => {
    if (!captured) return;
    pending = {image_id: current.image_id, value: {request_id: crypto.randomUUID(),
      queue_id: current.queue_id, snapshot_id: captured.snapshot_id}};
    remember(); $('recheck-status').textContent = 'Đang chấm lại từ snapshot nhãn đã Save…';
    await post();
  }));
  $('retry-recheck').addEventListener('click', () => perform(async () => {
    if (!pending) return;
    try {
      const status = await request(`/rechecks/${pending.value.request_id}`);
      if (status.status === 'completed') return finished(status.result);
      if (status.status === 'failed') {
        pending = null; remember(); captured = null;
        $('recheck-status').textContent = 'Yêu cầu đã thất bại, chưa đổi queue. Đọc nhãn lại để thử mới.'; return;
      }
      $('recheck-status').textContent = 'Yêu cầu đang chạy. Có thể kiểm tra trạng thái lại, không gửi bản trùng.';
    } catch (e) { if (e.status === 404) await post(); else throw e; }
  }));
  $('show-history').addEventListener('click', () => perform(async () => {
    const data = await request(`/web/recheck-history/${encodeURIComponent(current.image_id)}`);
    $('recheck-history').replaceChildren();
    for (const entry of data.entries) {
      const section = document.createElement('section'), p = document.createElement('p');
      const result = entry.result;
      p.textContent = result ? `${result.risk_before} → ${result.risk_after} · ${result.model_version}` :
        `${entry.status}: ${entry.error || 'đang xử lý'}`;
      section.append(p);
      if (result) for (const [title, id] of [['Trước', result.previous_queue_id], ['Sau', result.queue_id]]) {
        const button = document.createElement('button'); button.textContent = `Xem ${title.toLowerCase()}`;
        button.addEventListener('click', async () => {
          try {
            const snapshot = await request(`/web/review/${encodeURIComponent(result.image_id)}?queue_id=${id}`);
            const pre = document.createElement('pre');
            pre.textContent = `${title}: ${snapshot.risk_score}/100 · ${id}\n` + snapshot.annotations.map(
              b => `Box ${b.number} · ${b.category} (${b.box.join(', ')})`).join('\n');
            section.querySelector('pre')?.remove(); section.append(pre);
          } catch (e) { $('recheck-status').textContent = e.message; }
        });
        section.append(button);
      }
      $('recheck-history').append(section);
    }
    if (!data.entries.length) $('recheck-history').textContent = 'Chưa có lần chấm lại nào cho ảnh này.';
  }));
  return {
    reset(detail) {
      current = detail; captured = null;
      $('open-cvat').hidden = true; $('open-cvat').removeAttribute('href');
      $('cvat-status').textContent = 'CVAT tùy chọn. Kiểm tra kết nối trước khi mở để sửa.';
      $('saved-status').textContent = ''; $('saved-boxes').replaceChildren(); $('recheck-history').replaceChildren();
      $('recheck-status').textContent = pending ? 'Có yêu cầu chấm lại chưa được xác nhận. Bấm kiểm tra trạng thái.' : '';
      controls();
    },
  };
}
