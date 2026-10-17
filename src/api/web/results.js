import {request} from './transport.js';
const $ = id => document.getElementById(id);
const percent = v => v == null ? 'Chưa có' : `${(v*100).toFixed(2)}%`;
request('/auth/session').then(async auth=>{
  if(auth.enabled&&auth.identity?.role!=='admin')return;
  const pilot=await request('/pilot/status');
  $('report-pilot-link').hidden=!pilot.configured;
}).catch(()=>{});
async function load() {
  $('report-retry').hidden = true;
  try {
    const r = await request('/web/results');
    $('report-dataset').textContent = (r.dataset_kind==='bdd2018_labels_verified'?
      'Nhãn BDD2018 đúng hash đã chốt, với lỗi tiêm có đáp án.':'Dữ liệu fixture/chưa xác minh nguồn nhãn, với lỗi tiêm có đáp án.') +
      ' Không phải lỗi được QC xác nhận hoặc nghiệm thu ảnh BDD thật.';
    $('report-meta').textContent = `${r.model_version} · split ${r.split} · ${r.n_images} ảnh · ${r.n_errors} lỗi tiêm / ${r.n_error_images} ảnh có lỗi · seed ${r.seed} · random ${r.random_seeds} seed.`;
    $('report-rows').replaceChildren();
    for (const [name,row] of [[r.model_version,r],['Thứ tự file',r.file_order],
      ['Random · trung bình',Object.fromEntries(Object.entries(r.random).map(([k,v])=>[k,v.mean]))],
      ['Random · độ lệch chuẩn',Object.fromEntries(Object.entries(r.random).map(([k,v])=>[k,v.std]))]]) {
      const tr = document.createElement('tr');
      for (const v of [name,percent(row.recall20_img),percent(row.recall20_weighted),percent(row.time_saved)]) {
        const td = document.createElement('td');td.textContent=v;tr.append(td);
      }
      $('report-rows').append(tr);
    }
    $('per-type').replaceChildren();
    for (const [type,value] of Object.entries(r.per_type)) {
      const li=document.createElement('li');li.textContent=`${type}: ${percent(value)}`;$('per-type').append(li);
    }
    $('report-source').textContent=JSON.stringify({provenance:r.provenance,limitations:r.limitations,
      time_saved_kind:r.time_saved_kind,review_cost_kind:r.review_cost_kind},null,2);
    $('report').hidden=false;$('report-status').textContent='Đã tải metric và gain curve từ artifacts đã kiểm hash.';
  } catch(e) { $('report-status').textContent=e.message;$('report').hidden=true;$('report-retry').hidden=false; }
}
$('report-retry').addEventListener('click',load);load();
async function loadTiming() {
  $('timing-retry').hidden=true;
  try {
    const t=await request('/web/team-timing');
    $('team-timing').textContent=`${t.image_count} ảnh: có trợ lý ${t.assisted_minutes} phút; `+
      `thủ công ${t.manual_minutes} phút. Mức giảm tính từ số liệu này: ${(t.reduction_fraction*100).toFixed(1)}%.`;
  }catch(e){$('team-timing').textContent=e.message;$('timing-retry').hidden=false;}
}
$('timing-retry').addEventListener('click',loadTiming);loadTiming();
