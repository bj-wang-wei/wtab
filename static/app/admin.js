/* 管理后台前端（原生 JS，无构建）。接口契约与原 ThinkPHP 项目一致。 */
(function () {
  const M = window.WTAB || {};
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function api(path, data) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {}),
    });
    let json = {};
    try { json = await res.json(); } catch (e) { json = { code: 0, msg: '服务器无响应' }; }
    return json;
  }
  // 兼容没有 code 字段、直接返回 {msg,data} 的接口
  const okOf = (json) => json.code === 1 || (json.code === undefined && json.data !== undefined);

  function modal(html) {
    $('modalBox').innerHTML = html;
    $('modal').classList.add('on');
  }
  function closeModal() { $('modal').classList.remove('on'); }
  function msgModal(text) {
    $('msgText').textContent = text;
    $('msgModal').classList.add('on');
  }
  function closeMsg() { $('msgModal').classList.remove('on'); }
  $('modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeModal(); });
  $('msgModal').addEventListener('click', (e) => { if (e.target.id === 'msgModal') closeMsg(); });
  $('msgOk').onclick = closeMsg;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeModal(); closeMsg(); } });

  function form(fields) {
    return fields.map((f) => {
      if (f.type === 'select') {
        const opts = f.options.map((o) => `<option value="${esc(o[0])}"${String(o[0]) === String(f.value) ? ' selected' : ''}>${esc(o[1])}</option>`).join('');
        return `<div class="field"><label>${esc(f.label)}</label><select id="f_${f.key}">${opts}</select></div>`;
      }
      if (f.type === 'textarea') {
        return `<div class="field"><label>${esc(f.label)}</label><textarea id="f_${f.key}" rows="3">${esc(f.value)}</textarea></div>`;
      }
      return `<div class="field"><label>${esc(f.label)}</label><input id="f_${f.key}" type="${f.type || 'text'}" value="${esc(f.value)}"></div>`;
    }).join('');
  }
  const fv = (key) => { const el = $('f_' + key); return el ? el.value.trim() : ''; };

  function pager(el, info, page, last, total, load) {
    info.textContent = `共 ${total} 条，第 ${page} / ${last} 页`;
    el.prev.disabled = page <= 1;
    el.next.disabled = page >= last;
    el.prev.onclick = () => load(page - 1);
    el.next.onclick = () => load(page + 1);
  }

  /* ---------- 仪表盘 ---------- */
  const DASH_ICONS = {
    users: '<circle cx="9" cy="7" r="4"/><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  };
  const dashIco = (k) => `<span class="stat-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${DASH_ICONS[k]}</svg></span>`;
  const fmt = (n) => Number(n || 0).toLocaleString('zh-CN');

  async function loadDash() {
    const j = await api('/admin/getServicesStatus', {});
    const d = okOf(j) ? (j.data || {}) : {};
    if (okOf(j)) {
      $('stats').innerHTML = [
        ['用户总数', d.userNum, 'users'], ['文件数', d.fileNum, 'file'],
        ['7 日活跃用户', d.userWeekActive, 'pulse'],
      ].map(([k, v, ic]) => `<div class="stat">${dashIco(ic)}<div class="stat-meta"><span>${k}</span><b>${fmt(v)}</b></div></div>`).join('');
    }
    loadHot(d.topLinks || []);
  }

  function loadHot(list) {
    const el = $('hotList');
    if (!list.length) {
      el.innerHTML = '<div class="chart-empty">暂无点击数据</div>';
      $('lineSum').textContent = '暂无数据';
      return;
    }
    const max = Math.max(1, ...list.map((i) => i.count));
    // 一条一色：色相从青蓝渐变到品红，与主题蓝同调；前三名加饱和度做强调
    const tone = (k, n) => {
      const hue = 196 + (k / Math.max(1, n - 1)) * 132;
      const sat = k < 3 ? 84 : 66;
      return `--c:hsl(${hue.toFixed(0)} ${sat}% 60%);--c2:hsl(${(hue + 14).toFixed(0)} ${sat}% 68%)`;
    };
    el.innerHTML = list.map((i, k) => `
      <div class="hot-row${k < 3 ? ' top' : ''}" style="${tone(k, list.length)}">
        <span class="hot-rank">${k + 1}</span>
        <span class="hot-name" title="${esc(i.name)}">${esc(i.name)}</span>
        <span class="hot-bar"><i style="width:${Math.max(3, (i.count / max) * 100)}%"></i></span>
        <b class="hot-count">${fmt(i.count)}</b>
      </div>`).join('');
    $('lineSum').textContent = `共 ${fmt(list.reduce((s, i) => s + i.count, 0))} 次点击`;
  }

  /* ---------- 用户 ---------- */
  let uPage = 1;

  async function loadUsers(page) {
    uPage = page || 1;
    const status = $('uStatus').value;
    const j = await api('/admin/UserList', {
      limit: Number($('uLimit').value), page: uPage,
      search: { mail: $('uMail').value.trim(), nickname: $('uNick').value.trim(), status: Number(status) },
      sort: { prop: 'id', order: 'desc' },
    });
    if (!okOf(j)) { msgModal(j.msg || '读取失败'); return; }
    const d = j.data;
    $('uBody').innerHTML = d.data.map((u) => `
      <tr>
        <td>${u.id}</td>
        <td>${u.avatar ? `<img class="u-avatar" src="${esc(u.avatar)}" alt="">` : '-'}</td>
        <td>${esc(u.mail)}</td><td>${esc(u.nickname || '-')}</td>
        <td>${u.manager == 1 ? '管理员' : '普通'}</td>
        <td>${u.status == 1 ? '冻结' : '正常'}</td>
        <td class="mini">${esc(u.login_time || '-')}</td><td class="mini">${esc(u.create_time || '-')}</td>
        <td>
          <button class="btn ghost" data-u-edit="${u.id}">编辑</button>
          <button class="btn ghost" data-u-log="${u.id}">记录</button>
          <button class="btn ghost" data-u-del="${u.id}">删除</button>
        </td>
      </tr>`).join('');
    pager({ prev: $('uPrev'), next: $('uNext') }, $('uInfo'), d.current_page, d.last_page, d.total, loadUsers);
    $('uBody').querySelectorAll('[data-u-edit]').forEach((b) => (b.onclick = () => editUser(findUser(d.data, b.dataset.uEdit))));
    $('uBody').querySelectorAll('[data-u-del]').forEach((b) => (b.onclick = () => delUser(b.dataset.uDel)));
    $('uBody').querySelectorAll('[data-u-log]').forEach((b) => (b.onclick = () => loginRecords(b.dataset.uLog)));
  }
  const findUser = (rows, id) => rows.find((u) => String(u.id) === String(id)) || {};

  const AVATAR_PRESETS = Array.from({ length: 10 }, (_, i) => `/static/avatar/presets/${String(i + 1).padStart(2, '0')}.png`);

  function editUser(u) {
    const av = u.avatar || (u.id ? '' : AVATAR_PRESETS[0]);
    modal(`<h3>${u.id ? '编辑用户 #' + u.id : '新建用户'}</h3>
      <div class="field"><label>头像</label>
        <div class="avatar-pick">
          <div class="avatar-pick-left">
            <img id="fAvatarPrev" class="u-avatar-prev" alt="" src="${esc(av)}"${av ? '' : ' hidden'}>
            <input id="f_avatar" type="hidden" value="${esc(av)}">
          </div>
          <div class="u-avatar-presets" id="fAvatarPresets"></div>
        </div>
      </div>
      ${form([
        { key: 'mail', label: '邮箱', value: u.mail || '' },
        { key: 'nickname', label: '昵称', value: u.nickname || '' },
        { key: 'password', label: '密码（留空不修改）', value: '' },
        { key: 'manager', label: '角色', value: u.manager || 0, type: 'select', options: [['0', '普通用户'], ['1', '管理员']] },
        { key: 'status', label: '状态', value: u.status || 0, type: 'select', options: [['0', '正常'], ['1', '冻结']] },
      ])}
      <div class="modal-actions"><button class="btn ghost" id="cancel">取消</button><button class="btn" id="save">保存</button></div>`);
    const avInput = $('f_avatar');
    const avPrev = $('fAvatarPrev');
    const presetBox = $('fAvatarPresets');
    const syncAvatar = () => {
      const v = avInput.value.trim();
      avPrev.hidden = !v;
      if (v) avPrev.src = v;
      presetBox.querySelectorAll('img').forEach((el) => el.classList.toggle('on', el.dataset.url === v));
    };
    AVATAR_PRESETS.forEach((url, i) => {
      const img = document.createElement('img');
      img.src = url;
      img.alt = `预设 ${i + 1}`;
      img.title = `预设 ${i + 1}`;
      img.dataset.url = url;
      img.onclick = () => { avInput.value = url; syncAvatar(); };
      presetBox.appendChild(img);
    });
    avInput.addEventListener('input', syncAvatar);
    syncAvatar();
    $('cancel').onclick = closeModal;
    $('save').onclick = async () => {
      const body = {
        id: u.id || 0, mail: fv('mail'), nickname: fv('nickname'), password: fv('password'),
        avatar: fv('avatar'),
        manager: Number(fv('manager')), status: Number(fv('status')),
      };
      const j = await api('/admin/userUpdate', body);
      if (okOf(j)) { closeModal(); loadUsers(uPage); }
      else msgModal(j.msg);
    };
  }

  async function delUser(id) {
    modal(`<h3>删除用户 #${id}</h3><p class="warn">会同时删除该用户的书签、配置、笔记、备份与登录令牌，不可恢复。</p>
      <div class="modal-actions"><button class="btn ghost" id="cancel">取消</button><button class="btn" id="save">确认删除</button></div>`);
    $('cancel').onclick = closeModal;
    $('save').onclick = async () => {
      const j = await api('/admin/userDelete', { id: Number(id) });
      if (!okOf(j)) msgModal(j.msg);
      closeModal();
      loadUsers(uPage);
    };
  }

  async function loginRecords(id) {
    const j = await api('/admin/userLoginRecord', { user_id: Number(id) });
    const rows = (j.data || []).map((r) => `<tr><td class="mini">${esc(r.create_time || '-')}</td><td class="mini">${esc(r.ip || '-')}</td><td class="mini">${esc((r.user_agent || '').slice(0, 42))}</td></tr>`).join('');
    modal(`<h3>登录记录 · 用户 #${id}</h3>
      <div class="table-wrap"><table><thead><tr><th>时间</th><th>IP</th><th>User-Agent</th></tr></thead><tbody>${rows || '<tr><td colspan="3">暂无记录</td></tr>'}</tbody></table></div>
      <div class="modal-actions"><button class="btn ghost" id="cancel">关闭</button></div>`);
    $('cancel').onclick = closeModal;
  }

  /* ---------- 搜索引擎管理 ---------- */
  async function loadEngines(page) {
    ePage = page || 1;
    const j = await api('/searchEngine/list', {
      search: { name: $('eSearch').value.trim() }
    });
    if (!okOf(j)) { msgModal(j.msg || '读取失败'); return; }
    const rows = j.data || [];
    $('eBody').innerHTML = rows.map((it) => `
      <tr>
        <td>${it.id}</td>
        <td>${it.icon ? `<img class="ico" src="${esc(it.icon)}" alt="">` : ''}</td>
        <td>${esc(it.name)}</td>
        <td class="mini">${esc(it.url)}</td>
        <td>${it.sort || 0}</td>
        <td>${it.status == 1 ? '启用' : '禁用'}</td>
        <td class="mini">${esc(it.tips || '-')}</td>
        <td>
          <button class="btn ghost" data-e-edit="${it.id}">编辑</button>
          <button class="btn ghost" data-e-tog="${it.id}" data-st="${it.status}">${it.status == 1 ? '禁用' : '启用'}</button>
          <button class="btn ghost" data-e-del="${it.id}">删除</button>
        </td>
      </tr>`).join('');
    pager({ prev: $('ePrev'), next: $('eNext') }, $('eInfo'), 1, 1, rows.length, loadEngines);
    $('eBody').querySelectorAll('[data-e-edit]').forEach((b) => (b.onclick = () => editEngine(rows.find((x) => String(x.id) === b.dataset.eEdit))));
    $('eBody').querySelectorAll('[data-e-del]').forEach((b) => (b.onclick = async () => {
      const j2 = await api('/searchEngine/del', { ids: [Number(b.dataset.eDel)] });
      if (!okOf(j2)) msgModal(j2.msg); loadEngines(ePage);
    }));
    $('eBody').querySelectorAll('[data-e-tog]').forEach((b) => (b.onclick = async () => {
      const it = rows.find((x) => String(x.id) === b.dataset.eTog);
      const j2 = await api('/searchEngine/add', { form: { id: it.id, status: b.dataset.st == 1 ? 0 : 1 } });
      if (!okOf(j2)) msgModal(j2.msg); loadEngines(ePage);
    }));
  }

  function editEngine(it) {
    it = it || {};
    const iconVal = it.icon || '/static/searchEngine/search.svg';
    modal(`<h3>${it.id ? '编辑搜索引擎 #' + it.id : '添加搜索引擎'}</h3>
      ${form([
        { key: 'name', label: '名称', value: it.name || '' },
        { key: 'url', label: '地址（含 {1} 占位符）', value: it.url || '' },
        { key: 'icon', type: 'hidden', value: iconVal },
        { key: 'tips', label: '提示文字', value: it.tips || '' },
        { key: 'sort', label: '排序', value: it.sort || 0, type: 'number' },
        { key: 'status', label: '状态', value: it.status == null ? 1 : it.status, type: 'select', options: [['1', '启用'], ['0', '禁用']] },
      ])}
      <div class="field"><label>图标预览</label>
        <div class="inline-field">
          <img id="eIconPrev" class="e-icon-prev" alt="" src="${esc(iconVal)}"${iconVal ? '' : ' hidden'}>
          <input type="file" accept="image/*" id="eIconUpload" style="display:none;">
          <button type="button" class="btn ghost" id="eIconUploadBtn">选择图标</button>
          <span id="eIconUploadStatus" style="margin-left:8px;font-size:12px;color:var(--muted)"></span>
        </div>
      </div>
      <div class="modal-actions"><button class="btn ghost" id="cancel">取消</button><button class="btn" id="save">保存</button></div>`);
    const iconInput = $('f_icon');
    const iconPrev = $('eIconPrev');
    const uploadBtn = $('eIconUploadBtn');
    const fileInput = $('eIconUpload');
    const statusEl = $('eIconUploadStatus');
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      statusEl.textContent = '上传中...';
      const fd = new FormData();
      fd.append('file', f);
      fd.append('category', 'linklogo');
      try {
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        const j = await res.json();
        if (j.code === 1) {
          const url = j.data.url;
          iconInput.value = url;
          iconPrev.src = url;
          iconPrev.hidden = false;
          statusEl.textContent = '上传成功';
        } else {
          statusEl.textContent = '上传失败：' + (j.msg || '未知错误');
        }
      } catch (err) {
        statusEl.textContent = '上传异常：' + err.message;
      }
    };
    $('cancel').onclick = closeModal;
    $('save').onclick = async () => {
      const payload = {
        id: it.id || 0, name: fv('name'), url: fv('url'), icon: fv('icon'),
        tips: fv('tips'), sort: Number(fv('sort') || 0), status: Number(fv('status')),
      };
      const j = await api('/searchEngine/add', { form: payload });
      if (okOf(j)) { closeModal(); loadEngines(ePage); }
      else msgModal(j.msg);
    };
  }

  let ePage = 1;

  /* ---------- 壁纸 ---------- */
  let wallOffset = 0;
  let wallLoading = false;
  let wallNoMore = false;
  const wallPage = 20;

  function wallItemHtml(w) {
    return `
      <div class="wall-item" data-wall-id="${w.id}" data-wall-url="${esc(w.url)}" data-wall-mime="${w.mime}">
        ${w.mime == 1
          ? `<video src="${esc(w.url)}" muted preload="metadata"></video>`
          : `<img src="${esc(w.url)}" alt="" loading="lazy">`}
        <span class="name">${esc(w.name || '')}</span>
      </div>`;
  }

  async function loadWalls(reset) {
    if (wallLoading) return;
    wallLoading = true;
    if (reset) {
      wallOffset = 0;
      wallNoMore = false;
      // 保留上传控件，只清掉壁纸项
      [...$('wGrid').children].forEach((c) => { if (c.id !== 'wUpload' && c.id !== 'wFile') c.remove(); });
      $('wGrid').style.minHeight = '';
    }
    const j = await api('/wallpaper/allClient', { offset: wallOffset, limit: wallPage });
    wallLoading = false;
    if (!okOf(j)) { msgModal(j.msg || '壁纸加载失败'); return; }
    const rows = j.data || [];
    if (reset && !rows.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.textContent = '暂无壁纸';
      $('wGrid').appendChild(empty);
      wallNoMore = true;
      return;
    }
    rows.forEach((w) => {
      const tpl = document.createElement('div');
      tpl.innerHTML = wallItemHtml(w);
      const node = tpl.firstElementChild;
      $('wGrid').appendChild(node);
    });
    wallOffset += 1;
    wallNoMore = rows.length < wallPage;
    scrollWallAdminCheck();
  }

  /* 滚动到底自动加载 */
  function scrollWallAdminCheck() {
    if (wallNoMore || wallLoading) return;
    const doc = document.documentElement;
    const nearBottom = window.innerHeight + window.scrollY >= doc.scrollHeight - 200;
    if (nearBottom) loadWalls(false);
  }

  /* ---------- 文件 ---------- */
  let fPage = 1;
  /* 选择列：表头全选 / 半选状态 */
  function syncFAll() {
    const boxes = [...$('fBody').querySelectorAll('[data-f-check]')];
    const on = boxes.filter((b) => b.checked).length;
    $('fAll').checked = boxes.length > 0 && on === boxes.length;
    $('fAll').indeterminate = on > 0 && on < boxes.length;
  }

  async function loadFiles(page) {
    fPage = page || 1;
    const j = await api('/file/list', { limit: 20, page: fPage, search: { path: $('fSearch').value.trim() } });
    if (!okOf(j)) { msgModal(j.msg || '读取失败'); return; }
    const d = j.data;
    $('fBody').innerHTML = (d.data || []).map((f) => `
      <tr>
        <td><input type="checkbox" data-f-check="${f.id}"></td>
        <td>${f.id}</td>
        <td>${f.mime_type && f.mime_type.startsWith('image') ? `<img class="ico" src="${esc(f.path)}" alt="">` : ''}</td>
        <td class="mini">${esc(f.path)}</td><td class="mini">${esc(f.mime_type || '-')}</td>
        <td>${Math.round((f.size || 0) / 1024)} KB</td>
        <td class="mini">${esc((f.user && f.user.mail) || '-')}</td><td class="mini">${esc(f.create_time || '-')}</td>
        <td><span class="ops"><button class="btn ghost" data-f-del="${f.id}">删除</button><a class="btn ghost" href="${esc(f.path)}" download>下载</a></span></td>
      </tr>`).join('');
    pager({ prev: $('fPrev'), next: $('fNext') }, $('fInfo'), d.current_page, d.last_page, d.total, loadFiles);
    $('fBody').querySelectorAll('[data-f-check]').forEach((b) => (b.onchange = syncFAll));
    syncFAll();
    $('fBody').querySelectorAll('[data-f-del]').forEach((b) => (b.onclick = async () => {
      const id = Number(b.dataset.fDel);
      const path = b.closest('tr').children[3].textContent; // 第 1 列是勾选框，路径在第 4 列
      modal(`<h3>删除文件</h3><p class="warn">确认删除 ${esc(path)} ？关联的壁纸记录会一并移除，不可恢复。</p>
        <div class="modal-actions"><button class="btn ghost" id="cancel">取消</button><button class="btn" id="save">确认删除</button></div>`);
      $('cancel').onclick = closeModal;
      $('save').onclick = async () => {
        const j2 = await api('/file/del', { ids: [id] });
        if (!okOf(j2)) msgModal(j2.msg);
        closeModal();
        loadFiles(fPage);
      };
    }));
  }

  /* ---------- 系统设置 ---------- */
  const SETTING_FIELDS = [
    ['基础信息', [
      ['title', '网站标题', 'text'], ['keywords', '关键词', 'text'], ['description', '描述', 'text'],
      ['logo', 'Logo 地址', 'image'], ['favicon', 'Favicon 地址', 'image'],
      ['defaultTab', '出厂书签文件', 'text'],
    ]],
    ['注册与登录', [
      ['user_register', '关闭注册', 'bool'],
      ['loginCloseRecordNumber', '未登录页隐藏备案号', 'bool'],
    ]],
    ['联系与备案', [
      ['email', '联系邮箱', 'text'], ['qqGroup', 'QQ 群', 'text'], ['copyright', '版权信息', 'text'],
      ['beianMps', '公安备案', 'text'], ['recordNumber', 'ICP 备案', 'text'],
      ['mobileRecordNumber', '移动端隐藏备案', 'bool'], ['aboutMe', '关于我们（HTML）', 'textarea'],
    ]],
    ['邮件通知', [
      ['smtp_host', 'SMTP 服务器', 'text'], ['smtp_port', 'SMTP 端口', 'text'], ['smtp_email', '发件邮箱', 'text'],
      ['smtp_password', '邮箱密码/授权码', 'text'],
      ['smtp_code_template', '验证码模板', 'textarea-tall'],
      ['resend_api_key', '发送邮件 API Key', 'text'],
    ]],
    ['上传与资源', [
      ['upload_size', '上传大小上限(MB)', 'slider'],
      ['assets_host', '静态资源 CDN', 'text'],
    ]],
    ['其它', [
      ['privacy', '隐私政策（HTML）', 'textarea'],
      ['globalNotify', '全局公告(JSON)', 'textarea'],
    ]],
  ];
  const ALL_KEYS = SETTING_FIELDS.flatMap(([, items]) => items.map(([k]) => k)).concat(['mail_use_resend', 'smtp_ssl']);

  async function loadSettings() {
    const j = await api('/setting/getSetting', { role: ALL_KEYS });
    const saved = (j && j.data && typeof j.data === 'object') ? j.data : {};
    $('setForm').innerHTML = SETTING_FIELDS.map(([group, items]) => {
      const body = items.map(([key, label, type]) => {
        const value = saved[key] == null ? '' : saved[key];
        if (type === 'bool') {
          return `<label class="check"><input type="checkbox" id="s_${key}"${value === '1' ? ' checked' : ''}>${esc(label)}</label>`;
        }
        if (type === 'textarea' || type === 'textarea-tall') {
          return `<label class="s-field wide${type === 'textarea-tall' ? ' tall' : ''}"><span class="s-label">${esc(label)}</span><textarea id="s_${key}">${esc(value)}</textarea></label>`;
        }
        if (type === 'image') {
          return `<div class="s-field"><span class="s-label">${esc(label)}</span><span class="s-up-row"><input id="s_${key}" value="${esc(value)}"><button type="button" class="btn ghost s-up" data-key="${key}">上传</button></span></div>`;
        }
        if (type === 'slider') {
          // upload_size 空值等价于后端默认 2
          const cur = esc(value === '' ? (key === 'upload_size' ? '2' : '0') : value);
          return `<div class="s-field"><span class="s-label">${esc(label)}</span><div class="s-range"><span>2</span><input type="range" id="s_${key}" min="2" max="10" step="1" value="${cur}"><span>10</span><span>当前 <b id="v_${key}">${cur}</b></span></div></div>`;
        }
        if (key === 'smtp_port') {
          return `<div class="s-field"><span class="s-label">${esc(label)}</span><span class="s-inline"><input id="s_${key}" value="${esc(value)}"><label class="check"><input type="checkbox" id="s_smtp_ssl"${saved.smtp_ssl === '1' ? ' checked' : ''}>使用 SSL</label></span></div>`;
        }
        if (key === 'resend_api_key') {
          return `<div class="s-field"><span class="s-label">${esc(label)}</span><span class="s-inline"><input id="s_${key}" value="${esc(value)}"><label class="check"><input type="checkbox" id="s_mail_use_resend"${saved.mail_use_resend === '1' ? ' checked' : ''}>使用 Resend</label></span></div>`;
        }
        return `<label class="s-field"><span class="s-label">${esc(label)}</span><input id="s_${key}" value="${esc(value)}"></label>`;
      }).join('');
      return `<div class="set-group"><h3>${esc(group)}</h3><div class="set-grid">${body}</div></div>`;
    }).join('');
    // 滑块实时显示当前值
    $('setForm').querySelectorAll('.s-range input[type="range"]').forEach((el) => {
      const out = $('v_' + el.id.slice(2));
      if (out) el.oninput = () => { out.textContent = el.value; };
    });
    // 图片地址字段：上传后把返回的 url 填进输入框，保存设置时一起提交
    $('setForm').querySelectorAll('.s-up').forEach((btn) => {
      const key = btn.dataset.key;
      const file = document.createElement('input');
      file.type = 'file';
      file.accept = 'image/*';
      file.hidden = true;
      btn.after(file);
      btn.onclick = () => file.click();
      file.onchange = async () => {
        const f = file.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append('file', f);
        fd.append('category', 'linklogo');
        btn.disabled = true;
        btn.textContent = '上传中…';
        try {
          const res = await fetch('/api/upload', { method: 'POST', body: fd });
          const rj = await res.json();
          if (rj.code !== 1) { msgModal(rj.msg || '上传失败'); return; }
          $('s_' + key).value = rj.data.url;
          btn.textContent = '已上传';
        } catch (err) {
          msgModal('上传异常：' + err.message);
        } finally {
          btn.disabled = false;
          file.value = '';
          setTimeout(() => { btn.textContent = '上传'; }, 1200);
        }
      };
    });
  }

  async function saveSettings() {
    const formData = {};
    ALL_KEYS.forEach((key) => {
      const el = $('s_' + key);
      if (!el) return;
      formData[key] = el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value.trim();
    });
    const j = await api('/setting/saveSetting', { form: formData });
    if (!okOf(j)) msgModal(j.msg);
  }

  /* ---------- 事件绑定 ---------- */
  const TITLES = { dash: '仪表盘', users: '用户列表', engine: '搜索引擎', wall: '壁纸管理', file: '文件管理', setting: '系统设置' };
  $('nav').addEventListener('click', (e) => {
    const tab = e.target.dataset.tab;
    if (!tab) return;
    $('nav').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b === e.target));
    document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('on', p.id === 'pane-' + tab));
    $('title').textContent = TITLES[tab];
    ({ dash: loadDash, users: () => loadUsers(1), engine: () => loadEngines(1), wall: () => loadWalls(true), file: () => loadFiles(1), setting: loadSettings }[tab])();
  });

  $('uLimit').onchange = () => loadUsers(1);
  $('uSearch').onclick = () => loadUsers(1);
  $('uNew').onclick = () => editUser({});
  $('eSearchBtn').onclick = () => loadEngines(1);
  $('eNew').onclick = () => editEngine({});
  $('wUpload').onclick = () => $('wFile').click();
  $('wFile').onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f);
    fd.append('category', 'wallpaper');
    $('wUpload').classList.add('busy');
    try {
      const res = await fetch('/api/AdminUpload', { method: 'POST', body: fd });
      const j = await res.json();
      if (j.code !== 1) { msgModal(j.msg || '上传失败'); return; }
      const ja = await api('/wallpaper/addWallpaper', {
        url: j.data.url, type: 0, mime: f.type.startsWith('video') ? 1 : 0,
      });
      if (!okOf(ja)) { msgModal(ja.msg || '登记失败'); return; }
      loadWalls(true);
    } catch (err) {
      msgModal('上传异常：' + err.message);
    } finally {
      e.target.value = '';
      $('wUpload').classList.remove('busy');
    }
  };
  window.addEventListener('scroll', scrollWallAdminCheck, { passive: true });
  $('wGrid').addEventListener('scroll', scrollWallAdminCheck, { passive: true });
  $('fSearchBtn').onclick = () => loadFiles(1);
  $('fZip').onclick = async () => {
    const ids = [...$('fBody').querySelectorAll('[data-f-check]')]
      .filter((b) => b.checked).map((b) => Number(b.dataset.fCheck));
    if (!ids.length) { msgModal('请先勾选要下载的文件'); return; }
    const res = await fetch('/file/downloadZip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) { msgModal('打包失败'); return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = 'files.zip';
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $('fAll').onchange = () => {
    $('fBody').querySelectorAll('[data-f-check]').forEach((b) => { b.checked = $('fAll').checked; });
    syncFAll();
  };
  $('setSave').onclick = saveSettings;
  $('setRefresh').onclick = async () => { const j = await api('/setting/refreshCache', {}); if (!okOf(j)) msgModal(j.msg); };
  $('mailTest').onclick = async () => {
    await saveSettings(); // 先保存，勾选「使用 Resend」无需再点保存
    const j = await api('/setting/mailTest', { email: $('mailTo').value.trim() });
    msgModal(okOf(j) ? '邮件发送成功' : j.msg);
  };
  $('doRepair').onclick = async () => { const j = await api('/admin/repair', {}); if (!okOf(j)) msgModal(j.msg); };
  $('doExport').onclick = async () => {
    const cur = await api('/link/get', {});
    const link = okOf(cur) ? cur.data : null;
    if (!link || !link.length) { msgModal('没有可导出的书签'); return; }
    const j = await api('/admin/export', { link });
    if (!okOf(j)) msgModal(j.msg);
  };
  // 重置系统：要手打确认词才能点，防误触
  const RESET_WORD = '重置此系统';
  $('doReset').onclick = () => {
    modal(`
      <h3>危险操作：重置此系统</h3>
      <p>这会删除数据库中的<b>全部数据</b>：所有用户与管理员账号、书签、分组、便签、标签栏、搜索引擎、浏览历史、上传记录、壁纸和站点设置。随后移除安装标记并跳转到安装向导。</p>
      <p><b>删除后无法恢复</b>，请先自行备份数据库。</p>
      <div class="field"><label>输入「${RESET_WORD}」以确认</label><input id="resetWord" autocomplete="off" placeholder="${RESET_WORD}"></div>
      <div class="modal-actions">
        <button class="btn ghost" id="resetCancel">取消</button>
        <button class="btn danger" id="resetOk" disabled>确认重置</button>
      </div>`);
    const word = $('resetWord');
    const btn = $('resetOk');
    word.focus();
    word.oninput = () => { btn.disabled = word.value.trim() !== RESET_WORD; };
    $('resetCancel').onclick = closeModal;
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = '重置中…';
      const j = await api('/admin/reset', {});
      if (!okOf(j)) { closeModal(); msgModal(j.msg || '重置失败'); return; }
      location.href = '/install';
    };
  };
  loadDash();
})();
