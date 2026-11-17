/* 诊断明细的行内筛选：只做展示过滤，不改任何后端结论。 */
(() => {
  const state = { code: '', level: '', rows: [] };

  function apply() {
    let shown = 0;
    state.rows.forEach((row) => {
      const okCode = !state.code || row.dataset.code === state.code;
      const okLevel = !state.level || row.dataset.level === state.level;
      const visible = okCode && okLevel;
      row.hidden = !visible;
      if (visible) shown += 1;
    });
    const counter = document.getElementById('filter-count');
    if (counter) counter.textContent = '显示 ' + shown + ' / ' + state.rows.length;
    const params = new URLSearchParams();
    if (state.code) params.set('code', state.code);
    if (state.level) params.set('level', state.level);
    const query = params.toString();
    window.history.replaceState(null, '', query ? '?' + query : window.location.pathname);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const table = document.getElementById('diag-table');
    if (!table) return;
    state.rows = Array.from(table.querySelectorAll('tbody tr'));
    const codeSelect = document.getElementById('filter-code');
    const levelSelect = document.getElementById('filter-level');
    const params = new URLSearchParams(window.location.search);
    if (codeSelect) {
      codeSelect.value = params.get('code') || '';
      codeSelect.addEventListener('change', () => {
        state.code = codeSelect.value;
        apply();
      });
    }
    if (levelSelect) {
      levelSelect.value = params.get('level') || '';
      levelSelect.addEventListener('change', () => {
        state.level = levelSelect.value;
        apply();
      });
    }
    state.code = codeSelect ? codeSelect.value : '';
    state.level = levelSelect ? levelSelect.value : '';
    apply();
  });
})();
