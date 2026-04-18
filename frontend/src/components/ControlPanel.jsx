import { useState } from 'react';
import { Settings2, Clock, CheckCircle2, XCircle, Database, Trash2 } from 'lucide-react';
import DataUpload from './DataUpload';

export default function ControlPanel({ params, onStart, isRunning, history, onSelectHistory, onDeleteHistory, currentRunId, dataInfo, onDataUploaded }) {
  const [activeTab, setActiveTab] = useState('data');
  const [advancedParams, setAdvancedParams] = useState({ ...params });

  const handleAdvancedChange = (name, value) => {
    setAdvancedParams(prev => ({ ...prev, [name]: value }));
  };

  const handleConfigReady = (config) => {
    if (isRunning) return;
    // Merge advanced params with data config
    const merged = { ...advancedParams, ...config };
    onStart(merged);
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Tab Switcher */}
      <div className="p-4 border-b border-slate-200 shrink-0">
        <div className="flex bg-slate-100 p-1 rounded-lg">
          <button
            onClick={() => setActiveTab('data')}
            className={`flex-1 flex justify-center items-center gap-2 py-2 text-sm font-medium rounded-md transition-all ${
              activeTab === 'data' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Database size={16} />
            Data
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`flex-1 flex justify-center items-center gap-2 py-2 text-sm font-medium rounded-md transition-all ${
              activeTab === 'settings' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Settings2 size={16} />
            Advanced
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex-1 flex justify-center items-center gap-2 py-2 text-sm font-medium rounded-md transition-all ${
              activeTab === 'history' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Clock size={16} />
            History
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'data' && (
        <DataUpload 
          onConfigReady={handleConfigReady}
          existingDataInfo={dataInfo}
        />
      )}

      {activeTab === 'settings' && (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider">Algorithm Parameters</h3>
            <p className="text-xs text-slate-500">Tune these to control optimization quality vs speed.</p>
            
            <div className="space-y-3">
              <ParamRow label="LNS Iterations" name="lns_iters" value={advancedParams.lns_iters} onChange={handleAdvancedChange} />
              <ParamRow label="SA Iterations" name="sa_iters" value={advancedParams.sa_iters} onChange={handleAdvancedChange} />
              <ParamRow label="SA Start Temp" name="sa_t_start" value={advancedParams.sa_t_start} onChange={handleAdvancedChange} step="0.001" />
              <ParamRow label="SA Cooling Rate" name="sa_cool" value={advancedParams.sa_cool} onChange={handleAdvancedChange} step="0.0001" />
              <ParamRow label="Vertex Steal Neighbours" name="steal_n_neighbours" value={advancedParams.steal_n_neighbours} onChange={handleAdvancedChange} />
              <ParamRow label="Merge-Split Pairs" name="merge_split_pairs" value={advancedParams.merge_split_pairs} onChange={handleAdvancedChange} />
              <ParamRow label="Archive Size" name="archive_k" value={advancedParams.archive_k} onChange={handleAdvancedChange} />
            </div>

            <div className="pt-4 border-t border-slate-200 space-y-3">
              <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider">Objective Weights</h3>
              <ParamRow label="Alpha (area)" name="alpha" value={advancedParams.alpha} onChange={handleAdvancedChange} step="0.01" />
              <ParamRow label="Beta (overlap)" name="beta" value={advancedParams.beta} onChange={handleAdvancedChange} step="0.01" />
              <ParamRow label="Delta (compactness)" name="delta" value={advancedParams.delta} onChange={handleAdvancedChange} step="0.01" />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-3">
            {history.length === 0 ? (
              <div className="text-sm text-slate-500 text-center py-8">No optimization runs yet.</div>
            ) : (
              history.map(run => (
                <button
                  key={run.run_id}
                  onClick={() => onSelectHistory(run.run_id)}
                  className={`w-full text-left p-3 rounded-lg border transition-all ${
                    currentRunId === run.run_id 
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500' 
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2 group">
                    <span className="text-xs font-mono text-slate-500" title={run.run_id}>
                      {run.run_id.substring(0, 8)}...
                    </span>
                    <div className="flex items-center gap-2">
                      {run.status === 'completed' ? (
                        <span className="flex items-center text-xs font-medium text-green-600 bg-green-100 px-2 py-0.5 rounded-full"><CheckCircle2 size={12} className="mr-1" /> Done</span>
                      ) : run.status === 'failed' ? (
                        <span className="flex items-center text-xs font-medium text-red-600 bg-red-100 px-2 py-0.5 rounded-full"><XCircle size={12} className="mr-1" /> Failed</span>
                      ) : (
                        <span className="flex items-center text-xs font-medium text-amber-600 bg-amber-100 px-2 py-0.5 rounded-full">Running</span>
                      )}
                      
                      <button 
                        onClick={(e) => { e.stopPropagation(); onDeleteHistory(run.run_id); }}
                        className="p-1 rounded-md text-slate-400 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete Run"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="text-sm font-semibold text-slate-800">
                        {run.area_km2 ? `${run.area_km2.toFixed(2)} km²` : '-- km²'}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {run.num_couriers} couriers | {run.n_deliveries} pts
                      </div>
                    </div>
                    {run.reduction_pct && (
                      <div className="text-sm font-bold text-emerald-600">
                        -{run.reduction_pct.toFixed(1)}%
                      </div>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ParamRow({ label, name, value, onChange, step = "1" }) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-700 mb-1 block">{label}</label>
      <input
        type="number"
        name={name}
        value={value}
        step={step}
        onChange={e => onChange(name, Number(e.target.value))}
        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  );
}
