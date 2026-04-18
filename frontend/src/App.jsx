import { useState, useEffect } from 'react';
import { Toaster } from 'react-hot-toast';
import Header from './components/Header';
import ControlPanel from './components/ControlPanel';
import MainDashboard from './components/MainDashboard';
import { api } from './lib/api';

function App() {
  const [params, setParams] = useState(null);
  const [runId, setRunId] = useState(null);
  const [runStatus, setRunStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [history, setHistory] = useState([]);
  const [dataInfo, setDataInfo] = useState(null);
  
  // Load default parameters + check for existing data on mount
  useEffect(() => {
    async function init() {
      try {
        const [paramData, info] = await Promise.all([
          api.getParameters(),
          api.getDataInfo().catch(() => null),
        ]);
        setParams(paramData);
        if (info && info.status === 'valid') {
          setDataInfo(info);
        }
      } catch (err) {
        console.error("Failed to load initial data:", err);
      }
    }
    init();
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const data = await api.getHistory();
      setHistory(data.runs || []);
    } catch (err) {
      console.error("Failed to fetch history:", err);
    }
  };

  const handleDeleteHistory = async (id) => {
    try {
      await api.deleteHistoryRun(id);
      toast.success("Run deleted from history");
      if (runId === id) {
        setRunId(null);
        setResults(null);
        setRunStatus(null);
      }
      fetchHistory();
    } catch (err) {
      toast.error("Failed to delete run");
    }
  };

  const handleStartRun = async (config) => {
    const prevResults = results;
    const prevStatus = runStatus;
    try {
      setResults(null); 
      setRunStatus({ status: 'pending', message: 'Starting...' });
      // Merge data config with algorithm defaults
      const updatedParams = { ...params, ...config };
      const res = await api.startOptimization(updatedParams);
      setRunId(res.run_id);
      fetchHistory();
    } catch (err) {
      console.error("Start run error:", err);
      let errMsg = err.message || 'Failed to start optimization';
      if (err.message && err.message.includes('[{')) {
        try {
          const parsed = JSON.parse(err.message);
          errMsg = parsed.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', ');
        } catch(e) {}
      }
      toast.error(errMsg);
      setResults(prevResults);
      setRunStatus(prevStatus);
    }
  };

  // WebSocket for progress updates
  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${window.location.hostname}:8000/ws/${runId}`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      console.error("WS connect failed:", e);
      return;
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setRunStatus(data);
        
        if (data.status === 'completed' || data.final) {
          fetchResults(runId);
        }
      } catch (e) {
        // Handle JSON parse error
      }
    };

    ws.onerror = () => {
      // Fallback to polling
      const poll = setInterval(async () => {
        try {
          const res = await fetch(`/api/status/${runId}`);
          const data = await res.json();
          setRunStatus(data);
          if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(poll);
            if (data.status === 'completed') fetchResults(runId);
          }
        } catch (e) {}
      }, 2000);
      return () => clearInterval(poll);
    };

    return () => {
      ws.close();
    };
  }, [runId]);

  const fetchResults = async (id) => {
    try {
      const res = await api.getResults(id);
      if (res && res.status === 'completed') {
        setResults(res);
        fetchHistory();
      }
    } catch (err) {
      console.error("Fetch results err:", err);
    }
  };

  const handleSelectHistory = (id) => {
    setRunId(id);
    fetchResults(id);
  };

  const handleDataUploaded = (info) => {
    setDataInfo(info);
  };

  if (!params) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full flex-col bg-slate-50 overflow-hidden">
      <Header />
      <Toaster position="top-right" />
      
      <div className="flex flex-1 overflow-hidden">
        {/* Left side: Controls */}
        <div className="w-96 flex-shrink-0 border-r border-slate-200 bg-white shadow-sm z-20 flex flex-col">
          <ControlPanel 
            params={params} 
            onStart={handleStartRun} 
            isRunning={runStatus?.status === 'running' || runStatus?.status === 'pending'}
            history={history}
            onSelectHistory={handleSelectHistory}
            onDeleteHistory={handleDeleteHistory}
            currentRunId={runId}
            dataInfo={dataInfo}
            onDataUploaded={handleDataUploaded}
          />
        </div>
        
        {/* Right side: Visualization */}
        <div className="flex-1 min-w-0 bg-slate-50 relative">
          <MainDashboard 
            runStatus={runStatus} 
            results={results} 
            runId={runId} 
          />
        </div>
      </div>
    </div>
  );
}

export default App;
