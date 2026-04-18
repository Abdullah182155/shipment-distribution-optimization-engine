export const api = {
  // ── Data Management ──
  async uploadCSV(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/data/upload', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
    }
    return res.json();
  },

  async getDataInfo() {
    const res = await fetch('/api/data/info');
    if (!res.ok) throw new Error('Failed to fetch data info');
    return res.json();
  },

  async getDates() {
    const res = await fetch('/api/data/dates');
    if (!res.ok) throw new Error('Failed to fetch dates');
    return res.json();
  },

  // ── Parameters ──
  async getParameters() {
    const res = await fetch('/api/parameters');
    if (!res.ok) throw new Error('Failed to fetch parameters');
    return res.json();
  },

  // ── Optimization ──
  async startOptimization(params) {
    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to start optimization');
    }
    return res.json();
  },

  // ── Results ──
  async getResults(runId) {
    const res = await fetch(`/api/results/${runId}`);
    if (!res.ok) throw new Error('Failed to fetch results');
    return res.json();
  },

  async getHistory() {
    const res = await fetch('/api/history');
    if (!res.ok) throw new Error('Failed to fetch history');
    return res.json();
  },

  async deleteHistoryRun(runId) {
    const res = await fetch(`/api/history/${runId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete run');
    return res.json();
  },
};
