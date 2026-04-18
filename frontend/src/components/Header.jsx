import { Package, Map } from 'lucide-react';

export default function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 z-30">
      <div className="flex items-center gap-3">
        <div className="bg-blue-600 p-2 rounded-lg text-white">
          <Map size={24} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-800 leading-tight">Courier Optimizer</h1>
          <p className="text-sm text-slate-500 font-medium tracking-wide">V17 Engine — Advanced Area Minimization</p>
        </div>
      </div>
      <div className="flex items-center gap-4 text-sm font-medium text-slate-600">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
          Backend Connected
        </div>
      </div>
    </header>
  );
}
