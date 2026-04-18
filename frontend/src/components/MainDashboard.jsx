import { useMemo } from 'react';
import { Activity, Zap, Maximize, MapPin, Download, BarChart3 } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import MapVisualization from './MapVisualization';

const COLORS = [
  '#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
  '#dc2626', '#2563eb', '#059669', '#d97706', '#7c3aed',
  '#db2777', '#0891b2', '#ea580c', '#0d9488', '#4f46e5'
];

export default function MainDashboard({ runStatus, results, runId }) {

  const isRunning = runStatus?.status === 'running' || runStatus?.status === 'pending';
  const hasResults = !!results;

  // Convergence chart data
  const chartData = useMemo(() => {
    if (hasResults && results.convergence_history) {
      return results.convergence_history.map((val, idx) => ({ iter: idx, area: val }));
    }
    return [];
  }, [hasResults, results]);

  // Workload distribution data
  const workloadData = useMemo(() => {
    if (hasResults && results.couriers) {
      return results.couriers.map(c => ({
        name: `C${c.courier_id}`,
        deliveries: c.n_deliveries,
        area: parseFloat(c.area_km2?.toFixed(2) || 0),
      }));
    }
    return [];
  }, [hasResults, results]);

  return (
    <div className="h-full flex flex-col p-6 overflow-hidden">

      {/* Top Stats Bar */}
      <div className="grid grid-cols-4 gap-4 mb-6 shrink-0">
        <StatCard
          icon={<MapPin className="text-blue-500" size={24} />}
          title="Total Area"
          value={hasResults ? `${results.area_km2.toFixed(2)} km²` : (runStatus?.current_area ? `${runStatus.current_area.toFixed(2)} km²` : '--')}
          sub={hasResults ? `vs ${results.baseline_km2?.toFixed(2)} km²` : ''}
          highlight={hasResults && results.reduction_pct ? `-${results.reduction_pct.toFixed(1)}%` : null}
        />
        <StatCard
          icon={<Maximize className="text-amber-500" size={24} />}
          title="Overlap Area"
          value={hasResults ? `${results.overlap_km2?.toFixed(2)} km²` : '--'}
          sub="Intersection between hulls"
        />
        <StatCard
          icon={<Activity className="text-indigo-500" size={24} />}
          title="Avg Compactness"
          value={hasResults ? results.avg_compact?.toFixed(3) : '--'}
          sub="Isoperimetric ratio (higher is better)"
        />
        <StatCard
          icon={<Zap className="text-emerald-500" size={24} />}
          title="Time Elapsed"
          value={hasResults ? `${results.time_s?.toFixed(1)} s` : (runStatus?.elapsed_seconds ? `${runStatus.elapsed_seconds.toFixed(1)} s` : '--')}
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex gap-6 min-h-0">

        {/* Map View */}
        <div className="flex-1 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col relative">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex justify-between items-center z-20 absolute top-0 left-0 right-0 bg-opacity-90 backdrop-blur">
            <h3 className="font-semibold text-slate-800">Spatial Visualization</h3>
            {hasResults && (
              <a
                href={`/api/download/json/${runId}`}
                className="flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800 bg-blue-50 px-3 py-1.5 rounded-full"
              >
                <Download size={14} />
                Export JSON
              </a>
            )}
          </div>

          <div className="flex-1 relative bg-slate-100 z-10 pt-[52px]">
            {(!hasResults && !isRunning) ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-3">
                <MapPin size={48} className="opacity-20" />
                <p>Run optimization to see the map</p>
              </div>
            ) : (
              <MapVisualization results={results} runStatus={runStatus} />
            )}
          </div>
        </div>

        {/* Progress & Logs (Right Sidebar) */}
        <div className="w-80 flex flex-col gap-6 shrink-0">

          {/* Progress Box */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 shrink-0">
            <h3 className="font-semibold text-slate-800 mb-3 text-sm flex justify-between">
              Progress
              <span className="text-xs font-normal text-slate-500 font-mono">
                {runStatus ? runStatus.phase : 'Idle'}
              </span>
            </h3>
            <div className="relative h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="absolute top-0 left-0 h-full bg-blue-500 transition-all duration-300 ease-out"
                style={{ width: `${(runStatus?.progress || 0) * 100}%` }}
              />
            </div>

            {hasResults && chartData.length > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="h-24 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <Line type="monotone" dataKey="area" stroke="#3b82f6" strokeWidth={2} dot={false} isAnimationActive={false} />
                      <YAxis domain={['auto', 'auto']} hide />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="text-xs text-center text-slate-500 mt-1">Convergence History</div>
              </div>
            )}
          </div>

          {/* Workload Distribution */}
          <div className="flex-1 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-800 flex items-center justify-between">
              <span>Workload Distribution</span>
              {hasResults && results.workload && (
                <span className="text-xs font-normal text-slate-500">
                  min {results.workload.min} · max {results.workload.max} · avg {results.workload.mean?.toFixed(1)}
                </span>
              )}
            </div>
            <div className="flex-1 p-4">
              {hasResults && results.couriers && results.couriers.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={workloadData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: '#94a3b8' }}
                      axisLine={{ stroke: '#e2e8f0' }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: '#94a3b8' }}
                      axisLine={{ stroke: '#e2e8f0' }}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#1e293b',
                        border: 'none',
                        borderRadius: '8px',
                        fontSize: '12px',
                        color: '#f1f5f9',
                        boxShadow: '0 10px 25px rgba(0,0,0,0.3)'
                      }}
                      cursor={{ fill: 'rgba(59,130,246,0.08)' }}
                    />
                    <Bar
                      dataKey="deliveries"
                      radius={[4, 4, 0, 0]}
                      maxBarSize={32}
                    >
                      {workloadData.map((entry, index) => (
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-2">
                  <BarChart3 size={36} className="opacity-20" />
                  <p className="text-sm">Run optimization to see workload</p>
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, title, value, sub, highlight }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-col">
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 bg-slate-50 rounded-lg shrink-0">
          {icon}
        </div>
        <div className="text-sm font-semibold text-slate-600">{title}</div>
      </div>
      <div className="flex items-baseline gap-3 mt-1">
        <div className="text-2xl font-bold text-slate-800">{value}</div>
        {highlight && (
          <div className="text-sm font-bold text-emerald-500 bg-emerald-50 px-2 py-0.5 rounded-full">{highlight}</div>
        )}
      </div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}
