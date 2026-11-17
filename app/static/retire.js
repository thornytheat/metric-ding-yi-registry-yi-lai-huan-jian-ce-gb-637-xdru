/* 下线计划的可读视图：把后端返回的次序、环与阻断排成等宽段落，不做判定。 */
(() => {
  const state = { loading: false };

  function line(label, value) {
    return label + ' ' + value;
  }

  function renderPlan(payload) {
    const lines = [];
    const counters = payload.counters || {};
    lines.push('# ' + line('目标', (payload.targets || []).join(',')) +
      '  ' + line('受影响', counters.affected) +
      '  ' + line('环', counters.rings) +
      '  ' + line('阻断', counters.blocked));
    lines.push('-'.repeat(64));

    (payload.checklist || []).forEach((row) => {
      lines.push(String(row.step).padStart(2, '0') + '. ' + row.metric +
        '  <- ' + row.dependents + ' 依赖方  ' + row.reports_text);
    });

    if ((payload.rings || []).length) {
      lines.push('-'.repeat(64));
      payload.rings.forEach((ring) => {
        lines.push('ring ' + ring.ring_id + ' x' + ring.rotations + ': ' +
          (ring.path || []).join(' -> '));
      });
    }

    const blockers = payload.blockers || [];
    if (blockers.length) {
      lines.push('-'.repeat(64));
      blockers.forEach((row) => {
        const mark = row.level === 'error' ? 'x' : '!';
        lines.push(mark + ' ' + row.metric + '  ' + row.code);
      });
    }

    if ((payload.isolated || []).length) {
      lines.push('-'.repeat(64));
      lines.push('isolated: ' + payload.isolated.join(' '));
    }
    return lines.join('\n');
  }

  async function load() {
    const node = document.getElementById('retire-art');
    if (!node || state.loading) return;
    const batchId = node.dataset.batch;
    if (!batchId) {
      node.textContent = '无批次。';
      return;
    }
    state.loading = true;
    const query = new URLSearchParams({ batch_id: batchId });
    if (node.dataset.targets) query.set('targets', node.dataset.targets);
    try {
      const response = await fetch('/api/retire?' + query.toString());
      if (!response.ok) {
        let body = null;
        try { body = await response.json(); } catch (err) { body = null; }
        const code = body && body.error ? body.error : response.status;
        node.textContent = '读取失败 ' + code;
        return;
      }
      node.textContent = renderPlan(await response.json());
    } catch (err) {
      node.textContent = '网络失败，检查服务是否在 18206';
    } finally {
      state.loading = false;
    }
  }

  document.addEventListener('DOMContentLoaded', load);
})();
