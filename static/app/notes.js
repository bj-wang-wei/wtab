(function () {
  const $ = (id) => document.getElementById(id);
  const loggedIn = !!(window.WTAB && window.WTAB.loggedIn);
  let notes = [];
  let editing = null;

  function toast(msg) {
    const node = $("toast");
    node.textContent = msg;
    node.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (node.hidden = true), 1800);
  }

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  function render() {
    const box = $("noteList");
    box.innerHTML = "";
    if (!notes.length) {
      box.innerHTML = '<div class="notes-hint">还没有笔记，点右上角「新建笔记」开始。</div>';
      return;
    }
    notes.forEach((note, index) => {
      const card = document.createElement("div");
      card.className = "note-card" + (Number(note.weight) ? " pinned" : "");

      const title = document.createElement("h3");
      title.textContent = note.title || "无标题";
      card.appendChild(title);

      const excerpt = document.createElement("div");
      excerpt.className = "excerpt";
      excerpt.textContent = (note.text || "").slice(0, 200);
      card.appendChild(excerpt);

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = note.update_time || note.create_time || "";
      card.appendChild(meta);

      const ops = document.createElement("div");
      ops.className = "ops";
      const add = (label, fn) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ghost-btn";
        btn.textContent = label;
        btn.onclick = fn;
        ops.appendChild(btn);
      };
      add("编辑", () => openEditor(note));
      add(Number(note.weight) ? "取消置顶" : "置顶", () => setWeight(note, Number(note.weight) ? 0 : 1));
      if (index > 0) add("↑", () => move(index, -1));
      if (index < notes.length - 1) add("↓", () => move(index, 1));
      add("删除", () => {
        if (!confirm(`删除「${note.title || "无标题"}」？`)) return;
        post("/note/del", { id: note.id }).then((res) => {
          if (res.code !== 1) return toast(res.msg || "删除失败");
          toast("已删除");
          load();
        });
      });
      card.appendChild(ops);
      box.appendChild(card);
    });
  }

  function openEditor(note) {
    editing = note || null;
    $("noteTitle").value = note ? note.title || "" : "";
    $("noteText").value = note ? note.text || "" : "";
    $("noteEditor").hidden = false;
    $("noteText").focus();
  }

  async function save() {
    const payload = { title: $("noteTitle").value.trim(), text: $("noteText").value };
    const url = editing ? "/note/update" : "/note/add";
    if (editing) payload.id = editing.id;
    const res = await post(url, payload);
    if (res.code !== 1) return toast(res.msg || "保存失败");
    $("noteEditor").hidden = true;
    toast("已保存");
    load();
  }

  async function setWeight(note, weight) {
    await post("/note/setWeight", { id: note.id, weight });
    load();
  }

  async function move(index, delta) {
    const next = notes.slice();
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    notes = next;
    render();
    await post("/note/sort", { ids: notes.map((n) => n.id) });
  }

  async function load() {
    const res = await post("/note/get", {});
    if (res.code !== 1 || !Array.isArray(res.data)) {
      notes = [];
      render();
      return;
    }
    notes = res.data;
    // 置顶的排前面，其余保持后端给出的 sort 顺序
    notes.sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0));
    render();
  }

  function bind() {
    if (!loggedIn) {
      $("noteHint").hidden = false;
      $("noteNew").hidden = true;
      return;
    }
    $("noteNew").hidden = false;
    $("noteNew").onclick = () => openEditor(null);
    $("noteCancel").onclick = () => ($("noteEditor").hidden = true);
    $("noteSave").onclick = save;
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") $("noteEditor").hidden = true;
    });
  }

  bind();
  load();
})();
