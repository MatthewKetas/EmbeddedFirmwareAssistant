import React from 'react';
import { X, BookOpen, ExternalLink, CheckCircle2, AlertTriangle, Copy, Check } from 'lucide-react';
import { CitedDoc } from '../types/hardware';

interface CitedDocsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citations: CitedDoc[];
  selectedDocId?: string | null;
}

export const CitedDocsDrawer: React.FC<CitedDocsDrawerProps> = ({
  isOpen,
  onClose,
  citations,
  selectedDocId
}) => {
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopyCitation = (doc: CitedDoc) => {
    const text = `// Reference: ${doc.title} (${doc.docCode})\n// Section: ${doc.section}\n// Note: ${doc.snippet}`;
    navigator.clipboard.writeText(text);
    setCopiedId(doc.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200">
      <div className="w-full max-w-xl h-full bg-[#0c1017] border-l border-white/[0.08] shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/[0.07] bg-[#10151f]">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-mono font-semibold text-slate-100">
              Cited Hardware Documentation ({citations.length})
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 hover:bg-white/[0.08] rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 font-sans text-xs">
          <p className="text-slate-400 font-mono text-[11px] leading-relaxed">
            The following documentation excerpts were retrieved by the RAG vector engine and verified against official silicon vendor reference manuals and errata sheets.
          </p>

          {citations.map((doc) => {
            const isHighlight = selectedDocId === doc.id;
            const isErrata = doc.type === 'errata';

            return (
              <div
                key={doc.id}
                className={`rounded-xl border p-4 transition-all ${
                  isHighlight
                    ? 'border-cyan-500/60 bg-cyan-950/20'
                    : isErrata
                    ? 'border-amber-500/30 bg-amber-950/10'
                    : 'border-white/[0.08] bg-[#131923]'
                }`}
              >
                {/* Top Badge & Code */}
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span
                    className={`font-mono text-[11px] px-2 py-0.5 rounded font-semibold ${
                      isErrata
                        ? 'bg-amber-950/80 text-amber-300 border border-amber-500/40'
                        : 'bg-cyan-950/80 text-cyan-300 border border-cyan-500/40'
                    }`}
                  >
                    {doc.docCode}
                  </span>

                  <div className="flex items-center gap-1.5 text-slate-400">
                    {doc.verified && (
                      <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Verified
                      </span>
                    )}
                  </div>
                </div>

                {/* Title and section */}
                <h3 className="text-slate-200 font-semibold text-sm mb-1">{doc.title}</h3>
                <div className="text-slate-400 font-mono text-[11px] mb-3">{doc.section}</div>

                {/* Excerpt quote */}
                <blockquote className="p-3 rounded-lg bg-black/40 border border-white/[0.05] text-slate-300 font-mono text-xs leading-relaxed italic mb-3">
                  "{doc.snippet}"
                </blockquote>

                {/* Page details and action */}
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.05] text-[11px] font-mono">
                  <span className="text-slate-400">
                    Source Page: <strong className="text-slate-200">{doc.page}</strong>
                  </span>

                  <button
                    onClick={() => handleCopyCitation(doc)}
                    className="flex items-center gap-1 text-slate-400 hover:text-cyan-300 transition-colors"
                  >
                    {copiedId === doc.id ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy C Comment</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
