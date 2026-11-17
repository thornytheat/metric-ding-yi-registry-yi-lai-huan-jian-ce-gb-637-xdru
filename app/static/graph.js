/* 依赖图的等宽文本视图：只把后端返回的边排成文本，不做任何判定。 */
(() => {
  const state = { loading: false };

  function bar(label, value) {
    return label + ' ' + value;
  }

  function renderGraph(payload) {
    const lines = [];
    const cycles = payload.cycles || [];
    const cycleMembers = new Set();
    cycles.forEach((comp) => comp.members.forEach((name) => cycleMembers.add(name)));

    lines.push('# ' + bar('nodes', payload.counts.nodes) + '  ' +
      bar('edges', payload.counts.edges) + '  ' +
      bar('components', payload.counts.components) + '  ' +
      bar('cycles', payload.counts.cycles));
    lines.push('-'.repeat(72));

    const byMetric = new Map();
    (payload.edges || []).forEach((edge) => {
      if (edge.src.indexOf('metric:') !== 0) return;
      const name = edge.src.slice(7);
      if (!byMetric.has(name)) byMetric.set(name, []);
      byMetric.get(name).push(edge);
    });

    const names = Array.from(byMetric.keys()).sort((a, b) => a.localeCompare(b, 'zh'));
    names.forEach((name) => {
      const flag = cycleMembers.has(name) ? '!!' : '  ';
      const targets = byMetric.get(name).map((edge) => {
        const kind = edge.kind === 'metric_metric' ? '->'
          : edge.kind === 'metric_field' ? '~>' : '=>';
        return kind + ' ' + edge.dst;
      });
      lines.push(flag + ' ' + name + '  ' + targets.join('  '));
    });

    if (cycles.length) {
      lines.push('-'.repeat(72));
      cycles.forEach((comp) => {
        lines.push('cycle(' + comp.size + '): ' + (comp.path || []).join(' -> '));
      });
    }
    return lines.join('\n');
  }

  async function load() {
    const node = document.getElementById('graph-art');
    if (!node || state.loading) return;
    const batchId = node.dataset.batch;
    if (!batchId) {
      node.textContent = '无批次。';
      return;
    }
    state.loading = true;
    try {
      const response = await fetch('/api/graph?batch_id=' + encodeURIComponent(batchId));
      if (!response.ok) {
        node.textContent = '读取失败 ' + response.status;
        return;
      }
      node.textContent = renderGraph(await response.json());
    } catch (err) {
      node.textContent = '网络失败，检查服务是否在 18206';
    } finally {
      state.loading = false;
    }
  }

  document.addEventListener('DOMContentLoaded', load);
})();
