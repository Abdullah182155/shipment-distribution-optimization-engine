import { useState, useRef } from 'react';
import { Upload, CheckCircle2, XCircle, AlertTriangle, FileSpreadsheet, Calendar, Users, ChevronRight, RotateCcw } from 'lucide-react';
import { api } from '../lib/api';
import toast from 'react-hot-toast';

const STEPS = ['upload', 'validate', 'date', 'configure'];
const STEP_LABELS = ['Upload CSV', 'Validate', 'Select Date', 'Configure'];

export default function DataUpload({ onConfigReady, existingDataInfo }) {
  const [step, setStep] = useState(existingDataInfo?.status === 'valid' ? 'date' : 'upload');
  const [uploading, setUploading] = useState(false);
  const [validationResult, setValidationResult] = useState(existingDataInfo || null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [deliveryCount, setDeliveryCount] = useState(0);
  const [numCouriers, setNumCouriers] = useState(20);
  const [minPerCourier, setMinPerCourier] = useState(10);
  const [maxPerCourier, setMaxPerCourier] = useState(20);
  const fileInputRef = useRef(null);

  // ── Step 1: Upload ──
  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Please select a .csv file');
      return;
    }

    setUploading(true);
    try {
      const result = await api.uploadCSV(file);
      setValidationResult(result);
      setStep('validate');
      toast.success(`Uploaded ${file.name} successfully`);
    } catch (err) {
      toast.error(err.message);
      setValidationResult({ status: 'error', message: err.message });
      setStep('validate');
    } finally {
      setUploading(false);
    }
  };

  // ── Step 2 → 3: Move to date selection ──
  const proceedToDate = () => {
    if (!validationResult || validationResult.status !== 'valid') return;
    setStep('date');
  };

  // ── Step 3: Select date ──
  const handleDateSelect = (dateInfo) => {
    setSelectedDate(dateInfo.date);
    setDeliveryCount(dateInfo.count);

    // Auto-suggest couriers: deliveries / 15 (midpoint of 10-20 range)
    const suggested = Math.max(2, Math.min(100, Math.round(dateInfo.count / 15)));
    setNumCouriers(suggested);
    setMinPerCourier(Math.max(1, Math.floor(dateInfo.count / suggested) - 5));
    setMaxPerCourier(Math.ceil(dateInfo.count / suggested) + 5);
  };

  const proceedToConfigure = () => {
    if (!selectedDate) return;
    setStep('configure');
  };

  // ── Step 4: Configure and launch ──
  const handleLaunch = () => {
    if (!selectedDate || !numCouriers) return;
    onConfigReady({
      target_date: selectedDate,
      n_deliveries: deliveryCount,
      num_couriers: numCouriers,
      min_per_courier: minPerCourier,
      max_per_courier: maxPerCourier,
      data_file: validationResult.filename,
    });
  };

  const handleReset = () => {
    setStep('upload');
    setValidationResult(null);
    setSelectedDate(null);
    setDeliveryCount(0);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const currentStepIdx = STEPS.indexOf(step);

  return (
    <div className="flex flex-col h-full">
      {/* Step Progress Bar */}
      <div className="px-4 pt-4 pb-2 shrink-0">
        <div className="flex items-center justify-between mb-3">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                i < currentStepIdx ? 'bg-emerald-500 text-white' :
                i === currentStepIdx ? 'bg-blue-600 text-white ring-4 ring-blue-100' :
                'bg-slate-200 text-slate-500'
              }`}>
                {i < currentStepIdx ? '✓' : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-8 h-0.5 mx-1 transition-all ${
                  i < currentStepIdx ? 'bg-emerald-400' : 'bg-slate-200'
                }`} />
              )}
            </div>
          ))}
        </div>
        <div className="text-xs text-slate-500 text-center font-medium">
          {STEP_LABELS[currentStepIdx]}
        </div>
      </div>

      {/* Step Content */}
      <div className="flex-1 overflow-y-auto p-4">

        {/* ── STEP 1: Upload ── */}
        {step === 'upload' && (
          <div className="space-y-4">
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                uploading ? 'border-blue-400 bg-blue-50' : 'border-slate-300 hover:border-blue-400 hover:bg-blue-50/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileSelect}
                className="hidden"
              />
              {uploading ? (
                <>
                  <div className="animate-spin w-10 h-10 border-3 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
                  <p className="text-sm text-blue-600 font-medium">Uploading & validating...</p>
                </>
              ) : (
                <>
                  <Upload size={40} className="mx-auto mb-3 text-slate-400" />
                  <p className="text-sm font-semibold text-slate-700">Click to upload CSV</p>
                  <p className="text-xs text-slate-400 mt-1">Drag & drop or click to browse</p>
                </>
              )}
            </div>

            <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
              <p className="text-xs font-semibold text-slate-600 mb-2">Required Columns:</p>
              <div className="flex flex-wrap gap-1.5">
                {['latitude', 'longitude', 'date'].map(col => (
                  <span key={col} className="text-xs font-mono bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">{col}</span>
                ))}
              </div>
              <p className="text-xs font-semibold text-slate-600 mt-3 mb-2">Optional Columns:</p>
              <div className="flex flex-wrap gap-1.5">
                {['full_address', 'delivery_id', 'city', 'area', 'zone'].map(col => (
                  <span key={col} className="text-xs font-mono bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full">{col}</span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 2: Validate ── */}
        {step === 'validate' && validationResult && (
          <div className="space-y-4">
            {validationResult.status === 'valid' ? (
              <>
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <CheckCircle2 size={20} className="text-emerald-600" />
                    <span className="font-bold text-emerald-800">Validation Passed</span>
                  </div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileSpreadsheet size={16} className="text-emerald-600" />
                    <span className="text-sm font-medium text-emerald-700">{validationResult.filename}</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-white border border-slate-200 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-slate-800">{validationResult.total_rows}</div>
                    <div className="text-xs text-slate-500">Total Rows</div>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-emerald-600">{validationResult.valid_rows}</div>
                    <div className="text-xs text-slate-500">Valid</div>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-lg p-3 text-center">
                    <div className={`text-lg font-bold ${validationResult.invalid_rows > 0 ? 'text-amber-600' : 'text-slate-400'}`}>
                      {validationResult.invalid_rows}
                    </div>
                    <div className="text-xs text-slate-500">Invalid</div>
                  </div>
                </div>

                {/* Columns found */}
                <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                  <p className="text-xs font-semibold text-slate-600 mb-2">Columns Detected:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {validationResult.columns.map(col => {
                      const isRequired = validationResult.required_columns.includes(col);
                      return (
                        <span key={col} className={`text-xs font-mono px-2 py-0.5 rounded-full ${
                          isRequired ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                        }`}>
                          {isRequired && '✓ '}{col}
                        </span>
                      );
                    })}
                  </div>
                </div>

                <div className="text-center text-sm text-slate-500">
                  {validationResult.dates?.length || 0} unique dates found
                </div>
              </>
            ) : (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <XCircle size={20} className="text-red-600" />
                  <span className="font-bold text-red-800">Validation Failed</span>
                </div>
                <p className="text-sm text-red-700">{validationResult.message || 'Invalid file format'}</p>
                {validationResult.missing && (
                  <div className="mt-3">
                    <p className="text-xs font-semibold text-red-600">Missing columns:</p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {validationResult.missing.map(col => (
                        <span key={col} className="text-xs font-mono bg-red-200 text-red-800 px-2 py-0.5 rounded-full">{col}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── STEP 3: Select Date ── */}
        {step === 'date' && validationResult && (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-slate-700 mb-2">Select Processing Date:</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(validationResult.dates || []).map(d => (
                <button
                  key={d.date}
                  onClick={() => handleDateSelect(d)}
                  className={`w-full flex items-center justify-between p-3 rounded-lg border transition-all ${
                    selectedDate === d.date
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Calendar size={18} className={selectedDate === d.date ? 'text-blue-600' : 'text-slate-400'} />
                    <span className={`text-sm font-semibold ${selectedDate === d.date ? 'text-blue-700' : 'text-slate-700'}`}>
                      {d.date}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-bold ${selectedDate === d.date ? 'text-blue-600' : 'text-slate-500'}`}>
                      {d.count}
                    </span>
                    <span className="text-xs text-slate-400">deliveries</span>
                  </div>
                </button>
              ))}
            </div>

            {selectedDate && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-blue-800">Selected: {selectedDate}</span>
                  <span className="text-lg font-bold text-blue-700">{deliveryCount} deliveries</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── STEP 4: Configure ── */}
        {step === 'configure' && (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-blue-700 font-medium">{selectedDate}</span>
                <span className="text-blue-800 font-bold">{deliveryCount} deliveries</span>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-semibold text-slate-700 mb-1 flex items-center gap-2">
                  <Users size={16} className="text-blue-500" />
                  Number of Couriers
                </label>
                <input
                  type="number" min={2} max={100}
                  value={numCouriers}
                  onChange={e => setNumCouriers(Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-slate-800 font-semibold text-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-slate-400 mt-1">
                  ≈ {Math.round(deliveryCount / numCouriers)} deliveries per courier
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-slate-700 mb-1 block">Min per courier</label>
                  <input
                    type="number" min={1}
                    value={minPerCourier}
                    onChange={e => setMinPerCourier(Number(e.target.value))}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-700 mb-1 block">Max per courier</label>
                  <input
                    type="number" min={1}
                    value={maxPerCourier}
                    onChange={e => setMaxPerCourier(Number(e.target.value))}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              {/* Sanity check warnings */}
              {numCouriers * maxPerCourier < deliveryCount && (
                <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-xs">
                  <AlertTriangle size={16} />
                  <span>Max capacity ({numCouriers} × {maxPerCourier} = {numCouriers * maxPerCourier}) is less than deliveries ({deliveryCount})</span>
                </div>
              )}
              {numCouriers * minPerCourier > deliveryCount && (
                <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-xs">
                  <AlertTriangle size={16} />
                  <span>Min capacity ({numCouriers} × {minPerCourier} = {numCouriers * minPerCourier}) exceeds deliveries ({deliveryCount})</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Buttons */}
      <div className="p-4 border-t border-slate-200 bg-slate-50 shrink-0 space-y-2">
        {step === 'validate' && validationResult?.status === 'valid' && (
          <button onClick={proceedToDate} className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-white bg-blue-600 hover:bg-blue-700 transition-all shadow-lg hover:-translate-y-0.5">
            Continue to Date Selection <ChevronRight size={18} />
          </button>
        )}
        {step === 'validate' && validationResult?.status !== 'valid' && (
          <button onClick={handleReset} className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-white bg-slate-600 hover:bg-slate-700 transition-all">
            <RotateCcw size={18} /> Upload Another File
          </button>
        )}
        {step === 'date' && (
          <button onClick={proceedToConfigure} disabled={!selectedDate}
            className={`w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-white transition-all shadow-lg ${
              selectedDate ? 'bg-blue-600 hover:bg-blue-700 hover:-translate-y-0.5' : 'bg-slate-400 cursor-not-allowed'
            }`}>
            Continue to Configure <ChevronRight size={18} />
          </button>
        )}
        {step === 'configure' && (
          <button onClick={handleLaunch}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-white bg-emerald-600 hover:bg-emerald-700 transition-all shadow-lg hover:-translate-y-0.5">
            🚀 Start Optimization
          </button>
        )}

        {step !== 'upload' && (
          <button onClick={handleReset} className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-all">
            <RotateCcw size={14} /> Start Over
          </button>
        )}
      </div>
    </div>
  );
}
