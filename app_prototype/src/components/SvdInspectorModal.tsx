import React, { useState } from 'react';
import {
  X,
  FileCode2,
  Upload,
  Cpu,
  Sliders,
  Check,
  Copy,
  Binary,
  Layers,
  ArrowRight
} from 'lucide-react';
import { MOCK_SVD_PERIPHERALS } from '../data/mockHardwareData';
import { SvdPeripheral, SvdRegister } from '../types/hardware';

interface SvdInspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialRegisterName?: string | null;
}

export const SvdInspectorModal: React.FC<SvdInspectorModalProps> = ({
  isOpen,
  onClose,
  initialRegisterName
}) => {
  const [activeTab, setActiveTab] = useState<'inspector' | 'upload'>('inspector');
  const [selectedPeripheral, setSelectedPeripheral] = useState<SvdPeripheral>(MOCK_SVD_PERIPHERALS[0]);
  const [selectedRegister, setSelectedRegister] = useState<SvdRegister>(() => {
    if (initialRegisterName) {
      for (const p of MOCK_SVD_PERIPHERALS) {
        const found = p.registers.find(r => r.name.toLowerCase() === initialRegisterName.toLowerCase());
        if (found) return found;
      }
    }
    return MOCK_SVD_PERIPHERALS[0].registers[0];
  });

  // State for bitfield values in current register
  const [fieldValues, setFieldValues] = useState<Record<string, number>>({
    HSW: 40,
    VSH: 9,
    AHBP: 79,
    AVBP: 37
  });

  const [copiedMacro, setCopiedMacro] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState('');

  if (!isOpen) return null;

  // Calculate composite 32-bit register value
  const calculateTotalHex = (): { hex: string; decimal: number; bits: string } => {
    let total = 0;
    selectedRegister.fields.forEach(f => {
      const rawVal = fieldValues[f.name] ?? f.resetValue ?? 0;
      // In LTDC registers, loaded value is often (N - 1)
      const adjustedVal = (f.name === 'HSW' || f.name === 'VSH') ? Math.max(0, rawVal - 1) : rawVal;
      const mask = (1 << (f.bitEnd - f.bitStart + 1)) - 1;
      const maskedVal = adjustedVal & mask;
      total |= (maskedVal << f.bitStart);
    });

    const hex = `0x${(total >>> 0).toString(16).toUpperCase().padStart(8, '0')}`;
    const bits = (total >>> 0).toString(2).padStart(32, '0');
    return { hex, decimal: total >>> 0, bits };
  };

  const { hex, decimal, bits } = calculateTotalHex();

  const handleFieldChange = (fieldName: string, valStr: string) => {
    const num = parseInt(valStr, 10);
    setFieldValues(prev => ({
      ...prev,
      [fieldName]: isNaN(num) ? 0 : num
    }));
  };

  const handleCopyMacros = () => {
    const macroStr = `/* CMSIS Register & Bitfield Definition for ${selectedRegister.name} */
#define ${selectedRegister.name}_ADDR (${selectedPeripheral.baseAddress} + ${selectedRegister.offset})
${selectedRegister.fields.map(f => {
  const mask = ((1 << (f.bitEnd - f.bitStart + 1)) - 1) << f.bitStart;
  return `#define ${selectedRegister.name}_${f.name}_Pos ${f.bitStart}U\n#define ${selectedRegister.name}_${f.name}_Msk (0x${mask.toString(16).toUpperCase()}UL)`;
}).join('\n')}

