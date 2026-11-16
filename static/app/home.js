/* 主页：书签渲染与交互。数据由服务端注入 window.WTAB，改动通过 /link/update 回写。 */
(function () {
  const S = window.WTAB;
  const $ = (id) => document.getElementById(id);
  const theme = (S.config && S.config.theme) || {};
  const openType = (S.config && S.config.openType) || {};
  // 编辑未登录主页：所有改动先留在内存，点「保存」才写库
  const GUEST = S.guestEdit === true;
  const GUEST_HELD = new Set(["/link/update", "/config/update", "/tabbar/update"]);

  let links = Array.isArray(S.links) ? S.links.slice() : [];
  let activePage = (() => {
    const saved = theme.latestPageGroup || "";
    return saved && (S.pageGroups || []).includes(saved) ? saved : "";
  })();

  let dirNext = null; // "up"：切到更下面的分类，内容从底部升起；"down"：切到更上面的分类，内容从顶部落下
  let engine = null;

  /* ---------- 工具 ---------- */
  const uuid = () =>
    (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).toUpperCase();

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.hidden = true), 2000);
  }

  async function post(url, body) {
    if (GUEST && GUEST_HELD.has(url)) return { code: 1, msg: "ok" };
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    if (res.status === 401) return { code: 0, msg: "请先登录" };
    return res.json();
  }

  // 书签点击埋点：pointerdown 在导航前触发，sendBeacon 不阻塞跳转
  document.addEventListener(
    "pointerdown",
    (e) => {
      const a = e.target.closest && e.target.closest("a[href]");
      const href = a && a.getAttribute("href");
      if (!href || !/^https?:\/\//i.test(href)) return;
      const payload = JSON.stringify({ url: href, name: (a.dataset.name || a.textContent || "").trim() });
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/link/click", new Blob([payload], { type: "application/json" }));
      } else {
        fetch("/link/click", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true });
      }
    },
    true
  );

  const groupsOf = () => links.filter((i) => i.type === "component");
  const childrenOf = (pid) => links.filter((i) => i.pid === pid);
  const isChild = (i) => !!i.pid;

  /* ---------- 排序 ---------- */
  function normalizeSort() {
    const pageOrder = [""].concat(S.pageGroups || []);
    links.forEach((i) => {
      if (!pageOrder.includes(i.pageGroup || "")) pageOrder.push(i.pageGroup);
    });
    // 按分类分桶，各组内按 sort 排序（不能全局排序——sort 编号带分类偏移 pi*1000，混排会跨分类串位）
    pageOrder.forEach((p, pi) => {
      const bucket = links
        .filter((i) => !isChild(i) && (i.pageGroup || "") === p)
        .sort((a, b) => (a.sort || 0) - (b.sort || 0));
      bucket.forEach((item, idx) => (item.sort = pi * 1000 + idx * 10));
    });
  }

  /* ---------- 渲染 ---------- */
  function iconNode(item) {
    const node = document.createElement("a");
    const [rows, cols] = (item.size || "1x1").split("x").map(Number);
    node.className = "icon";
    node.dataset.size = item.size || "1x1";
    node.draggable = true; // 拖动图标即可换位置（同一分类内）
    node.style.setProperty("--spanr", rows || 1);
    node.style.setProperty("--spanc", cols || 1);
    node.href = item.url || "#";
    node.dataset.id = item.id;
    if (item.type !== "component") node.target = openType.linkOpen === false ? "_self" : "_blank";
    node.rel = "noopener";

    const box = document.createElement("div");
    box.className = "icon-img";
    if (item.bgColor) box.style.background = item.bgColor;
    if (item.src) {
      box.innerHTML = `<img src="${item.src}" alt="" loading="lazy">`;
      const img = box.firstElementChild;
      img.onerror = () => {
        img.remove();
        const span = document.createElement("span");
        span.className = "letter";
        span.textContent = (item.name || "?").trim().charAt(0);
        box.appendChild(span);
      };
    }
    if (!item.src) {
      const span = document.createElement("span");
      span.className = "letter";
      span.textContent = (item.name || "?").trim().charAt(0);
      box.appendChild(span);
    }
    node.appendChild(box);

    if (theme.LinkTitle) {
      const t = document.createElement("span");
      t.className = "icon-name";
      t.textContent = item.name || "";
      node.appendChild(t);
    }
    node.title = item.name || "";

    node.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openCtx(item, e);
    });

    if (S.loggedIn) bindDrag(node, item);

    return node;
  }

  /* ---------- 拖动排序 ---------- */
  let dragId = null;
  let dragNode = null;
  let lastXY = null; // 最近一次 dragover 的指针坐标（dragend 坐标为空时兜底）
  let dockDrag = null; // dock 栏被拖动的项 { id, node }
  let dockAt = null;

  // 把 node 就地插到 target 前/后，其它兄弟用 FLIP 平滑让位（only 限定参与动画的元素）
  function shiftInto(container, node, target, after, only) {
    if (!node || node === target) return;
    const ref = after ? target.nextSibling : target;
    if (ref === node) return;
    if (!after && node.nextSibling === target) return;

    const before = new Map();
    [...container.children].forEach((el) => {
      if (only && !el.matches(only)) return;
      before.set(el, el.getBoundingClientRect());
    });
    container.insertBefore(node, ref);
    [...container.children].forEach((el) => {
      if (el === node) return;
      const prev = before.get(el);
      if (!prev) return;
      const now = el.getBoundingClientRect();
      const dx = prev.left - now.left;
      const dy = prev.top - now.top;
      if (!dx && !dy) return;
      el.style.transition = "none";
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        el.style.transition = "transform .18s cubic-bezier(.2,.8,.3,1)";
        el.style.transform = "";
      });
    });
  }

  function shiftIcons(target, after) {
    shiftInto($("grid"), dragNode, target, after);
  }

  // 拖动期间给网格打标记，CSS 里禁掉悬停位移/放大（否则被拖的图标看起来变大了）
  function markDragging(on) {
    $("grid").classList.toggle("dragging", on);
  }

  function bindDrag(node, item) {
    node.addEventListener("dragstart", (e) => {
      dragId = item.id;
      dragNode = node;
      lastXY = null;
      e.dataTransfer.setData("text/plain", item.id);
      e.dataTransfer.effectAllowed = "move";
      markDragging(true);
      node.classList.add("dragging");
    });
    node.addEventListener("dragend", (e) => finishDrag(e));
    node.addEventListener("dragover", (e) => {
      // 卡片内的图标拖出来时不要插进网格（那样会被网格拉伸，看起来“变大了”）
      if (!dragId || dragId === item.id || (dragNode && dragNode.classList.contains("gicon"))) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      lastXY = { x: e.clientX, y: e.clientY };
      const r = node.getBoundingClientRect();
      shiftIcons(node, e.clientX > r.left + r.width / 2);
    });
  }

  // 把 fromId 放到 toId 之前（after=false）或之后（after=true），同一分类内换位置
  function moveIcon(fromId, toId, after) {
    const moved = links.find((i) => i.id === fromId);
    const target = links.find((i) => i.id === toId);
    if (!moved || !target) return;
    delete moved.pid; // 从文件夹里拖出来：脱离父文件夹，回到当前分类
    moved.pageGroup = target.pageGroup || "";
    // normalizeSort() 会先按 sort 重新排序，所以这里用相邻的中间值定序，再由它重新编号
    moved.sort = (target.sort || 0) + (after ? 5 : -5);
    normalizeSort();
  }

  // 卡片尺寸按「先横向再纵向」长大：2x2 → 2x3 → 3x3 → 3x4 → 4x4 → 4x5…
  function fitSize(size, need) {
    let [r, c] = (size || "2x2").split("x").map(Number);
    r = Math.max(r || 2, 2);
    c = Math.max(c || 2, 2);
    while (r * c < need) {
      if (c <= r) c++;
      else r++;
    }
    return r + "x" + c;
  }

  // 子项变少时缩回刚好装得下的尺寸（只缩不涨）
  function shrinkGroup(g) {
    if (!g) return;
    const cap = (s) => (s || "2x2").split("x").reduce((a, b) => a * Number(b), 1);
    const next = fitSize("2x2", childrenOf(g.id).length);
    if (cap(next) < cap(g.size)) g.size = next;
  }

  // 拖到网格空白处 = 追加到当前分类末尾（末尾位置没有可拖目标时，空区域就是落点）
  async function moveIconToEnd(id) {
    const moved = links.find((i) => i.id === id);
    if (!moved) return;
    delete moved.pid;
    moved.pageGroup = activePage || "";
    const tops = links.filter((i) => i.id !== id && !isChild(i) && (i.pageGroup || "") === moved.pageGroup);
    moved.sort = tops.length ? Math.max(...tops.map((i) => i.sort || 0)) + 10 : 0;
    normalizeSort();
    render();
    await saveLinks();
  }

  // 松手位置 → 插入点：按「行」定位（行内以中心线判断插在哪个图标前/后）
  // 这样鼠标落在哪就插到哪，不再靠“最近矩形左半边”猜（之前会突然跳到首位）
  function findDropSlot(node, x, y) {
    const boxes = [...$("grid").children]
      .filter((n) => n.dataset.id && n !== node)
      .map((n) => ({ n, r: n.getBoundingClientRect() }));
    if (!boxes.length) return null;
    // 以距页面顶部的偏移分行（卡片跨多行，归到它起始的那行）
    const pageTop = boxes[0].r.top + window.scrollY;
    const rows = new Map();
    boxes.forEach((b) => {
      const k = Math.round((b.r.top + window.scrollY - pageTop) / 8);
      if (!rows.has(k)) rows.set(k, []);
      rows.get(k).push(b);
    });
    const rowList = [...rows.values()].map((v) => v.sort((a, b) => a.r.left - b.r.left));
    let row = rowList[0];
    let bestD = Infinity;
    rowList.forEach((v) => {
      // 行距离 = 该行各项中心到指针的最小距离（卡片跨多行时按中心算，不会把整列都算成同一行）
      const d = Math.min(...v.map((b) => Math.abs(y - (b.r.top + b.r.height / 2))));
      if (d < bestD) { bestD = d; row = v; }
    });
    for (const b of row) {
      if (x < b.r.left + b.r.width / 2) return { id: b.n.dataset.id, after: false };
    }
    return { id: row[row.length - 1].n.dataset.id, after: true };
  }

  // 松手时统一在这里决定落点：落在文件夹卡片里 → 收进文件夹；否则按位置插到某图标前/后
  async function applyDrop(id, node, x, y) {
    const moved = links.find((i) => i.id === id);
    if (!moved) return;
    const from = moved.pid; // 从文件夹里拖出来的，源文件夹要缩回
    const grid = $("grid");
    const card = [...grid.querySelectorAll(".group-card")].find((c) => {
      if (c === node || c.dataset.id === id) return false;
      const r = c.getBoundingClientRect();
      return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    });
    if (card) {
      const gid = card.dataset.id;
      if (moved.type === "component") {
        const r = card.getBoundingClientRect();
        moveIcon(id, gid, x > r.left + r.width / 2); // 文件夹拖到文件夹 = 换位置，不嵌套
      } else {
        addToGroup(id, gid); // 内部已 render
      }
    } else {
      const slot = findDropSlot(node, x, y);
      if (!slot) {
        if (from) shrinkGroup(links.find((i) => i.id === from));
        moveIconToEnd(id); // 内部已 render + save
        return;
      }
      moveIcon(id, slot.id, slot.after);
    }
    if (from) shrinkGroup(links.find((i) => i.id === from));
    render();
    await saveLinks();
  }

  // 拖拽结束（松手、按 Esc、拖到窗口外都会触发）：统一按指针位置落位
  // 之前每个元素各写一份 drop 逻辑，落在没绑 drop 的区域就完全没反应 → 现在只认 dragend
  function finishDrag(e) {
    const id = dragId;
    const node = dragNode;
    dragId = null;
    dragNode = null;
    markDragging(false);
    // 清掉可能残留的高亮（拖到 dock 栏/垃圾篓时 drop 会先清 dragNode，这里按 DOM 兜底）
    $("grid").querySelectorAll(".dragging").forEach((el) => el.classList.remove("dragging"));
    $("grid").querySelectorAll(".group-card.drop-in").forEach((c) => c.classList.remove("drop-in"));
    if (!id) return;
    const x = (e && e.clientX) || (lastXY && lastXY.x) || 0;
    const y = (e && e.clientY) || (lastXY && lastXY.y) || 0;
    lastXY = null;
    if (!x && !y) { render(); return; } // Esc 取消：把让位动过的 DOM 还原
    applyDrop(id, node, x, y).catch(() => {});
  }

  /* ---------- 文件夹卡片（iconGroup）：矩形卡片，拖入图标自动变大 ---------- */
  function groupCard(item) {
    const card = document.createElement("div");
    card.className = "group-card";
    card.dataset.id = item.id;
    const kids = childrenOf(item.id).sort((a, b) => (a.sort || 0) - (b.sort || 0));
    // 尺寸至少 2x2；子项装不下时按 2x2→2x3→3x3→3x4… 自动长大（渲染时也算一遍，
    // 这样历史数据里尺寸偏小的文件夹也会被撑开）
    const [rows, cols] = fitSize(item.size, kids.length).split("x").map(Number);
    card.style.setProperty("--spanr", rows);
    card.style.setProperty("--spanc", cols);

    // 卡片本体（圆角矩形）+ 下方名称，名称与桌面图标下的名称同样处理
    const box = document.createElement("div");
    box.className = "group-box";
    const name = document.createElement("div");
    name.className = "group-name";
    name.textContent = item.name || "文件夹";

    const inner = document.createElement("div");
    inner.className = "group-inner";
    kids.forEach((k) => {
        const tile = document.createElement("a");
        tile.className = "gicon";
        tile.href = k.url || "#";
        tile.target = openType.linkOpen === false ? "_self" : "_blank";
        tile.rel = "noopener";
        tile.dataset.id = k.id;
        tile.title = k.name || "";
        if (k.src) {
          tile.innerHTML = `<img src="${k.src}" alt="" loading="lazy" onerror="this.remove()">`;
        } else {
          const s = document.createElement("span");
          s.className = "letter";
          s.textContent = (k.name || "?").trim().charAt(0);
          tile.appendChild(s);
        }
        inner.appendChild(tile);
        if (S.loggedIn) {
          // 卡片里的图标也能拖：拖到网格里的图标上 = 换位/移出，拖到别的卡片 = 换文件夹
          tile.draggable = true;
          tile.addEventListener("dragstart", (ev) => {
            dragId = String(k.id);
            dragNode = tile;
            lastXY = null;
            ev.dataTransfer.setData("text/plain", String(k.id));
            ev.dataTransfer.effectAllowed = "move";
            markDragging(true);
            tile.classList.add("dragging");
            ev.stopPropagation();
          });
          tile.addEventListener("dragend", (ev) => {
            ev.stopPropagation();
            finishDrag(ev);
          });
        }
      });
    box.appendChild(inner);
    card.appendChild(box);
    card.appendChild(name);

    card.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openCtx(item, e);
    });

    if (S.loggedIn) {
      // 卡片本身可拖动换位置（靠其它图标的 dragover 计算落点）
      card.draggable = true;
      card.addEventListener("dragstart", (e) => {
        dragId = item.id;
        dragNode = card;
        lastXY = null;
        e.dataTransfer.setData("text/plain", item.id);
        e.dataTransfer.effectAllowed = "move";
        markDragging(true);
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", (e) => finishDrag(e));
      // 悬停时只做让位预览（落点以下一节的 findDropSlot 为准）
      card.addEventListener("dragover", (e) => {
        if (!dragId || dragId === item.id) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "move";
        lastXY = { x: e.clientX, y: e.clientY };
        const dragged = links.find((i) => i.id === dragId);
        if (dragged && dragged.type === "component") {
          const r = card.getBoundingClientRect();
          shiftIcons(card, e.clientX > r.left + r.width / 2);
        } else {
          card.classList.add("drop-in");
        }
      });
      card.addEventListener("dragleave", () => card.classList.remove("drop-in"));
    }
    return card;
  }

  // 把图标收进文件夹卡片；容量不够时卡片自动增大
  function addToGroup(itemId, groupId) {
    const moved = links.find((i) => i.id === itemId);
    const g = links.find((i) => i.id === groupId);
    if (!moved || !g || moved.pid === g.id) return;
    if (moved.type === "component") return; // 不把文件夹塞进文件夹
    const from = moved.pid; // 从一个文件夹拖到另一个：源文件夹要缩回
    moved.pid = g.id;
    moved.pageGroup = g.pageGroup || "";
    const kids = childrenOf(g.id).filter((k) => k.id !== moved.id);
    moved.sort = kids.length ? Math.max(...kids.map((k) => k.sort || 0)) + 10 : 0;
    g.size = fitSize(g.size, kids.length + 1);
    if (from && from !== g.id) shrinkGroup(links.find((i) => i.id === from));
    render();
  }

  // 卡片高度 = 卡片外同等行数的高度（含图标下方名称）；行高实测，免得跟字号跑偏
  function sizeCards() {
    const grid = $("grid");
    const sample = grid.querySelector(".icon");
    const rowH = sample ? sample.getBoundingClientRect().height : 64 + 27.5;
    const gap = parseFloat(getComputedStyle(grid).rowGap) || 0;
    grid.querySelectorAll(".group-card").forEach((card) => {
      const r = parseInt(card.style.getPropertyValue("--spanr"), 10) || 2;
      card.style.height = Math.round(rowH * r + gap * (r - 1)) + "px";
      const box = card.querySelector(".group-box");
      const inner = card.querySelector(".group-inner");
      if (!box || !inner) return;
      // 间距全部交给 CSS 的 space-evenly；这里只清掉旧的横向间距变量
      card.style.removeProperty("--pad");
      inner.style.rowGap = "";
    });
  }

  function applyScheme() {
    // 用 theme 别名：saveSettings 后 S.config 会被换成新对象，读 S.config.theme 会拿到旧值
    const cs = theme.colorScheme === "light" || theme.colorScheme === "dark"
      ? theme.colorScheme
      : (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    document.documentElement.setAttribute("data-color-scheme", cs);
  }

  function render() {
    applyScheme();
    const grid = $("grid");
    grid.classList.remove("slide-up", "slide-down");
    grid.innerHTML = "";
    const items = links
      .filter((i) => !isChild(i) && (i.pageGroup || "") === activePage)
      .sort((a, b) => (a.sort || 0) - (b.sort || 0));
    items.forEach((i, idx) => {
      const node = i.type === "component" ? groupCard(i) : iconNode(i);
      node.style.animationDelay = Math.min(idx, 14) * 18 + "ms";
      grid.appendChild(node);
    });

    $("empty").hidden = items.length > 0;
    sizeCards();
    // 首帧列宽可能还没定下来（会算出偏大的留白），布局稳定后再量一次
    requestAnimationFrame(sizeCards);

    if (dirNext) {
      void grid.offsetWidth; // 强制重排，让动画能重复播放
      grid.classList.add(dirNext === "up" ? "slide-up" : "slide-down");
      dirNext = null;
    }

    renderTabbar();
    renderSide();
  }

  /* ---------- 分类切换（记住上次分类，同源项目 theme.latestPageGroup） ---------- */
  function goPage(p) {
    const list = [""].concat(S.pageGroups || []);
    const from = list.indexOf(activePage);
    const to = list.indexOf(p);
    dirNext = to === from ? null : to > from ? "up" : "down";
    activePage = p;
    theme.latestPageGroup = p;
    post("/config/update", { config: S.config });
    render();
  }

  /* ---------- 左侧分类导航条 ---------- */
  async function saveGroups() {
    const next = Object.assign({}, S.config, { pageGroups: S.pageGroups || [] });
    S.config = next;
    const res = await post("/config/update", { config: next });
    if (res.code !== 1) toast(res.msg || "保存失败");
    return res.code === 1;
  }

  const ICON_HOME = '<svg viewBox="0 0 24 24"><path d="M12 3 2 11h3v10h5v-6h4v6h5V11h3z"/></svg>';
  const ICON_FOLDER = '<svg viewBox="0 0 24 24"><path d="M3 5h6l2 2h10v12H3z"/></svg>';

  // 新建分类时可选的预制图标
  const GROUP_ICONS = {
    folder: ICON_FOLDER,
    star: '<svg viewBox="0 0 24 24"><path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/></svg>',
    bookmark: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
    heart: '<svg viewBox="0 0 24 24"><path d="M12 21s-7-4.4-9-8a5 5 0 0 1 9-3 5 5 0 0 1 9 3c-2 3.6-9 8-9 8z"/></svg>',
    briefcase: '<svg viewBox="0 0 24 24"><path d="M9 4h6v3h5v13H4V7h5zM11 6v1h2V6z"/></svg>',
    code: '<svg viewBox="0 0 24 24"><path d="M8 6l-5 6 5 6 1.5-1.4L5.6 12l3.9-4.6zM16 6l5 6-5 6-1.5-1.4L18.4 12l-3.9-4.6z"/></svg>',
    music: '<svg viewBox="0 0 24 24"><path d="M9 18a3 3 0 1 1-2-2.8V5l10-2v11a3 3 0 1 1-2-2.8V6.2L9 8z"/></svg>',
    globe: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2c1.7 0 3.2 2.7 3.2 6s-1.5 6-3.2 6-3.2-2.7-3.2-6S10.3 4 12 4zM4 11h16v2H4z"/></svg>',
    home: '<svg viewBox="0 0 24 24"><path d="M12 3 2 11h3v10h5v-6h4v6h5V11h3z"/></svg>',
    book: '<svg viewBox="0 0 24 24"><path d="M3 4h8v16H3zM13 4h8v16h-8z"/></svg>',
    gift: '<svg viewBox="0 0 24 24"><path d="M3 8h18v4H3zM5 12h14v9H5z"/><path d="M11 3.5A2.5 2.5 0 1 0 8.5 6H11zM13 3.5A2.5 2.5 0 1 1 15.5 6H13z"/></svg>',
    cloud: '<svg viewBox="0 0 24 24"><path d="M6.5 18a4.5 4.5 0 0 1-.3-9 5.5 5.5 0 0 1 10.4-1.6A4.5 4.5 0 0 1 17.5 18z"/></svg>',
    sun: '<svg viewBox="0 0 24 24"><path d="M11 2h2v3h-2zM11 19h2v3h-2zM2 11h3v2H2zM19 11h3v2h-3zM4.2 5.6l1.4-1.4 2.1 2.1-1.4 1.4zM16.3 17.7l1.4-1.4 2.1 2.1-1.4 1.4zM4.2 18.4l2.1-2.1 1.4 1.4-2.1 2.1zM16.3 6.3l2.1-2.1 1.4 1.4-2.1 2.1z"/><path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"/></svg>',
    moon: '<svg viewBox="0 0 24 24"><path d="M13.5 2a9.5 9.5 0 1 0 8.5 13.8A8 8 0 0 1 13.5 2z"/></svg>',
    bolt: '<svg viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 10-12h-6z"/></svg>',
    plane: '<svg viewBox="0 0 24 24"><path d="M2 13.5 21 4l-6 8.5 1.5 7-4-4.2-3.6 2.8 1-4.2z"/></svg>',
    rocket: '<svg viewBox="0 0 24 24"><path d="M12 2c3 3 4.5 6.2 4.5 9.5L14 15H10l-2.5-3.5C7.5 8.2 9 5 12 2zM10 16h4l-2 6zM6.5 13 3 19l4.5-1.5zM17.5 13 21 19l-4.5-1.5z"/></svg>',
    coffee: '<svg viewBox="0 0 24 24"><path d="M4 8h12v7a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4zM17 9.5h2a2.5 2.5 0 0 1 0 5h-2z"/></svg>',
    shield: '<svg viewBox="0 0 24 24"><path d="M12 2 20 5v7c0 5-4 8-8 10-4-2-8-5-8-10V5z"/></svg>',
    flag: '<svg viewBox="0 0 24 24"><path d="M5 3h2v18H5zM8 4h11l-3 4 3 4H8z"/></svg>',
    pin: '<svg viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7zm0 4.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z"/></svg>',
    leaf: '<svg viewBox="0 0 24 24"><path d="M4 20C4 10 10 4 20 4c0 10-6 16-16 16z"/></svg>',
    tag: '<svg viewBox="0 0 24 24"><path fill-rule="evenodd" d="M3 3h9l9 9-9 9-9-9zm4.5 3a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z"/></svg>',
    box: '<svg viewBox="0 0 24 24"><path d="M12 2 21 7v10l-9 5-9-5V7z"/></svg>',
    play: '<svg viewBox="0 0 24 24"><path d="M8 4l12 8-12 8z"/></svg>',
  };
  // 主面板前 24 个之外的「更多」图标：50 个，不与上面 24 个重复，自身也不重复
  const GROUP_ICONS_ZH = {
    folder: "文件夹", star: "星标", bookmark: "书签", heart: "收藏",
    briefcase: "工作", code: "代码", music: "音乐", globe: "地球",
    home: "主页", book: "书籍", gift: "礼物", cloud: "云",
    sun: "太阳", moon: "月亮", bolt: "闪电", plane: "飞机",
    rocket: "火箭", coffee: "咖啡", shield: "盾牌", flag: "旗帜",
    pin: "图钉", leaf: "叶子", tag: "标签", box: "盒子", play: "播放",
    bell: "铃铛", chat: "聊天", mail: "邮箱", paper: "文档",
    clip: "附件", cam: "相机", mic: "麦克风", video: "视频",
    link: "链接", search: "搜索", gear: "设置", user: "用户",
    users: "群组", clock: "时钟", cal: "日历", chart: "图表",
    chart2: "趋势", pie: "饼图", grid: "网格", list: "列表",
    filter: "筛选", fun: "菜单", check: "对勾", cross: "关闭",
    plus: "添加", minus: "减少", minus2: "双横线", up: "上移",
    down: "下移", left: "左移", right: "右移", reload: "刷新",
    share: "分享", dl: "下载", ul: "上传", eye: "查看",
    key: "钥匙", lock: "锁定", unlock: "解锁", save: "保存",
    folder2: "新文件夹", archive: "归档", zip: "压缩包", db: "数据库",
    server: "服务器", cpu: "芯片", phone: "手机", wifi: "网络",
    bat: "电池", card: "卡片", tv: "电视", game: "游戏",
    travel: "旅行", cup: "咖啡杯", net: "互联", camera: "照相机",
    ticket: "票据", note: "记事", ball: "球类", printer: "打印机",
  };
  const GROUP_ICONS_MORE = {
    bell: '<svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 18a2 2 0 0 0 4 0z"/></svg>',
    chat: '<svg viewBox="0 0 24 24"><path d="M4 4h16v12H8l-4 4z"/></svg>',
    mail: '<svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zm2 2 7 5 7-5"/></svg>',
    paper: '<svg viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6z"/><path d="M15 2v4h4"/></svg>',
    clip: '<svg viewBox="0 0 24 24"><path d="M9 4h6l-1 5h4l-7 11-3-9z"/></svg>',
    cam: '<svg viewBox="0 0 24 24"><path d="M4 8h4l2-2h4l2 2h4v12H4z"/><circle cx="12" cy="14" r="3"/></svg>',
    mic: '<svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/></svg>',
    video: '<svg viewBox="0 0 24 24"><path d="M3 6h12v12H3zM15 10l6-3v10l-6-3z"/></svg>',
    link: '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
    search: '<svg viewBox="0 0 24 24"><path d="M10 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12zM15 15l5 5"/></svg>',
    gear: '<svg viewBox="0 0 24 24"><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/></svg>',
    user: '<svg viewBox="0 0 24 24"><path d="M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM4 20a8 8 0 0 1 16 0z"/></svg>',
    users: '<svg viewBox="0 0 24 24"><path d="M8 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM3 19a5 5 0 0 1 10 0M16 6a3 3 0 1 1 0 5M15 19a5 5 0 0 0-2-4"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><path d="M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8v4l3 2"/></svg>',
    cal: '<svg viewBox="0 0 24 24"><path d="M4 6h16v14H4zM4 10h16M8 4v4M16 4v4"/></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M4 20V9h2.5V20zM10 20V4h2.5v16zM16 20v-7h2.5v7zM4 20h16v2.5H4z"/></svg>',
    chart2: '<svg viewBox="0 0 24 24"><path d="M4 18l5-6 4 4 5-8 2 1.5-5 8-4-4-5 6z"/><path d="M4 21h16v1.5H4z"/></svg>',
    pie: '<svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M14 3.5A9 9 0 0 1 20.5 14H14z"/></svg>',
    grid: '<svg viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>',
    list: '<svg viewBox="0 0 24 24"><path d="M8 5h12v3H8zM8 10.5h12v3H8zM8 16h12v3H8zM4 5.5h2v2H4zM4 11h2v2H4zM4 16.5h2v2H4z"/></svg>',
    filter: '<svg viewBox="0 0 24 24"><path d="M3 5h18l-7 8v6l-4 2v-8z"/></svg>',
    fun: '<svg viewBox="0 0 24 24"><path d="M4 5h16v3H4zM7 10.5h10v3H7zM10 16h4v3h-4z"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M9.5 18.2 3 11.7l2-2 4.5 4.5L19 5.5 21 7.5z"/></svg>',
    cross: '<svg viewBox="0 0 24 24"><path d="M7 6l2-2 3 3 3-3 2 2-3 3 3 3-2 2-3-3-3 3-2-2 3-3z"/></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M10.5 4h3v6.5H20v3h-6.5V20h-3v-6.5H4v-3h6.5z"/></svg>',
    minus: '<svg viewBox="0 0 24 24"><path d="M5 10h14v4H5z"/></svg>',
    minus2: '<svg viewBox="0 0 24 24"><path d="M4 8h16v3H4zM4 14h16v3H4z"/></svg>',
    up: '<svg viewBox="0 0 24 24"><path d="M12 5l7 8h-4v6H9v-6H5z"/></svg>',
    down: '<svg viewBox="0 0 24 24"><path d="M12 19l-7-8h4V5h6v6h4z"/></svg>',
    left: '<svg viewBox="0 0 24 24"><path d="M19 12l-8 7V6z"/></svg>',
    right: '<svg viewBox="0 0 24 24"><path d="M5 12l8-7v14z"/></svg>',
    reload: '<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 6.3M20 5v6h-6"/></svg>',
    share: '<svg viewBox="0 0 24 24"><path d="M6 12v8h12v-8M12 3v12M8 7l4-4 4 4"/></svg>',
    dl: '<svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>',
    ul: '<svg viewBox="0 0 24 24"><path d="M12 15V3M7 10l5-5 5 5M5 21h14"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 19 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    key: '<svg viewBox="0 0 24 24"><path d="M8 12a4 4 0 1 0 8 0 4 4 0 0 0-8 0zM14 12h6v4h-4v3h-2z"/></svg>',
    lock: '<svg viewBox="0 0 24 24"><path d="M7 10V7a5 5 0 0 1 10 0v3M6 10h12v10H6z"/></svg>',
    unlock: '<svg viewBox="0 0 24 24"><path d="M7 10V7a5 5 0 0 1 9.5-2M6 10h12v10H6z"/></svg>',
    save: '<svg viewBox="0 0 24 24"><path d="M5 3h12l4 4v14H5zM8 3v5h7V3M8 14h8v6H8z"/></svg>',
    folder2: '<svg viewBox="0 0 24 24"><path d="M3 6h7l2 2h9v12H3z"/></svg>',
    archive: '<svg viewBox="0 0 24 24"><path d="M4 4h16v4H4zM5 8h14v12H5zM10 12h4v4h-4z"/></svg>',
    zip: '<svg viewBox="0 0 24 24"><path d="M4 5h16v14H4zM8 3v4M12 3v4M16 3v4"/></svg>',
    db: '<svg viewBox="0 0 24 24"><path d="M5 4h14v4H5zM5 10h14v4H5zM5 16h14v4H5z"/></svg>',
    server: '<svg viewBox="0 0 24 24"><path d="M4 5h16v6H4zM4 13h16v6H4zM7 8h1M7 16h1"/></svg>',
    cpu: '<svg viewBox="0 0 24 24"><path d="M8 8h8v8H8zM4 10h4M4 14h4M16 10h4M16 14h4M10 4v4M14 4v4M10 16v4M14 16v4"/></svg>',
    phone: '<svg viewBox="0 0 24 24"><path d="M5 4h4l2 5-2 2a12 12 0 0 0 6 6l2-2 5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>',
    wifi: '<svg viewBox="0 0 24 24"><path d="M2 8a15 15 0 0 1 20 0M5.5 11.5A10 10 0 0 1 18.5 11.5M9 15a5 5 0 0 1 6 0M12 19h.01"/></svg>',
    bat: '<svg viewBox="0 0 24 24"><path d="M4 8h13v8H4z"/><path d="M17 10h3v4h-3z"/><path d="M6 10h3v4H6z"/><path d="M11 10h3v4h-3z"/></svg>',
    card: '<svg viewBox="0 0 24 24"><path d="M3 5h18v14H3zM3 10h18M7 15h4"/></svg>',
    tv: '<svg viewBox="0 0 24 24"><path d="M3 6h18v12H3zM3 18h18M9 3l2 3M15 3l-2 3"/></svg>',
    game: '<svg viewBox="0 0 24 24"><path d="M8 4h8a5 5 0 0 1 5 5v2a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5V9a5 5 0 0 1 5-5z"/><circle cx="8.5" cy="10" r="1.5"/><circle cx="15.5" cy="10" r="1.5"/></svg>',
    travel: '<svg viewBox="0 0 24 24"><path d="M12 3l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6z"/><circle cx="12" cy="10" r="2"/></svg>',
    cup: '<svg viewBox="0 0 24 24"><path d="M5 5h11v8a5 5 0 0 1-5 5H9a5 5 0 0 1-4-4zM16 7h2a3 3 0 0 1 0 6h-2"/></svg>',
    net: '<svg viewBox="0 0 24 24"><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><circle cx="12" cy="6" r="3"/><path d="M12 9v3M9.5 15.5L7 17.5M14.5 15.5L17 17.5"/></svg>',
    camera: '<svg viewBox="0 0 24 24"><path d="M4 8h4l2-2h4l2 2h4v12H4zM9 3h6v3H9z"/><circle cx="12" cy="13" r="3"/></svg>',
    ticket: '<svg viewBox="0 0 24 24"><path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/><path d="M13 6v12"/></svg>',
    note: '<svg viewBox="0 0 24 24"><path d="M9 3v18H7a3 3 0 0 1 0-6h2zM15 3v18h2a3 3 0 0 0 0-6h-2zM9 6h6v6H9z"/></svg>',
    ball: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3c4 3 4 15 0 18M3.5 9h17M3.5 15h17"/></svg>',
    printer: '<svg viewBox="0 0 24 24"><path d="M7 3h10v5H7zM4 8h16v7H4zM8 15h8v6H8z"/></svg>',
  };
  let groupIcon = "folder";
  let _prevGroupIcon = "folder";

  const groupIconOf = (g) => ((S.config && S.config.groupIcons) || {})[g] || "folder";

  function renderSide() {
    const list = $("sideList");
    if (!list) return;
    list.innerHTML = "";
    const add = $("sideAdd");
    if (add) add.hidden = !S.loggedIn;
    const groupList = theme.pageGroup === false ? [] : (S.pageGroups || []);
    (S.loggedIn ? [""].concat(groupList) : [""]).forEach((g) => {
      const row = document.createElement("div");
      row.className = "side-item" + (g === activePage ? " on" : "");
      if (g) row.dataset.group = g;
      const name = document.createElement("button");
      name.type = "button";
      name.className = "side-name";
      name.title = g || "主页";
      name.innerHTML = '<span class="side-ico">' + (g ? (GROUP_ICONS[groupIconOf(g)] || GROUP_ICONS_MORE[groupIconOf(g)] || ICON_FOLDER) : ICON_HOME) + '</span><span class="side-label"></span>';
      name.querySelector(".side-label").textContent = g || "主页";
      name.onclick = () => goPage(g);
      row.appendChild(name);
      if (g) {
        const ops = document.createElement("span");
        ops.className = "side-ops";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "side-op";
        edit.textContent = "✎";
        edit.title = "重命名";
        edit.onclick = (e) => {
          e.stopPropagation();
          renameGroup(g);
        };
        const del = document.createElement("button");
        del.type = "button";
        del.className = "side-op";
        del.textContent = "✕";
        del.title = "删除";
        del.onclick = (e) => {
          e.stopPropagation();
          deleteGroup(g);
        };
        ops.append(edit, del);
        row.appendChild(ops);
        name.addEventListener("contextmenu", (ev) => {
          if (!S.loggedIn) return;
          ev.preventDefault();
          openCtxGroup2(g, ev);
        });
      }
      list.appendChild(row);
    });
  }

  const GROUP_ICON_SHOW = 24; // 主面板展示前 24 个，第 25 格是「更多」按钮

  function renderGroupIcons() {
    const box = $("groupIcons");
    const moreBox = $("groupIconsMore");
    const morePop = $("groupMorePop");
    if (!box || !moreBox || !morePop) return;
    box.innerHTML = "";
    moreBox.innerHTML = "";
    morePop.hidden = true;
    const keys = Object.keys(GROUP_ICONS);
    keys.slice(0, GROUP_ICON_SHOW).forEach((k) => box.appendChild(groupIconBtn(k, GROUP_ICONS)));
    box.appendChild(groupMoreBtn(morePop));
    Object.keys(GROUP_ICONS_MORE).forEach((k) => moreBox.appendChild(groupIconBtn(k, GROUP_ICONS_MORE)));
  }

  function groupIconBtn(k, dict) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pop-ico" + (k === groupIcon ? " on" : "");
    b.title = GROUP_ICONS_ZH[k] || k;
    b.innerHTML = dict[k];
    b.setAttribute("data-ico", "1");
    b.onclick = (e) => {
      e.stopPropagation();
      // 移除所有图标的 on 类
      document.querySelectorAll('.pop-ico.on').forEach((el) => el.classList.remove('on'));
      b.classList.add('on');
      groupIcon = k;
      // 实时更新左侧栏对应分类的图标
      const editName = $("groupPop").dataset.edit || "";
      if (editName) {
        const sideItem = document.querySelector('.side-item[data-group="' + editName + '"] .side-name .side-ico');
        if (sideItem) sideItem.innerHTML = dict[k] || GROUP_ICONS[k] || ICON_FOLDER;
      }
    };
    return b;
  }

  function groupMoreBtn(morePop) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pop-more";
    b.title = "更多图标";
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>';
    b.onclick = (e) => {
      e.stopPropagation();
      // 忽略来自图标按钮的冒泡点击
      if (e.target.closest('[data-ico]')) return;
      const pop = $("groupPop");
      const more = $("groupMorePop");
      if (!more.hidden) { more.hidden = true; return; }
      // 位置：叠在主弹窗的图标区附近（主弹窗 right/top 已知）
      const r = pop.getBoundingClientRect();
      more.style.left = r.right - more.offsetWidth + "px";
      more.style.top = r.top + 20 + "px";
      more.hidden = false;
      // 再点「更多」按钮可关闭
    };
    return b;
  }

  function openGroupPop(editName, triggerY) {
    const pop = $("groupPop");
    if (!pop) return;
    editName = editName || "";
    pop.dataset.edit = editName;
    $("popGroupTitle").textContent = editName ? "编辑分类" : "新建分类";
    $("groupCreate").textContent = editName ? "保存" : "创建";
    $("groupName").value = editName;
    $("groupName").focus();
    _prevGroupIcon = groupIcon = editName ? groupIconOf(editName) : "folder";
    renderGroupIcons();
    pop.hidden = false;
    // left 统一贴左侧栏右边；top 跟随触发位置（点击/右键点），clamp 到视口
    const side = $("side");
    const anchorR = side ? side.getBoundingClientRect().right : 64;
    const w = pop.offsetWidth || 240;
    const h = pop.offsetHeight || 260;
    pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, anchorR + 10)) + "px";
    const y = triggerY || (typeof pageYOffset !== "undefined" ? pageYOffset : 120);
    pop.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, y)) + "px";
  }

  async function saveGroup() {
    const editName = $("groupPop").dataset.edit || "";
    const name = $("groupName").value.trim();
    if (!name) return toast("请填写分类名称");
    if (name.length > 12) return toast("分类名称不能超过 12 个字");
    if ((S.pageGroups || []).includes(name) && name !== editName) return toast("分类已存在");
    const icons = Object.assign({}, (S.config && S.config.groupIcons) || {});
    icons[name] = groupIcon;
    if (editName && editName !== name) delete icons[editName];
    S.config.groupIcons = icons;
    if (editName) {
      S.pageGroups = (S.pageGroups || []).map((g) => (g === editName ? name : g));
      links.forEach((i) => { if ((i.pageGroup || "") === editName) i.pageGroup = name; });
      await saveGroups();
      await saveLinks();
      if (activePage === editName) goPage(name); else render();
    } else {
      S.pageGroups = (S.pageGroups || []).concat(name);
      await saveGroups();
      goPage(name);
    }
    const gp = $("groupPop");
    gp.hidden = true;
    const gm = $("groupMorePop");
    if (gm) gm.hidden = true;
  }

  function renameGroup(oldName, y) {
    openGroupPop(oldName, y);
  }

  function deleteGroup(name) {
    confirmBox("删除分类「" + name + "」？其中的标签会移回主页", async () => {
      S.pageGroups = (S.pageGroups || []).filter((g) => g !== name);
      const icons = Object.assign({}, (S.config && S.config.groupIcons) || {});
      delete icons[name];
      S.config.groupIcons = icons;
      links.forEach((i) => {
        if ((i.pageGroup || "") === name) i.pageGroup = "";
      });
      await saveGroups();
      await saveLinks();
      if (activePage === name) {
        goPage("");
        return;
      }
      render();
    });
  }

  function renderTabbar() {
    const bar = $("tabbar");
    const tabs = (Array.isArray(S.tabbar) ? S.tabbar : [])
      .filter((t) => !t.pid)
      .sort((a, b) => (a.sort || 0) - (b.sort || 0));
    if (!theme.tabbar || !tabs.length) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    bar.innerHTML = "";
    tabs.forEach((t) => {
      const a = document.createElement("a");
      a.className = "tab";
      a.href = t.url || "#";
      if ((t.url || "").startsWith("tab://")) {
        a.onclick = (e) => {
          e.preventDefault();
          if (t.url === "tab://setting") openSettings();
          else toast("该功能暂未实现：" + t.url);
        };
      } else {
        a.target = openType.linkOpen === false ? "_self" : "_blank";
      }
      a.title = t.name || "";
      a.dataset.id = String(t.id);
      const letter = (t.name || "?").trim().charAt(0) || "?";
      a.innerHTML = (t.src
        ? `<img src="${t.src}" alt="" onerror="this.remove()">`
        : `<i class="tab-letter">${letter}</i>`) + `<span>${t.name || ""}</span>`;
      a.draggable = true;
      a.addEventListener("dragstart", (e) => {
        dockDrag = { id: String(t.id), node: a };
        dockAt = null;
        e.dataTransfer.setData("text/plain", String(t.id));
        e.dataTransfer.effectAllowed = "move";
        a.classList.add("dragging");
      });
      a.addEventListener("dragend", () => {
        dockDrag = null;
        dockAt = null;
        a.classList.remove("dragging");
      });
      // 拖动排序：悬停时图标就地让位（与桌面图标一致），松手后写回 tabbar
      a.addEventListener("dragover", (e) => {
        if (!dockDrag || dockDrag.id === String(t.id)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        const r = a.getBoundingClientRect();
        const after = e.clientX > r.left + r.width / 2;
        dockAt = { id: String(t.id), after };
        shiftInto(bar, dockDrag.node, a, after, ".tab");
      });
      a.addEventListener("drop", async (e) => {
        if (!dockDrag || !dockAt) return;
        e.preventDefault();
        dockDrag = null;
        dockAt = null;
        // 以拖放后的 DOM 顺序为准重排 sort，避免 sort 中间值算错
        const ids = [...bar.querySelectorAll(".tab")].map((x) => x.dataset.id);
        const all = Array.isArray(S.tabbar) ? S.tabbar : (S.tabbar = []);
        const tops = ids.map((id) => all.find((x) => String(x.id) === id)).filter(Boolean);
        if (!tops.length) return render();
        tops.forEach((x, i) => {
          x.sort = i * 10;
        });
        const res = await post("/tabbar/update", { tabbar: S.tabbar });
        if (res.code !== 1) toast(res.msg || "保存失败");
        else toast("顺序已保存");
        render();
      });
      bar.appendChild(a);
    });

    // 分隔线 + 垃圾桶：把 dock 图标拖到垃圾桶即可移除
    const sep = document.createElement("span");
    sep.className = "tab-sep";
    bar.appendChild(sep);

    // 把桌面图标拖入 dock 栏（接收 dragId，非 dockDrag）
    bar.addEventListener("dragover", (e) => {
      if (!dragId || dockDrag) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      bar.classList.add("drop-in");
    });
    bar.addEventListener("dragleave", () => bar.classList.remove("drop-in"));
    bar.addEventListener("drop", async (e) => {
      e.preventDefault();
      bar.classList.remove("drop-in");
      const id = dragId;
      dragId = null;
      dragNode = null;
      if (!id) return;
      const item = links.find((x) => String(x.id) === id);
      if (!item || !item.url || item.type === "component") return;
      const tabs = Array.isArray(S.tabbar) ? S.tabbar : (S.tabbar = []);
      if (tabs.some((t) => t.url === item.url)) return toast("已在 dock 栏中");
      const maxSort = tabs.length ? Math.max(...tabs.map((t) => t.sort || 0)) : -10;
      tabs.push({
        id: uuid(), pid: null, name: item.name || item.url, url: item.url,
        src: item.src || "", sort: maxSort + 10,
      });
      const res = await post("/tabbar/update", { tabbar: tabs });
      if (res.code !== 1) return toast(res.msg || "保存失败");
      toast("已加入 dock 栏");
      S.tabbar = tabs;
      render();
    });

    const trash = document.createElement("button");
    trash.type = "button";
    trash.className = "tab-trash";
    trash.title = "把图标拖到这里移除";
    trash.innerHTML =
      '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16"/><path d="M10 4h4"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/></svg>';
    trash.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      trash.classList.add("over");
    });
    trash.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      trash.classList.remove("over");
      const droppedId = e.dataTransfer.getData("text/plain");
      const isDockTab = dockDrag && String(dockDrag.id) === String(droppedId);
      if (isDockTab) {
        const before = S.tabbar.length;
        S.tabbar = S.tabbar.filter((x) => String(x.id) !== dockDrag.id && String(x.pid) !== dockDrag.id);
        if (S.tabbar.length === before) return;
        const res = await post("/tabbar/update", { tabbar: S.tabbar });
        if (res.code !== 1) {
          toast(res.msg || "保存失败");
          return;
        }
        toast("已从 dock 栏移除");
        render();
        return;
      }
      const id = dragId;
      dragId = null;
      dragNode = null;
      if (!id) return;
      const item = links.find((x) => String(x.id) === id);
      if (!item) return;
      // 卡片 = 连同里面的图标一起删除；普通图标 = 只删自己
      const wasGroup = item.type === "component";
      confirmBox(
        wasGroup ? "删除该文件夹会连同里面的所有图标一起删除，确定？" : "确定删除这个图标？",
        async () => {
          links = links.filter((i) => i.id !== id && i.pid !== id);
          normalizeSort();
          render();
          const res = await post("/link/update", { link: links });
          if (res.code !== 1) {
            toast(res.msg || "保存失败");
            return;
          }
          toast("已删除");
        }
      );
    });
    bar.appendChild(trash);
  }

  /* ---------- 编辑 ---------- */
  const BG_PALETTE = ["#4f8cff", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#84cc16", "#64748b", "#f97316", "#14b8a6", "#eab308"];

  function setEditorBg(v) {
    const f = $("editorForm");
    const hex = (v || "").trim();
    f.bgColor.value = hex;
    const sw = $("editorColor");
    if (!sw) return;
    sw.classList.toggle("empty", !hex);
    sw.style.opacity = hex ? "1" : ".35";
    sw.title = hex || "未设置底色";
    const hexText = $("editorHex");
    if (hexText) hexText.textContent = hex ? hex.toUpperCase() : "未设置";
    if (/^#[0-9a-f]{6}$/i.test(hex)) sw.value = hex;
    else if (/^#[0-9a-f]{3}$/i.test(hex)) sw.value = "#" + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
    const box = $("editorPalette");
    if (box) box.querySelectorAll("button").forEach((b) => b.classList.toggle("on", (b.title || "").toLowerCase() === hex.toLowerCase() && !!hex));
  }

  function editorPrev() {
    const f = $("editorForm");
    const v = f.src.value.trim();
    const img = $("editorPrevImg");
    const txt = $("editorPrevText");
    txt.textContent = (f.elements.name.value || "?").trim().slice(0, 1) || "?";
    if (v) {
      img.src = v;
      img.hidden = false;
      txt.hidden = true;
    } else {
      img.hidden = true;
      img.removeAttribute("src");
      txt.hidden = false;
    }
  }

  function renderPalette() {
    const box = $("editorPalette");
    if (!box) return;
    const cur = ($("editorForm").elements.bgColor.value || "").toLowerCase();
    box.innerHTML = "";
    BG_PALETTE.forEach((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.style.background = c;
      b.title = c;
      b.className = c.toLowerCase() === cur ? "on" : "";
      b.onclick = (e) => {
        e.stopPropagation();
        setEditorBg(c);
      };
      box.appendChild(b);
    });
    // 调色板最后一格是吸管（取屏上任意颜色），不再单独放「探针」按钮
    const eye = document.createElement("button");
    eye.type = "button";
    eye.className = "eye";
    eye.title = "吸管取色";
    eye.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 3l2 2-8 8-3 3-3 1 1-3z"/><path d="M15 7l2 2"/></svg>';
    eye.onclick = async (e) => {
      e.stopPropagation();
      if (!window.EyeDropper) return toast("当前浏览器不支持吸管取色");
      try {
        const r = await new EyeDropper().open();
        setEditorBg(r.sRGBHex);
      } catch (err) {
        /* 用户取消取色 */
      }
    };
    box.appendChild(eye);
  }

  // 按住标题栏整窗拖动，位置夹在视口内
  function dragIt(box, handle) {
    let on = false,
      sx = 0,
      sy = 0,
      ox = 0,
      oy = 0;
    handle.addEventListener("pointerdown", (e) => {
      const r = box.getBoundingClientRect();
      box.style.position = "fixed";
      box.style.margin = "0";
      box.style.left = r.left + "px";
      box.style.top = r.top + "px";
      on = true;
      sx = e.clientX;
      sy = e.clientY;
      ox = r.left;
      oy = r.top;
      handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    handle.addEventListener("pointermove", (e) => {
      if (!on) return;
      box.style.left = Math.max(4, Math.min(innerWidth - box.offsetWidth - 4, ox + e.clientX - sx)) + "px";
      box.style.top = Math.max(4, Math.min(innerHeight - box.offsetHeight - 4, oy + e.clientY - sy)) + "px";
    });
    handle.addEventListener("pointerup", () => {
      on = false;
    });
  }

  function setEditorSize(v) {
    const box = $("editorSize");
    if (!box) return;
    box.querySelectorAll(".size-btn").forEach((b) => b.classList.toggle("on", b.dataset.size === v));
    $("editorForm").elements.size.value = v;
  }

  function openEditor(item, kind) {
    const f = $("editorForm");
    const folder = kind === "folder" || (item && item.type === "component");
    f.style.position = "";
    f.style.left = "";
    f.style.top = "";
    f.style.margin = "";
    $("editorTitle").textContent = folder
      ? (item ? "编辑文件夹" : "新建文件夹")
      : (item ? "编辑书签" : "添加书签");
    f.dataset.id = item ? item.id : "";
    f.dataset.pid = item ? item.pid || "" : "";
    f.dataset.kind = folder ? "folder" : "";
    f.elements.name.value = item ? item.name || "" : "";
    f.elements.url.value = item ? item.url || "" : "";
    f.elements.url.required = !folder;
    f.elements.url.closest("label").hidden = folder;
    f.elements.src.value = item ? item.src || "" : "";
    setEditorSize(item ? item.size || "1x1" : folder ? "2x2" : "1x1");
    setEditorBg(item ? item.bgColor || "" : "");
    f.elements.pageGroup.value = item ? item.pageGroup || "" : activePage;
    editorPrev();
    $("editor").hidden = false;
  }

  // 新建 2x2 空文件夹（不进弹窗，直接生成名称「文件夹」并落库）
  function newFolder() {
    const pageItems = links.filter((i) => !isChild(i) && (i.pageGroup || "") === activePage);
    const nextSort = pageItems.length ? Math.max(...pageItems.map((i) => i.sort || 0)) + 10 : 0;
    links.push({
      id: uuid(), app: 0, pid: null, name: "文件夹", url: "iconGroup",
      src: "", size: "2x2", bgColor: null, pageGroup: activePage,
      sort: nextSort, type: "component", component: "iconGroup", form: "link", children: [],
    });
    normalizeSort();
    render();
    saveLinks();
  }

  function upsert(form) {
    const id = form.dataset.id;
    const data = {
      name: form.elements.name.value.trim(),
      url: form.elements.url.value.trim(),
      src: form.elements.src.value.trim(),
      size: form.elements.size.value,
      bgColor: form.elements.bgColor.value.trim() || null,
      pageGroup: form.elements.pageGroup.value.trim(),
    };
    if (id) {
      const item = links.find((i) => i.id === id);
      if (item.type === "component") delete data.url; // 文件夹的 url 固定为 iconGroup，不参与编辑
      Object.assign(item, data);
    } else if (form.dataset.kind === "folder") {
      const pageItems = links.filter((i) => !isChild(i) && (i.pageGroup || "") === data.pageGroup);
      const nextSort = pageItems.length ? Math.max(...pageItems.map((i) => i.sort || 0)) + 10 : 0;
      links.push({
        id: uuid(), app: 0, pid: null, name: data.name || "文件夹", url: "iconGroup",
        src: data.src, size: data.size, bgColor: data.bgColor, pageGroup: data.pageGroup,
        sort: nextSort, type: "component", component: "iconGroup", form: "link", children: [],
      });
    } else {
      const pid = form.dataset.pid;
      const pageItems = links.filter((i) => !isChild(i) && (i.pageGroup || "") === (pid ? "" : data.pageGroup));
      const nextSort = pageItems.length ? Math.max(...pageItems.map((i) => i.sort || 0)) + 10 : 0;
      links.push(Object.assign({ id: uuid(), app: 0, type: "icon", form: "link", sort: nextSort, pid: pid || null }, data));
    }
    normalizeSort();
    render();
  }

  function removeLink(id) {
    if (!confirm("确定删除这个书签？")) return;
    links = links.filter((i) => i.id !== id && i.pid !== id);
    normalizeSort();
    render();
  }

  function reorder(fromId, toId) {
    const from = links.findIndex((i) => i.id === fromId);
    const to = links.findIndex((i) => i.id === toId);
    if (from < 0 || to < 0 || isChild(links[to])) return;
    const [moved] = links.splice(from, 1);
    moved.pageGroup = links[to] ? links[to].pageGroup || "" : "";
    links.splice(to, 0, moved);
    normalizeSort();
    render();
  }

  let saveChain = Promise.resolve(); // 串行化 /link/update，防止并发 POST 乱序覆盖
  async function saveLinks() {
    saveChain = saveChain.then(async () => {
      try {
        const res = await post("/link/update", { link: links });
        toast(res.code === 1 ? "已保存" : res.msg || "保存失败");
        return res.code === 1;
      } catch (err) {
        toast("保存失败：" + (err && err.message ? err.message : "网络错误"));
        return false;
      }
    });
    return saveChain.catch(() => false);
  }

  /* ---------- 搜索 ---------- */
  function runSearch(text) {
    const q = (text || "").trim();
    if (!q) return;
    if (/^(https?:\/\/|\/)/i.test(q)) {
      window.location.href = q;
      return;
    }
    if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(q)) {
      window.location.href = "https://" + q;
      return;
    }
    const url = (engine && engine.url) || "https://www.baidu.com/s?wd={1}";
    window.location.href = url.replace("{1}", encodeURIComponent(q));
  }

  let _pickBtnImg = null;
  function renderEngines() {
    const box = $("engines");
    const pickBtn = $("enginePick");
    const list = Array.isArray(S.engines) ? S.engines : [];
    if (!list.length) {
      box.hidden = true;
      pickBtn.hidden = true;
      return;
    }
    pickBtn.hidden = false;
    const saved = localStorage.getItem("wtab.engine");
    engine = list.find((e) => String(e.id) === saved) || list[0];
    // 确保触发按钮上有图标
    if (!_pickBtnImg) {
      _pickBtnImg = document.createElement("img");
      _pickBtnImg.alt = "";
      pickBtn.appendChild(_pickBtnImg);
    }
    _pickBtnImg.src = engine.icon || "";
    box.innerHTML = "";
    list.forEach((e) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "engine" + (e.id === engine.id ? " on" : "");
      b.title = e.tips || e.name;
      b.innerHTML = `<img src="${e.icon || ""}" alt="${e.name}" onerror="this.remove()"><span>${e.name}</span>`;
      b.onclick = (ev) => {
        ev.stopPropagation();
        engine = e;
        localStorage.setItem("wtab.engine", String(e.id));
        _pickBtnImg.src = e.icon || "";
        box.hidden = true;
        renderEngines();
      };
      box.appendChild(b);
    });
    if (!pickBtn._bound) {
      pickBtn.onclick = () => { box.hidden = !box.hidden; };
      document.addEventListener("click", (e) => {
        if (!e.target.closest(".engines-wrap")) box.hidden = true;
      });
      pickBtn._bound = true;
    }
  }

  function renderSuggest(text) {
    const box = $("suggest");
    if (!openType.searchLink || !text.trim()) {
      box.hidden = true;
      return;
    }
    const q = text.trim().toLowerCase();
    const hits = links
      .filter((i) => !isChild(i) && i.type !== "component" && (i.name || "").toLowerCase().includes(q))
      .slice(0, 8);
    if (!hits.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.innerHTML = "";
    hits.forEach((i) => {
      const a = document.createElement("a");
      a.href = i.url;
      a.target = "_blank";
      a.innerHTML = `<img src="${i.src || ""}" alt="" onerror="this.remove()"><span>${i.name}</span>`;
      box.appendChild(a);
    });
  }

  /* ---------- 时钟 ---------- */
  const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
  function tickClock() {
    if (!theme.timeView) return;
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    let h = d.getHours();
    if (theme.time24 === false) {
      h = h % 12 || 12;
    }
    $("clockTime").textContent = p(h) + ":" + p(d.getMinutes()) + (theme.timeSecond === false ? "" : ":" + p(d.getSeconds()));
    const parts = [];
    if (theme.timeMonthDay !== false) parts.push(`${d.getMonth() + 1}月${d.getDate()}日`);
    if (theme.timeWeek !== false) parts.push("周" + WEEK[d.getDay()]);
    // 农历 + 干支：服务端 lunar_python 计算后注入 WTAB.lunar（跨天刷新一次即可）
    if (S.lunar) parts.push(S.lunar);
    $("clockDate").textContent = parts.join(" ");
  }

  /* ---------- 设置弹窗 ---------- */
  function openSettings() {
    $("setBg").value = theme.backgroundImage || "";
    $("setIcon").value = theme.iconWidth || 80;
    $("setRadius").value = theme.iconRadius == null ? 10 : theme.iconRadius;
    $("setGap").value = theme.colsGap == null ? 35 : theme.colsGap;
    $("setCols").value = theme.maxColumn || 14;
    $("setBgBlur").value = theme.blur || 0;
    $("setMask").value = theme.maskOpacity == null ? 55 : Math.round(theme.maskOpacity * 100);
    $("setTitle").checked = !!theme.LinkTitle;
    $("setPageGroup").checked = theme.pageGroup !== false;
    $("setTabbar").checked = theme.tabbar !== false;
    $("setTime").checked = theme.timeView !== false;
    $("setColorScheme").value = (theme.colorScheme || "auto");
    syncRange();
    syncBgPreview();
    $("drawer").hidden = false;
  }

  // 壁纸预览：地址为空就整块隐藏，避免空白框
  function syncBgPreview() {
    const url = $("setBg").value.trim();
    const box = $("setBgPrev");
    box.hidden = !url;
    box.style.backgroundImage = url ? 'url("' + url.replace(/"/g, "%22") + '")' : "";
  }

  // 页面背景实时生效：选壁纸/改模糊/改遮罩都走这里
  function applyBgLive() {
    const bg = $("bg");
    if (!bg) return;
    const url = ($("setBg").value || "").trim();
    if (url) {
      bg.style.backgroundImage = 'url("' + url.replace(/"/g, "%22") + '")';
      bg.style.backgroundSize = "cover";
      bg.style.backgroundPosition = "center";
      bg.style.backgroundRepeat = "no-repeat";
    } else {
      bg.style.backgroundImage = "";
      bg.style.backgroundSize = "";
      bg.style.backgroundPosition = "";
      bg.style.backgroundRepeat = "";
    }
    const blur = Number($("setBgBlur").value) || 0;
    bg.style.filter = blur ? `blur(${blur}px)` : "";
    const maskEl = $("setMask");
    document.documentElement.style.setProperty("--mask", maskEl ? Number(maskEl.value) / 100 : 0.55);
  }

  let autoSaveTimer = null;
  function autoSave() {
    clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => { saveSettings(false); }, 400);
  }

  /* ---------- 搜索引擎编辑 ---------- */
  let engList = [];

  function renderEngEditor() {
    const box = $("engEditor");
    box.innerHTML = "";
    if (!engList.length) box.innerHTML = '<div class="eng-empty">暂无引擎</div>';
    engList.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "eng-row";
      ["name", "url", "icon"].forEach((field) => {
        const input = document.createElement("input");
        input.value = item[field] || "";
        input.placeholder = { name: "名称", url: "地址，含 {1}", icon: "图标" }[field];
        input.oninput = () => (item[field] = input.value);
        row.appendChild(input);
      });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "ghost-btn";
      del.textContent = "删";
      del.onclick = () => {
        engList.splice(index, 1);
        renderEngEditor();
      };
      row.appendChild(del);
      box.appendChild(row);
    });
  }

  async function loadSystemEngines() {
    const res = await post("/searchEngine/index");
    if (res.code !== 1 || !Array.isArray(res.data)) return toast("获取失败");
    engList = res.data.map((e) => ({ id: e.id, name: e.name, url: e.url, icon: e.icon }));
    renderEngEditor();
  }

  async function saveEngines() {
    if (!S.loggedIn) return false;
    const res = await post("/searchEngine/saveSearchEngine", { searchEngine: engList });
    if (res.code !== 1) toast(res.msg || "引擎保存失败");
    return res.code === 1;
  }

  function openRenamePop(item, title, onRename) {
    const pop = $("renamePop");
    pop.querySelector("h3").textContent = title || "修改名称";
    $("renameInput").value = item.name || "";
    pop.hidden = false;
    $("renameInput").focus();
    $("renameNo").onclick = () => (pop.hidden = true);
    $("renameYes").onclick = () => {
      const name = $("renameInput").value.trim();
      pop.hidden = true;
      if (!name) return;
      item.name = name;
      if (onRename) onRename(item.name);
      else {
        render();
        saveLinks();
      }
    };
  }

  function confirmBox(text, onYes) {
    $("confirmText").textContent = text;
    $("confirm").hidden = false;
    $("confirmNo").onclick = () => ($("confirm").hidden = true);
    $("confirmYes").onclick = async () => {
      $("confirm").hidden = true;
      await onYes();
    };
  }

  function syncRange() {
    $("setIconVal").textContent = $("setIcon").value;
    $("setRadiusVal").textContent = $("setRadius").value;
    $("setGapVal").textContent = $("setGap").value;
    $("setColsVal").textContent = $("setCols").value;
    $("setBgBlurVal").textContent = $("setBgBlur").value;
    $("setMaskVal").textContent = $("setMask").value + "%";
    const bgEl = $("bg");
    if (bgEl) bgEl.style.filter = "blur(" + Number($("setBgBlur").value) + "px)";
    document.documentElement.style.setProperty("--mask", Number($("setMask").value) / 100);
    const iconEl = $("grid");
    if (iconEl) {
      iconEl.style.setProperty("--icon", Number($("setIcon").value) + "px");
      iconEl.style.setProperty("--radius", Number($("setRadius").value) + "px");
      iconEl.style.setProperty("--gap", Number($("setGap").value) + "px");
      iconEl.style.setProperty("--cols", Number($("setCols").value));
    }
  }

  async function saveSettings(reload) {
    // 抽屉没打开说明表单是空的，直接保存会把背景/导航栏/名称重置掉
    if ($("drawer").hidden) return;
    const next = JSON.parse(JSON.stringify(S.config || {}));
    next.theme = Object.assign({}, theme, {
      backgroundImage: $("setBg").value.trim(),
      blur: Number($("setBgBlur").value),
      maskOpacity: Number($("setMask").value) / 100,
      iconWidth: Number($("setIcon").value),
      iconRadius: Number($("setRadius").value),
      colsGap: Number($("setGap").value),
      maxColumn: Number($("setCols").value),
      LinkTitle: $("setTitle").checked,
      pageGroup: $("setPageGroup").checked,
      tabbar: $("setTabbar").checked,
      timeView: $("setTime").checked,
      colorScheme: $("setColorScheme").value,
    });
    const res = await post("/config/update", { config: next });
    if (res.code !== 1) return toast(res.msg || "保存失败");
    // 同步内存中的配置，否则后续 goPage/saveGroups 会用旧配置覆盖刚保存的值
    Object.assign(theme, next.theme);
    S.config = next;
    if (reload && !GUEST) location.reload();
  }

  /* ---------- 壁纸选择 ---------- */
  let wallTargetId = "setBg";
  let wallOffset = 0;
  let wallLoading = false;
  let wallNoMore = false;
  const wallPage = 20;

  function wallItemNode(item) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "wall-item";
    if (item.mime === 1) {
      const media = document.createElement("video");
      media.src = item.url;
      media.muted = true;
      media.playsInline = true;
      media.preload = "metadata";
      node.appendChild(media);
    } else {
      const media = document.createElement("img");
      media.src = item.url;
      media.loading = "lazy";
      media.alt = "";
      media.onerror = () => { node.textContent = "图片缺失"; };
      node.appendChild(media);
    }
    return node;
  }

  function applyWall(item, node) {
    $(wallTargetId).value = item.url || "";
    syncBgPreview();
    if (typeof syncGlobalPreview === "function") syncGlobalPreview();
    if (wallTargetId === "setBg" && typeof applyBgLive === "function") {
      theme.backgroundImage = item.url || "";
      try { applyBgLive(); } catch (err) { console.error("applyBgLive failed:", err); }
      autoSave();
    }
    $("wallGrid").querySelectorAll(".wall-item").forEach((el) => el.classList.toggle("on", el === node));
    $("wall").hidden = true;
    toast("已选择");
  }

  async function openWallpaper() {
    $("wall").hidden = false;
    $("wallGrid").innerHTML = "";
    wallOffset = 0;
    wallNoMore = false;
    await loadWallpapers(true);
  }

  async function loadWallpapers(reset) {
    if (wallLoading) return;
    wallLoading = true;
    if (reset) {
      wallOffset = 0;
      $("wallGrid").innerHTML = "";
    }
    const res = await post("/wallpaper/allClient", { offset: wallOffset, limit: wallPage });
    wallLoading = false;
    if (res.code !== 1 || !Array.isArray(res.data)) return;
    if (reset && !res.data.length) {
      $("wallGrid").innerHTML = '<div class="eng-empty">暂无壁纸</div>';
      wallNoMore = true;
      return;
    }
    res.data.forEach((item) => {
      const node = wallItemNode(item);
      if (item.url && item.url === $(wallTargetId).value) node.classList.add("on");
      node.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        applyWall(item, node);
      };
      $("wallGrid").appendChild(node);
    });
    wallOffset += 1;
    wallNoMore = res.data.length < wallPage;
    $("wallMore").hidden = wallNoMore;
    if (wallNoMore) scrollWallPrevCheck();
  }

  /* 滚动到底部自动加载 */
  function scrollWallPrevCheck() {
    const grid = $("wallGrid");
    if (!grid || wallNoMore || wallLoading) return;
    if (grid.scrollHeight - grid.scrollTop - grid.clientHeight < 120) loadWallpapers(false);
  }

  async function randomWallpaper() {
    const res = await post("/wallpaper/randomWallpaper", {});
    if (res.code !== 1 || !res.data) return toast("没有可用壁纸");
    $(wallTargetId).value = res.data.url || "";
    syncBgPreview();
    if (typeof syncGlobalPreview === "function") syncGlobalPreview();
    if (wallTargetId === "setBg" && typeof applyBgLive === "function") { theme.backgroundImage = res.data.url || ""; applyBgLive(); autoSave(); }
    $("wall").hidden = true;
    toast("已随机选择");
  }

  /* ---------- 初始化 ---------- */
  /* ---------- 右键菜单 ---------- */
  function closeCtx() {
    $("ctx").hidden = true;
  }

  /* 右键菜单项的线性图标（24 视框，跟随文字颜色） */
  const CTX_ICON = {
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L20 8l-4-4L4 16z"/><path d="M14 6l4 4"/></svg>',
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 6h6l2 2h10v10H3z"/></svg>',
    dock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v10H4z"/><path d="M12 10v8"/><path d="M9 15l3 3 3-3"/></svg>',
    layout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/></svg>',
    dissolve: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4H4v5"/><path d="M15 4h5v5"/><path d="M9 20H4v-5"/><path d="M15 20h5v-5"/></svg>',
  };

  // 分类右键菜单：编辑分类（弹窗改组名+同步 link/pageGroup） / 删除分类（标签移回主页）
  function openCtxGroup2(name, e) {
    const menu = $("ctx");
    menu.innerHTML = "";
    menu.appendChild(
      ctxRow("编辑分类", () => renameGroup(name, e.clientY), { icon: CTX_ICON.edit })
    );
    menu.appendChild(
      ctxRow("删除分类", () => deleteGroup(name), { danger: true, icon: CTX_ICON.trash })
    );
    showCtx(e);
  }

  function ctxRow(label, onClick, opts) {
    const o = opts || {};
    const row = document.createElement("div");
    row.className = "ctx-item" + (o.danger ? " danger" : "") + (o.on ? " on" : "") + (o.sub ? " has-sub" : "");
    if (o.icon) {
      const ico = document.createElement("span");
      ico.className = "ctx-ico";
      ico.innerHTML = o.icon;
      row.appendChild(ico);
    }
    const text = document.createElement("span");
    text.textContent = label;
    row.appendChild(text);
    if (o.sub) {
      const sub = document.createElement("div");
      sub.className = "ctx-sub";
      o.sub.forEach((s) => sub.appendChild(ctxRow(s.label, s.onClick, { on: s.on })));
      row.appendChild(sub);
    } else if (onClick) {
      row.onclick = (e) => {
        e.stopPropagation();
        closeCtx();
        onClick();
      };
    }
    return row;
  }

  // 菜单弹出位置：贴鼠标，超出视口就夹回来；右侧不够时子菜单朝左开
  function showCtx(e) {
    const menu = $("ctx");
    menu.hidden = false;
    menu.classList.remove("left");
    const pad = 8;
    const rect = menu.getBoundingClientRect();
    let x = e.clientX;
    let y = e.clientY;
    if (x + rect.width + 150 > innerWidth - pad) menu.classList.add("left");
    if (x + rect.width > innerWidth - pad) x = Math.max(pad, innerWidth - rect.width - pad);
    if (y + rect.height > innerHeight - pad) y = Math.max(pad, innerHeight - rect.height - pad);
    menu.style.left = x + "px";
    menu.style.top = y + "px";
  }

  // 解散卡片：只删卡片本身，里面的图标回到当前分类
  function dissolveGroup(item) {
    const next = links.length ? Math.max(...links.map((i) => i.sort || 0)) + 10 : 0;
    childrenOf(item.id).forEach((k, idx) => {
      delete k.pid;
      k.pageGroup = activePage;
      k.sort = next + idx * 10;
    });
    links = links.filter((i) => i.id !== item.id);
    normalizeSort();
    render();
    saveLinks();
  }

  function openCtxGroup(item, e) {
    const menu = $("ctx");
    menu.innerHTML = "";
    menu.appendChild(
      ctxRow("修改名称", () => openRenamePop(item), { icon: CTX_ICON.edit })
    );
    const pages = [""].concat(S.pageGroups || []);
    if (item.pageGroup && !pages.includes(item.pageGroup)) pages.push(item.pageGroup);
    menu.appendChild(
      ctxRow("移动至分类", null, {
        icon: CTX_ICON.folder,
        sub: pages.map((p) => ({
          label: p || "主页",
          on: (item.pageGroup || "") === p,
          onClick: () => {
            item.pageGroup = p;
            childrenOf(item.id).forEach((k) => { k.pageGroup = p; }); // 子项跟着卡片走
            normalizeSort();
            render();
            saveLinks();
          },
        })),
      })
    );
    menu.appendChild(
      ctxRow("解散卡片", () => confirmBox("解散后卡片里的图标会回到当前分类，卡片本身删除。继续？", () => dissolveGroup(item)), {
        icon: CTX_ICON.dissolve,
      })
    );
    menu.appendChild(
      ctxRow(
        "删除卡片",
        () =>
          confirmBox("删除卡片会连同里面的所有图标一起删除，确定？", () => {
            links = links.filter((i) => i.id !== item.id && i.pid !== item.id);
            normalizeSort();
            render();
            saveLinks();
          }),
        { danger: true, icon: CTX_ICON.trash }
      )
    );
    showCtx(e);
  }

  function openCtx(item, e) {
    if (!S.loggedIn) return;
    if (item.type === "component") return openCtxGroup(item, e);
    const menu = $("ctx");
    menu.innerHTML = "";
    menu.appendChild(ctxRow("编辑标签", () => openEditor(item), { icon: CTX_ICON.edit }));

    const pages = [""].concat(S.pageGroups || []);
    if (item.pageGroup && !pages.includes(item.pageGroup)) pages.push(item.pageGroup);
    menu.appendChild(
      ctxRow("移动至分类", null, {
        icon: CTX_ICON.folder,
        sub: pages.map((p) => ({
          label: p || "主页",
          on: (item.pageGroup || "") === p,
          onClick: () => {
            item.pageGroup = p;
            normalizeSort();
            render();
            saveLinks();
          },
        })),
      })
    );

    menu.appendChild(
      ctxRow("加入 dock 栏", async () => {
        const tabs = Array.isArray(S.tabbar) ? S.tabbar : (S.tabbar = []);
        if (item.url && tabs.some((t) => t.url === item.url)) return toast("已在 dock 栏中");
        const next = tabs.length ? Math.max(...tabs.map((t) => t.sort || 0)) + 10 : 0;
        tabs.push({
          id: uuid(), app: 0, pid: null, name: item.name, url: item.url,
          src: item.src, size: "1x1", sort: next, type: "icon",
        });
        const res = await post("/tabbar/update", { tabbar: tabs });
        toast(res.code === 1 ? "已加入 dock 栏" : res.msg || "操作失败");
        render();
      }, { icon: CTX_ICON.dock })
    );

    // 布局：不用子菜单，直接在行内列出可选格子尺寸
    const layoutRow = document.createElement("div");
    layoutRow.className = "ctx-item ctx-layout";
    const layoutIco = document.createElement("span");
    layoutIco.className = "ctx-ico";
    layoutIco.innerHTML = CTX_ICON.layout;
    layoutRow.appendChild(layoutIco);
    const layoutText = document.createElement("span");
    layoutText.textContent = "布局";
    layoutRow.appendChild(layoutText);
    const sizes = document.createElement("div");
    sizes.className = "ctx-sizes";
    ["1x1", "1x2", "2x1", "2x2", "2x4"].forEach((s) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ctx-size" + ((item.size || "1x1") === s ? " on" : "");
      btn.textContent = s.toUpperCase();
      btn.onclick = (ev) => {
        ev.stopPropagation();
        closeCtx();
        item.size = s;
        render();
        saveLinks();
      };
      sizes.appendChild(btn);
    });
    layoutRow.appendChild(sizes);
    menu.appendChild(layoutRow);

    const hr = document.createElement("div");
    hr.className = "ctx-sep";
    menu.appendChild(hr);
    menu.appendChild(
      ctxRow(
        "删除标签",
        () =>
          confirmBox("确定删除这个标签？", () => {
            links = links.filter((i) => i.id !== item.id && i.pid !== item.id);
            normalizeSort();
            render();
            saveLinks();
          }),
        { danger: true, icon: CTX_ICON.trash }
      )
    );

    showCtx(e);
  }

  function bind() {
    // 空白区只需要 preventDefault（否则浏览器不允许 drop，也让光标显示禁止）并记录坐标；
    // 真正落在哪由 finishDrag → applyDrop 统一判定
    const dropZone = $("grid").parentElement;
    dropZone.addEventListener("dragover", (e) => {
      if (!dragId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      lastXY = { x: e.clientX, y: e.clientY };
    });
    const bg = $("bg");
    if (theme.backgroundImage) {
      bg.style.backgroundImage = 'url("' + theme.backgroundImage.replace(/"/g, "%22") + '")';
      bg.style.backgroundSize = "cover";
      bg.style.backgroundPosition = "center";
      bg.style.backgroundRepeat = "no-repeat";
    }
    if (theme.blur) bg.style.filter = `blur(${theme.blur}px)`;
    document.documentElement.style.setProperty("--mask", theme.maskOpacity == null ? 0.55 : theme.maskOpacity);
    if (theme.timeView === false) $("clock").hidden = true;

    $("searchForm").addEventListener("submit", (e) => {
      e.preventDefault();
      runSearch($("q").value);
    });
    $("q").addEventListener("input", (e) => renderSuggest(e.target.value));

    const authTabs = [...document.querySelectorAll("#login .auth-tab")];
    const authViews = [...document.querySelectorAll("#login .auth-view")];
    const showAuth = (view) => {
      authTabs.forEach((t) => t.classList.toggle("on", t.dataset.view === view));
      authViews.forEach((f) => (f.hidden = f.dataset.view !== view));
      const box = document.querySelector(`#login .auth-view[data-view="${view}"]`);
      const first = box && box.querySelector("input");
      if (first) first.focus();
    };
    authTabs.forEach((t) => (t.onclick = () => showAuth(t.dataset.view)));
    document.querySelectorAll("#login .auth-cancel").forEach((b) => (b.onclick = () => ($("login").hidden = true)));

    // 发送验证码后按钮倒计时，避免连点
    const countdown = (btn) => {
      let left = 60;
      const label = btn.textContent;
      btn.disabled = true;
      const timer = setInterval(() => {
        btn.textContent = `${left--}s`;
        if (left < 0) {
          clearInterval(timer);
          btn.disabled = false;
          btn.textContent = label;
        }
      }, 1000);
    };

    document.querySelectorAll("#login .code-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const form = btn.closest("form");
        const mail = form.querySelector("[name=mail]").value.trim();
        if (!mail) return toast("请先填写邮箱");
        const r = await post("/api/getMailCode", { mail });
        if (r.code !== 1) return toast(r.msg || "发送失败");
        toast("验证码已发送");
        countdown(btn);
      });
    });

    const captchaImg = $("captchaImg");
    const refreshCaptcha = () => { if (captchaImg) captchaImg.src = "/captcha?t=" + Date.now(); };
    if (captchaImg) captchaImg.addEventListener("click", refreshCaptcha);

    const loginBtn = $("loginBtn");
    const sideAdd = $("sideAdd");
    if (sideAdd) sideAdd.onclick = (ev) => openGroupPop("", ev.clientY);
    const openLogin = () => {
      const modal = $("login");
      modal.hidden = false;
      refreshCaptcha(); // 每次打开都换新码：图片只随页面加载一次，超 5 分钟或用过后就和会话里的答案对不上
      showAuth("login");
    };
    const sideGear = $("sideGear");
    if (sideGear) sideGear.onclick = () => (S.loggedIn ? openSettings() : openLogin());
    const sideLogin = $("sideLogin");
    if (sideLogin) sideLogin.onclick = openLogin;
    if (loginBtn) loginBtn.onclick = openLogin;
    $("loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const res = await post("/user/login", {
        mail: f.mail.value.trim(),
        password: f.password.value,
        code: f.code.value.trim(),
      });
      if (res.code === 1) location.reload();
      else {
        $("loginMsg").textContent = res.msg || "登录失败";
        f.password.value = "";
        f.code.value = "";
        refreshCaptcha();
      }
    });
    $("registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const mail = f.mail.value.trim();
      const res = await post("/user/register", {
        mail,
        password: f.password.value,
        code: f.code.value.trim(),
      });
      if (res.code === 1) {
        f.reset();
        showAuth("login");
        $("loginForm").querySelector("[name=mail]").value = mail;
        $("loginMsg").textContent = "注册成功，请登录";
      } else $("registerMsg").textContent = res.msg || "注册失败";
    });
    $("forgetForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const res = await post("/user/forgetPass", {
        mail: f.mail.value.trim(),
        password: f.password.value,
        code: f.code.value.trim(),
      });
      if (res.code === 1) {
        f.reset();
        showAuth("login");
        $("loginMsg").textContent = "密码已重置，请登录";
      } else $("forgetMsg").textContent = res.msg || "重置失败";
    });

    if (S.loggedIn) {
      $("btnAdd").onclick = () => openEditor(null);
      $("btnFolder").onclick = () => newFolder();
      const logoutBtn = $("btnLogout");
      if (logoutBtn)
        logoutBtn.onclick = async () => {
          await post("/user/loginOut", {});
          location.href = "/";
        };
    }

    dragIt($("editorForm"), $("editorTitle"));
    $("editorSize").addEventListener("click", (e) => {
      const b = e.target.closest(".size-btn");
      if (b) setEditorSize(b.dataset.size);
    });
    renderPalette();
    $("editorForm").src.addEventListener("input", editorPrev);
    $("editorForm").elements.name.addEventListener("input", editorPrev);
    $("editorUpload").onclick = () => $("editorFile").click();
    $("editorFile").onchange = async (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = "";
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file, file.name);
      fd.append("category", "linklogo");
      const res = await fetch("/api/upload", { method: "POST", body: fd })
        .then((r) => r.json())
        .catch(() => null);
      if (!res || res.code !== 1) return toast((res && res.msg) || "上传失败");
      $("editorForm").src.value = (res.data && res.data.url) || "";
      editorPrev();
    };
    $("editorNoBg").onclick = () => setEditorBg("");
    $("editorColor").oninput = () => setEditorBg($("editorColor").value);
    $("editorCancel").onclick = () => ($("editor").hidden = true);
    $("groupCancel").onclick = () => {
      $("groupPop").hidden = true;
      const g = $("groupMorePop");
      if (g) g.hidden = true;
      groupIcon = _prevGroupIcon;
      // 取消时也恢复左侧栏图标
      const en = $("groupPop").dataset.edit || "";
      if (en) {
        const ico = document.querySelector('.side-item[data-group="' + en + '"] .side-name .side-ico');
        if (ico) ico.innerHTML = GROUP_ICONS[_prevGroupIcon] || GROUP_ICONS_MORE[_prevGroupIcon] || ICON_FOLDER;
      }
    };
    $("groupCreate").onclick = saveGroup;
    $("groupName").addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveGroup();
    });
    document.addEventListener("click", (e) => {
      const pop = $("groupPop");
      if (pop.hidden) return;
      if (pop.contains(e.target) || e.target.closest("#sideAdd")) return;
      pop.hidden = true;
    });
    document.addEventListener("click", closeCtx);
    window.addEventListener("scroll", closeCtx, true);
    $("ctx").addEventListener("click", (e) => e.stopPropagation());
    $("editorForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      upsert(e.target);
      $("editor").hidden = true;
      if (await saveLinks()) toast("已保存");
    });

    const closeSettings = () => ($("drawer").hidden = true);
    $("setX").onclick = () => { saveSettings(true); closeSettings(); };
    // 点遮罩空白处关闭
    $("drawer").addEventListener("click", (e) => {
      if (e.target === $("drawer")) closeSettings();
    });
    $("setReset").onclick = () =>
      confirmBox("确定恢复为默认值？", async () => {
      // 1. 取第一张壁纸
      let defaultBg = "";
      try {
        const folderRes = await post("/wallpaper/getFolderClient");
        const folders = folderRes.code === 1 && Array.isArray(folderRes.data) ? folderRes.data : [];
        if (folders.length) {
          const wpRes = await post("/wallpaper/getFolderWallpaperClient", { id: folders[0].id, offset: 0 });
          const wps = wpRes.code === 1 && Array.isArray(wpRes.data) ? wpRes.data : [];
          if (wps.length) defaultBg = wps[0].url || "";
        }
      } catch {}
      const defaults = {
        backgroundImage: defaultBg,
        blur: 0,
        maskOpacity: 0.10,
        iconWidth: 60,
        iconRadius: 10,
        colsGap: 30,
        maxColumn: 14,
        LinkTitle: true,
        pageGroup: true,
        tabbar: true,
        timeView: true,
      };
      const next = JSON.parse(JSON.stringify(S.config || {}));
      next.theme = defaults;
      // 同步到表单控件
      $("setBg").value = defaults.backgroundImage;
      $("setBgBlur").value = defaults.blur;
      $("setMask").value = Math.round(defaults.maskOpacity * 100);
      $("setIcon").value = defaults.iconWidth;
      $("setRadius").value = defaults.iconRadius;
      $("setGap").value = defaults.colsGap;
      $("setCols").value = defaults.maxColumn;
      $("setTitle").checked = defaults.LinkTitle;
      $("setPageGroup").checked = defaults.pageGroup;
      $("setTabbar").checked = defaults.tabbar;
      $("setTime").checked = defaults.timeView;
      syncRange();
      syncBgPreview();
      // 2. 头像恢复为预设 1
      post("/user/updateInfo", { field: "avatar", value: "/static/avatar/presets/01.png" }).catch(() => {});
      const avatarPreview = $("accAvatarPreview");
      if (avatarPreview) avatarPreview.src = "/static/avatar/presets/01.png";
      // 3. 保存配置
      const res = await post("/config/update", { config: next });
      if (res.code !== 1) return toast(res.msg || "恢复失败");
      Object.assign(theme, defaults);
      S.config = next;
      toast("已恢复默认值");
      location.reload();
      });
    document.querySelectorAll("#setTabs .set-tab").forEach((b) => {
      b.onclick = async () => {
        document.querySelectorAll("#setTabs .set-tab").forEach((x) => x.classList.toggle("on", x === b));
        document.querySelectorAll("#drawer .set-pane").forEach((p) => (p.hidden = p.dataset.pane !== b.dataset.tab));
        if (b.dataset.tab === "about") {
          // 加载联系信息与关于我们信息
          try {
            const res = await post("/api/site", {});
            if (res.code === 1) {
              const d = res.data || {};
              // App info from backend (hardcoded in HTML as fallback)
              if (d.appName) { $("aboutName").textContent = d.appName; }
              if (d.appVersion) { $("aboutVer").textContent = "版本 " + d.appVersion; }
              if (d.appDesc) { $("aboutDesc").textContent = d.appDesc; }
              if (d.logo) { $("aboutLogo").src = d.logo; }
              else { $("aboutLogo").src = "/static/wtab.png"; }
              // Render app links
              const linksEl = $("aboutLinks");
              if (d.appLinks) {
                linksEl.innerHTML = d.appLinks
                  .split("|")
                  .map(function(pair) {
                    var k = pair.indexOf(":");
                    if (k > 0) {
                      var name = pair.slice(0, k);
                      var url = pair.slice(k + 1);
                      return '<a href="' + url + '" target="_blank" rel="noopener">' + name + '</a>';
                    }
                    return '';
                  })
                  .join('<span>·</span>');
              } else {
                linksEl.innerHTML = '<a href="https://github.com/" target="_blank" rel="noopener">GitHub</a><span>·</span><a href="/health" target="_blank" rel="noopener">运行状态</a>';
              }
              // Contact info
              const email = (d.email || "").trim();
              const qq = (d.qqGroup || "").trim();
              const about = (d.aboutMe || d.customAbout || "").trim();
              const emailEl = $("aboutEmail");
              const emailLink = $("aboutEmailLink");
              if (email) {
                emailEl.hidden = false;
                emailLink.href = "mailto:" + email;
                emailLink.textContent = email;
              } else { emailEl.hidden = true; }
              const qqEl = $("aboutQq");
              const qqLink = $("aboutQqLink");
              if (qq) {
                qqEl.hidden = false;
                qqLink.href = "https://jq.qq.com/?_wv=1027&k=" + qq;
                qqLink.textContent = qq;
              } else { qqEl.hidden = true; }
              const customEl = $("aboutCustom");
              const customHtml = $("aboutCustomHtml");
              if (about) {
                customEl.hidden = false;
                customHtml.innerHTML = about;
              } else { customEl.hidden = true; }
              $("aboutContact").hidden = !(email || qq || about);
            }
          } catch {}
        }
      };
    });
    $("setBgPick").onclick = () => { wallTargetId = "setBg"; openWallpaper(); };
    $("wallMore").onclick = () => loadWallpapers(false);
    $("wallGrid").addEventListener("scroll", scrollWallPrevCheck);
    $("wallRandom").onclick = randomWallpaper;
    $("wallCancel").onclick = () => { $("wall").hidden = true; };
    $("setBg").addEventListener("input", syncBgPreview);
    ["setIcon", "setRadius", "setGap", "setCols", "setBgBlur", "setMask"].forEach((id) =>
      $(id).addEventListener("input", () => { syncRange(); applyBgLive(); autoSave(); })
    );
    const liveFlags = {
      setTitle: "LinkTitle",
      setPageGroup: "pageGroup",
      setTabbar: "tabbar",
      setTime: "timeView",
    };
    Object.entries(liveFlags).forEach(([id, key]) => {
      $(id).addEventListener("change", () => {
        theme[key] = $(id).checked;
        if (key === "pageGroup" && !theme.pageGroup && activePage) {
          activePage = "";
          theme.latestPageGroup = "";
        }
        $("clock").hidden = theme.timeView === false;
        render();
        renderGroupIcons();
        autoSave();
      });
    });
    $("setBg").addEventListener("input", () => { autoSave(); applyBgLive(); });
    $("setColorScheme").addEventListener("change", () => {
      theme.colorScheme = $("setColorScheme").value;
      applyScheme();
      autoSave();
    });
    $("setBgUploadBtn").onclick = () => $("setBgUpload").click();
    $("setBgUpload").onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      fd.append("category", "wallpaper");
      toast("上传中…");
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const j = await res.json();
      if (j.code !== 1 || !j.data) return toast(j.msg || "上传失败");
      $("setBg").value = j.data.url;
      theme.backgroundImage = j.data.url;
      syncBgPreview();
      toast("壁纸已上传");
      e.target.value = "";
      if (typeof applyBgLive === "function") applyBgLive();
      autoSave();
    };

    /* ---------- 全局默认主页（管理员）：/guest 页面编辑未登录主页 ---------- */
    const globalBtn = $("globalCfgBtn");
    if (globalBtn) globalBtn.onclick = () => (location.href = "/guest");
    const guestSave = $("guestSave");
    if (guestSave) {
      guestSave.onclick = async () => {
        const r = await fetch("/config/setGuest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ link: links, config: S.config, tabbar: S.tabbar }),
        }).then((x) => x.json());
        if (r.code !== 1) return toast(r.msg || "保存失败");
        toast("已保存为未登录主页");
        setTimeout(() => (location.href = "/"), 400);
      };
    }
    const guestCancel = $("guestCancel");
    if (guestCancel) guestCancel.onclick = () => (location.href = "/");

    // 账号设置：昵称输入即时保存
    $("accNick").addEventListener("input", () => {
      const v = $("accNick").value.trim();
      post("/user/updateInfo", { field: "nickname", value: v || "" }).catch(() => {});
    });

    // 预设头像（本地 static/avatar/presets/）
    const syncSidebarAvatar = (url) => {
      const side = document.querySelector(".side-avatar");
      if (!side) return;
      if (side.tagName === "IMG") {
        side.src = url;
      } else {
        side.outerHTML = '<img class="side-avatar" src="' + url + '" alt="">';
      }
    };

    const avatarPresets = [
      { url: "/static/avatar/presets/01.png", label: "预设 1" },
      { url: "/static/avatar/presets/02.png", label: "预设 2" },
      { url: "/static/avatar/presets/03.png", label: "预设 3" },
      { url: "/static/avatar/presets/04.png", label: "预设 4" },
      { url: "/static/avatar/presets/05.png", label: "预设 5" },
      { url: "/static/avatar/presets/06.png", label: "预设 6" },
      { url: "/static/avatar/presets/07.png", label: "预设 7" },
      { url: "/static/avatar/presets/08.png", label: "预设 8" },
      { url: "/static/avatar/presets/09.png", label: "预设 9" },
      { url: "/static/avatar/presets/10.png", label: "预设 10" },
    ];
    const presetContainer = $("avatarPresets");
    if (presetContainer) {
      avatarPresets.forEach((p) => {
        const img = document.createElement("img");
        img.src = p.url;
        img.alt = p.label;
        img.title = p.label;
        img.dataset.value = p.url;
        img.style.cssText = "width:48px;height:48px;border-radius:50%;cursor:pointer;border:2px solid transparent;object-fit:cover;display:block;";
        img.onclick = () => {
          const avatarPreview = $("accAvatarPreview");
          avatarPreview.src = p.url;
          avatarPreview.dataset.value = p.url;
          syncSidebarAvatar(p.url);
          post("/user/updateInfo", { field: "avatar", value: p.url }).catch(() => {});
          toast("头像已更换为「" + p.label + "」");
          // 高亮选中
          presetContainer.querySelectorAll("img").forEach((el) => (el.style.borderColor = "transparent"));
          img.style.borderColor = "var(--accent)";
        };
        presetContainer.appendChild(img);
      });
    }

    // 点击预览大图也能换（触发文件选择）；没有头像时点文字头像同样有效
    $("accAvatarPick").onclick = () => $("accAvatarUpload").click();

    // 自定义上传
    $("accAvatarUploadBtn").onclick = () => $("accAvatarUpload").click();
    $("accAvatarUpload").onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) return toast("请选择图片文件");
      if (file.size > 5 * 1024 * 1024) return toast("图片不能超过 5MB");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("category", "avatar");
      toast("上传中…");
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (j.code !== 1 || !j.data) return toast(j.msg || "上传失败");
      $("accAvatarPreview").src = j.data.url;
      $("accAvatarPreview").dataset.value = j.data.url;
      syncSidebarAvatar(j.data.url);
      post("/user/updateInfo", { field: "avatar", value: j.data.url }).catch(() => {});
      toast("头像上传成功");
      e.target.value = "";
    };
    $("accCodeBtn").onclick = async () => {
      const mail = $("accNewMail").value.trim();
      if (!mail) return toast("请先填写新邮箱");
      const r = await post("/api/getMailCode", { mail });
      if (r.code !== 1) return toast(r.msg || "发送失败");
      toast("验证码已发送");
      countdown($("accCodeBtn"));
    };
    $("accMailSave").onclick = async () => {
      const mail = $("accNewMail").value.trim();
      const code = $("accCode").value.trim();
      if (!mail || !code) return toast("请填写新邮箱和验证码");
      const r = await post("/user/newMail", { mail, code });
      if (r.code !== 1) return toast(r.msg || "修改失败");
      $("accMail").value = mail;
      $("accNewMail").value = "";
      $("accCode").value = "";
      toast("邮箱已修改");
    };
    $("accPwdSave").onclick = async () => {
      const old = $("accOldPwd").value.trim();
      const newpw = $("accNewPwd").value.trim();
      const confirm = $("accConfirmPwd").value.trim();
      if (!old || !newpw) return toast("请填写完整");
      if (newpw !== confirm) return toast("两次密码不一致");
      if (newpw.length < 6) return toast("密码至少 6 位");
      const r = await post("/user/changePassword", { old, new: newpw });
      if (r.code !== 1) return toast(r.msg || "修改失败");
      $("accOldPwd").value = "";
      $("accNewPwd").value = "";
      $("accConfirmPwd").value = "";
      toast("密码已修改");
    };
    $("accLogout").onclick = async () => {
      await post("/user/loginOut", {});
      location.href = "/";
    };
    const adminEnter = $("adminEnter");
    if (adminEnter) adminEnter.onclick = () => window.open("/manager", "_blank");
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $("editor").hidden = true;
        $("drawer").hidden = true;
        $("login").hidden = true;
        $("wall").hidden = true;
        $("groupPop").hidden = true;
        closeCtx();
      }
    });

    renderEngines();
    render();
    tickClock();
    setInterval(tickClock, 1000);
  }

  /* ---------- 鼠标滚轮切换分类（滚到底继续滚=下一个，滚到顶继续滚=上一个） ---------- */
  let wheelAt = 0;
  window.addEventListener(
    "wheel",
    (e) => {
      if (!S.loggedIn || e.ctrlKey) return;
      const list = [""].concat(S.pageGroups || []);
      if (list.length < 2) return;
      if (document.querySelector(".modal:not([hidden]), #drawer:not([hidden])")) return;
      const doc = document.documentElement;
      const atBottom = window.innerHeight + window.scrollY >= doc.scrollHeight - 2;
      if (e.deltaY > 0 && !atBottom) return; // 页面还能继续下滚时，先让页面自己滚
      if (e.deltaY < 0 && window.scrollY > 0) return;
      const now = Date.now();
      if (now - wheelAt < 450) return;
      const i = list.indexOf(activePage);
      const next = e.deltaY > 0 ? (i + 1) % list.length : (i - 1 + list.length) % list.length;
      wheelAt = now;
      goPage(list[next]);
    },
    { passive: true }
  );

  bind();

  // 全局公告：status=1 时弹出
  (async () => {
    const r = await post("/api/globalNotify", {});
    if (!r || r.code !== 1 || !r.data) return;
    $("noticeTitle").textContent = r.data.title || "公告";
    $("noticeBody").innerHTML = r.data.content || "";
    $("notice").hidden = false;
  })();
  $("noticeOk").onclick = () => ($("notice").hidden = true);
})();
