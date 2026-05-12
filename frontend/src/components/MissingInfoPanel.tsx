import React from 'react';
import { AlertTriangle, CheckCircle } from 'lucide-react';

interface MissingInfoPanelProps {
  missingFields: string[];
  isComplete: boolean;
}

const fieldLabels: Record<string, string> = {
  tc_no: 'TC Kimlik No',
  iban: 'IBAN Bilgisi',
  eposta: 'E-posta Adresi',
  ad_soyad: 'Ad Soyad',
  telefon: 'Telefon Numarası',
  tutar: 'Tutar Bilgisi',
};

export const MissingInfoPanel: React.FC<MissingInfoPanelProps> = ({ missingFields, isComplete }) => {
  // Tekrarlayanları temizle
  const uniqueFields = Array.from(new Set(missingFields));
  const hasMissing = !isComplete && uniqueFields.length > 0;

  return (
    <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-sm transition-colors duration-500 ${hasMissing ? 'bg-amber-100 dark:bg-amber-500/20' : 'bg-emerald-100 dark:bg-emerald-500/20'}`}>
          {hasMissing ? (
            <AlertTriangle className="w-5 h-5 text-amber-500 animate-pulse" />
          ) : (
            <CheckCircle className="w-5 h-5 text-emerald-500" />
          )}
        </div>
        <div>
          <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {hasMissing ? 'Belge Eksiklikleri' : 'Doğrulama Tamamlandı'}
          </h2>
          <p className="text-[11px] text-slate-500">
            {hasMissing ? `${uniqueFields.length} adet eksik tespit edildi` : 'Tüm kriterler sağlandı'}
          </p>
        </div>
      </div>

      {hasMissing ? (
        <div className="space-y-3">
          {uniqueFields.map((field, idx) => (
            <div 
              key={field + idx} 
              className="flex items-center gap-3 p-3 bg-amber-50/50 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/20 rounded-xl animate-in slide-in-from-bottom-2 duration-300 group hover:border-amber-300 dark:hover:border-amber-500/40 transition-all"
              style={{ animationDelay: `${idx * 100}ms` }}
            >
              <div className="w-6 h-6 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                <span className="text-amber-600 dark:text-amber-400 text-xs">⚠️</span>
              </div>
              <span className="text-sm font-medium text-amber-900 dark:text-amber-200">
                {fieldLabels[field.toLowerCase()] ?? field} Eksik
              </span>
            </div>
          ))}
          
          <div className="mt-4 p-4 bg-slate-100 dark:bg-[#1a1d24] rounded-2xl border border-slate-200 dark:border-slate-800">
            <p className="text-[11px] text-slate-500 italic text-center">
              Lütfen belgeyi bu eksiklere göre kontrol ediniz. Sistem şu an sadece görüntüleme modundadır.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center gap-4 bg-emerald-50/30 dark:bg-emerald-500/5 rounded-3xl border border-emerald-100 dark:border-emerald-500/10">
          <div className="w-20 h-20 bg-emerald-100 dark:bg-emerald-500/20 rounded-full flex items-center justify-center animate-bounce duration-[2000ms]">
            <CheckCircle className="w-10 h-10 text-emerald-500" />
          </div>
          <div className="space-y-2">
            <h3 className="text-base font-bold text-emerald-600 dark:text-emerald-400">Belge Başarıyla Doğrulandı</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">Belgede eksik bilgi bulunmamaktadır.</p>
          </div>
        </div>
      )}
    </div>
  );
};