// Calculated value for panel: ${hex} (${decimal})
${selectedRegister.name} = ${hex};`;

    navigator.clipboard.writeText(macroStr);
    setCopiedMacro(true);
    setTimeout(() => setCopiedMacro(false), 2000);
  };

  const handleSimulateUpload = (filename: string) => {
    setUploadedFileName(filename);
    setUploadSuccess(true);
    setTimeout(() => {
      setActiveTab('inspector');
    }, 1200);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-4xl max-h-[85vh] bg-[#0c1017] border border-white/[0.1] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-[#10151f]">
          <div className="flex items-center gap-3">
            <FileCode2 className="w-5 h-5 text-cyan-400" />
            <div>
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                SVD Register & Bitfield Explorer
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                CMSIS SVD 1.3 parser & memory map bitmask calculator
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Tabs */}
            <div className="flex items-center p-1 bg-white/[0.04] rounded-lg border border-white/[0.06] text-xs font-mono">
              <button
                onClick={() => setActiveTab('inspector')}
                className={`px-3 py-1 rounded transition-colors ${
                  activeTab === 'inspector'
                    ? 'bg-cyan-950/80 text-cyan-300 font-medium border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Bitfield Inspector
              </button>
              <button
                onClick={() => setActiveTab('upload')}
                className={`px-3 py-1 rounded transition-colors ${
                  activeTab === 'upload'
                    ? 'bg-cyan-950/80 text-cyan-300 font-medium border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Upload SVD / PDF
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08] rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        {activeTab === 'inspector' ? (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Top selectors: Peripheral & Register */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1.5">
                  Target Peripheral
                </label>
                <select
                  value={selectedPeripheral.name}
                  onChange={(e) => {
                    const p = MOCK_SVD_PERIPHERALS.find(item => item.name === e.target.value);
                    if (p) {
                      setSelectedPeripheral(p);
                      setSelectedRegister(p.registers[0]);
                    }
                  }}
                  className="w-full bg-[#131923] border border-white/[0.1] rounded-lg px-3 py-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  {MOCK_SVD_PERIPHERALS.map(p => (
                    <option key={p.name} value={p.name}>
                      {p.name} ({p.baseAddress}) - {p.description}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1.5">
                  Register
                </label>
                <select
                  value={selectedRegister.name}
                  onChange={(e) => {
                    const r = selectedPeripheral.registers.find(item => item.name === e.target.value);
                    if (r) setSelectedRegister(r);
                  }}
                  className="w-full bg-[#131923] border border-white/[0.1] rounded-lg px-3 py-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  {selectedPeripheral.registers.map(r => (
                    <option key={r.name} value={r.name}>
                      {r.name} (Offset {r.offset})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Calculated Composite Register Card */}
            <div className="p-4 rounded-xl bg-[#131923] border border-white/[0.08] space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-mono text-slate-400">Calculated Value:</span>
                  <div className="text-2xl font-mono font-bold text-cyan-400 tracking-wider">
                    {hex}
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="text-xs font-mono text-slate-400">Decimal:</span>
                    <div className="text-sm font-mono text-slate-200">{decimal}</div>
                  </div>
                  <button
                    onClick={handleCopyMacros}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 text-xs font-mono hover:bg-cyan-900 transition-colors"
                  >
                    {copiedMacro ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Copied Macros</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy CMSIS C Code</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* 32-Bit Visual Strip (Bits 31 down to 0) */}
              <div className="space-y-1 pt-2">
                <div className="flex justify-between text-[10px] font-mono text-slate-500 px-1">
                  <span>31 (MSB)</span>
                  <span>16</span>
                  <span>15</span>
                  <span>0 (LSB)</span>
                </div>
                <div className="grid grid-cols-32 gap-0.5 p-2 bg-black/50 rounded-lg border border-white/[0.06] overflow-x-auto">
                  {bits.split('').map((bit, idx) => {
                    const bitIndex = 31 - idx;
                    // Check if bit is in a defined field
                    const activeField = selectedRegister.fields.find(
                      f => bitIndex >= f.bitStart && bitIndex <= f.bitEnd
                    );

                    let bgColor = "bg-white/[0.05] text-slate-500";
                    if (activeField) {
                      bgColor = bit === '1' ? 'bg-cyan-500 text-black font-bold' : 'bg-cyan-950 text-cyan-300';
                    }

                    return (
                      <div
                        key={idx}
                        title={`Bit ${bitIndex} (${activeField ? activeField.name : 'Reserved'}): ${bit}`}
                        className={`h-7 min-w-[18px] flex flex-col items-center justify-center rounded text-[10px] font-mono select-none ${bgColor}`}
                      >
                        {bit}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Individual Bitfields Breakdown */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase tracking-wider">
                Bitfields in {selectedRegister.name}
              </h3>

              <div className="space-y-2">
                {selectedRegister.fields.map((field) => {
                  const val = fieldValues[field.name] ?? field.resetValue;
                  const bitRange = field.bitStart === field.bitEnd
                    ? `[${field.bitStart}]`
                    : `[${field.bitEnd}:${field.bitStart}]`;

                  return (
                    <div
                      key={field.name}
                      className="p-3 rounded-lg bg-[#111721] border border-white/[0.06] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 font-mono text-xs"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-cyan-300 text-sm">{field.name}</span>
                          <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400">
                            Bits {bitRange}
                          </span>
                          <span className="text-[10px] px-1 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-500/20">
                            {field.access}
                          </span>
                        </div>
                        <p className="text-slate-400 text-[11px] mt-0.5">{field.description}</p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <label className="text-[11px] text-slate-400">Value:</label>
                        <input
                          type="number"
                          value={val}
                          onChange={(e) => handleFieldChange(field.name, e.target.value)}
                          className="w-24 bg-black/40 border border-white/[0.1] rounded px-2 py-1 text-slate-200 text-right focus:outline-none focus:border-cyan-500"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* Upload SVD / Datasheet Tab */
          <div className="flex-1 overflow-y-auto p-8 flex flex-col items-center justify-center text-center space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Upload className="w-8 h-8" />
            </div>

            <div className="max-w-md space-y-1">
              <h3 className="text-base font-semibold text-slate-200 font-mono">
                Index Vendor SVD or Datasheet PDF
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Upload ARM CMSIS-SVD (.svd, .xml) or Reference Manual (.pdf). The Python backend extracts registers, peripheral base addresses, and bitfield tables into vector embeddings.
              </p>
            </div>

            {uploadSuccess ? (
              <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs font-mono flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" />
                <span>Successfully parsed {uploadedFileName || 'STM32H743.svd'}. 42 Peripherals indexed!</span>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={() => handleSimulateUpload('STM32H743xI.svd')}
                  className="px-4 py-2 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-200 text-xs font-mono transition-colors"
                >
                  Load Sample STM32H7.svd
                </button>
                <button
                  onClick={() => handleSimulateUpload('ESP32S3_TRM_v1.4.pdf')}
                  className="px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.1] text-slate-300 text-xs font-mono transition-colors"
                >
                  Load ESP32-S3 TRM.pdf
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
