import React, { useState } from 'react';
import { ShieldAlert, ChevronDown, ChevronUp, AlertTriangle, Info, CheckCircle, XCircle } from 'lucide-react';

export interface AuditorChange {
  type: 'ekleme' | 'silme' | 'degisiklik' | 'risk';
  title: string;
  description: string;
  severity?: 'low' | 'medium' | 'high';
}

export interface AuditorResponse {
  risk_score: number; // 0–10
  executive_summary: string;
  changes: AuditorChange[];
  missing_clauses: string[];
  timestamp?: string;
}

interface AuditorReportProps {
  data: AuditorResponse;
  onItemClick?: (detail: string) => void;
}

const severityConfig = {
  low: {
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-500/10',
    border: 'border-emerald-200 dark:border-emerald-500/30',
    icon: CheckCircle,
    label: 'Düşük Risk',
  },
  medium: {
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-500/10',
    border: 'border-amber-200 dark:border-amber-500/30',
    icon: AlertTriangle,
    label: 'Orta Risk',
  },
  high: {
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-500/10',
    border: 'border-red-200 dark:border-red-500/30',
    icon: XCircle,
    label: 'Yüksek Risk',
  },
};

const typeConfig = {
  ekleme: { label: 'Ekleme', badge: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300' },
  silme: { label: 'Silme', badge: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300' },
  degisiklik: { label: 'Değişiklik', badge: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300' },
  risk: { label: 'Risk', badge: 'bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300' },
};

function RiskRing({ score }: { score: number }) {
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(score / 10, 1);
  const offset = circumference * (1 - progress);

  const color =
    score >= 7
      ? '#ef4444' // red
      : score >= 4
      ? '#f97316' // orange
      : '#22c55e'; // green

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
          <circle cx="60" cy="60" r={radius} fill="none" stroke="currentColor" strokeWidth="10" className="text-slate-200 dark:text-slate-700" />
          <circle
            cx="60" cy="60" r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(.4,0,.2,1)' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-4xl font-black" style={{ color }}>{score}</span>
          <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">/10</span>
        </div>
      </div>
      <span className="text-sm font-bold" style={{ color }}>
        {score >= 7 ? 'Yüksek Risk' : score >= 4 ? 'Orta Risk' : 'Düşük Risk'}
      </span>
    </div>
  );
}

function AccordionCard({ item, onClick }: { item: AuditorChange; onClick?: () => void }) {
  const [open, setOpen] = useState(false);
  const sev = item.severity ?? 'medium';
  const cfg = severityConfig[sev as keyof typeof severityConfig] || severityConfig.medium;
  const typeCfg = typeConfig[item.type as keyof typeof typeConfig] || typeConfig.risk;
  const Icon = cfg.icon;

  return (
    <div className={`border ${cfg.border} ${cfg.bg} rounded-xl overflow-hidden transition-all duration-200`}>
      <button
        onClick={() => {
          setOpen(!open);
          if (!open && onClick) onClick();
        }}
        className="w-full flex items-center gap-3 p-4 text-left group"
      >
        <Icon className={`w-4 h-4 flex-shrink-0 ${cfg.color} group-hover:scale-110 transition-transform`} />
        <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-200">{item.title}</span>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${typeCfg.badge}`}>{typeCfg.label}</span>
        {open ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />}
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-slate-600 dark:text-slate-400 leading-relaxed border-t border-slate-200/50 dark:border-slate-700/50 pt-3 animate-in slide-in-from-top-2 duration-200">
          {item.description}
        </div>
      )}
    </div>
  );
}

export const AuditorReport: React.FC<AuditorReportProps> = ({ data, onItemClick }) => {
  const [showMissing, setShowMissing] = useState(false);

  return (
    <div className="w-full bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-800 to-slate-900 dark:from-[#0f1115] dark:to-[#12141a] px-6 py-5 flex items-center gap-3">
        <div className="w-9 h-9 bg-red-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
          <ShieldAlert className="w-5 h-5 text-red-400" />
        </div>
        <div>
          <h2 className="text-white font-bold text-base">Sözleşme Denetçi Raporu</h2>
          {data.timestamp && (
            <p className="text-slate-400 text-xs mt-0.5">{new Date(data.timestamp).toLocaleString('tr-TR')}</p>
          )}
        </div>
      </div>

      <div className="p-6 flex flex-col gap-6">
        {/* Risk Score */}
        <div className="flex flex-col sm:flex-row items-center gap-6">
          <RiskRing score={data.risk_score} />
          <div className="flex-1">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" /> Yönetici Özeti
            </p>
            <p className="text-slate-800 dark:text-slate-200 text-sm leading-relaxed font-medium">
              {data.executive_summary}
            </p>
          </div>
        </div>

        {/* Changes */}
        {data.changes.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
              Tespit Edilen Değişiklikler & Riskler ({data.changes.length})
            </h3>
            {data.changes.map((item, i) => (
              <AccordionCard 
                key={i} 
                item={item} 
                onClick={() => onItemClick?.(`**${item.title}**: ${item.description}`)}
              />
            ))}
          </div>
        )}

        {/* Missing Clauses */}
        {data.missing_clauses.length > 0 && (
          <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowMissing(!showMissing)}
              className="w-full flex items-center justify-between p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  Eksik Maddeler ({data.missing_clauses.length})
                </span>
              </div>
              {showMissing ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>
            {showMissing && (
              <ul className="border-t border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800 animate-in slide-in-from-top-2 duration-200">
                {data.missing_clauses.map((clause, i) => (
                  <li key={i} className="px-4 py-3 flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                    <span className="w-5 h-5 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center text-[10px] font-bold text-slate-500 flex-shrink-0">{i + 1}</span>
                    {clause}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
