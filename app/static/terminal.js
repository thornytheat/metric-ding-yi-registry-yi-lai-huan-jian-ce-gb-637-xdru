/* 终端手册交互：键位切页、复制命令、两处表单提交。状态集中在一个对象里。 */
(() => {
  const state = { nav: [], busy: false };

  function navLinks() {
    return Array.from(document.querySelectorAll('[data-nav]'));
  }

  function goTo(key) {
    const link = state.nav.find((el) => el.dataset.nav === key);
    if (link) window.location.assign(link.href);
  }

  function onKeydown(event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = (event.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    const index = Number(event.key);
    if (!Number.isInteger(index) || index < 1 || index > state.nav.length) return;
    event.preventDefault();
    goTo(state.nav[index - 1].dataset.nav);
  }

  function wireCopy() {
    document.querySelectorAll('[data-copy]').forEach((button) => {
      button.addEventListener('click', async () => {
        const block = button.parentElement.querySelector('pre');
        if (!block) return;
        const text = block.textContent;
        try {
          await navigator.clipboard.writeText(text);
          button.textContent = '已复制';
        } catch (err) {
          button.textContent = '复制失败';
        }
        window.setTimeout(() => { button.textContent = '复制'; }, 1200);
      });
    });
  }

  function setMessage(node, text, kind) {
    if (!node) return;
    node.textContent = text;
    node.className = 'msg' + (kind ? ' msg-' + kind : '');
  }

  function errorText(body, status) {
    if (!body) return '失败 ' + status;
    const code = body.error || 'E_UNKNOWN';
    const message = body.message || '';
    const hint = body.detail && body.detail.hint ? body.detail.hint : '';
    return [code, message, hint].filter(Boolean).join(' / ');
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    let body = null;
    try { body = await response.json(); } catch (err) { body = null; }
    return { ok: response.ok, status: response.status, body };
  }

  function wireImport() {
    const form = document.getElementById('import-form');
    if (!form) return;
    const message = document.getElementById('import-msg');
    const textarea = form.querySelector('#dsl');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (state.busy) return;
      state.busy = true;
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      setMessage(message, '解析中…');
      const text = textarea.value.trim();
      const sample = form.querySelector('input[name="sample"]:checked').value;
      const payload = text ? { text } : { sample };
      try {
        const result = await postJson('/api/import', payload);
        if (result.ok) {
          setMessage(message, '完成 ' + result.body.batch_id + '（' +
            (result.body.reused ? '复用' : '新增') + '）', 'ok');
          window.setTimeout(() => window.location.reload(), 400);
        } else {
          setMessage(message, errorText(result.body, result.status), 'bad');
          textarea.focus();
        }
      } catch (err) {
        setMessage(message, '网络失败，检查服务是否在 18206', 'bad');
      } finally {
        state.busy = false;
        button.disabled = false;
      }
    });
  }

  function wireVersion() {
    const form = document.getElementById('version-form');
    if (!form) return;
    const message = document.getElementById('version-msg');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (state.busy) return;
      state.busy = true;
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      setMessage(message, '提交中…');
      const payload = {
        metric: form.querySelector('#v-metric').value,
        version: Number(form.querySelector('#v-version').value),
        valid_from: form.querySelector('#v-from').value,
        valid_to: form.querySelector('#v-to').value,
        author: 'web',
      };
      try {
        const result = await postJson('/api/versions/submit', payload);
        if (result.ok) {
          setMessage(message, '已接收 v' + result.body.version, 'ok');
          window.setTimeout(() => window.location.reload(), 500);
        } else {
          setMessage(message, errorText(result.body, result.status), 'bad');
        }
      } catch (err) {
        setMessage(message, '网络失败，检查服务是否在 18206', 'bad');
      } finally {
        state.busy = false;
        button.disabled = false;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    state.nav = navLinks();
    document.addEventListener('keydown', onKeydown);
    wireCopy();
    wireImport();
    wireVersion();
  });
})();
