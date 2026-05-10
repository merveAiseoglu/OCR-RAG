import React, { useState } from 'react';
import { X, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react';

export interface ValidatorResponse {
  is_complete: boolean;
  missing_fields: string[];
  document_type?: string;
  confidence?: number;
}

interface ValidatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  validatorData: ValidatorResponse;
  onSubmit: (filledFields: Record<string, string>) => Promise<void>;
}

const fieldLabels: Record<string, string> = {
  tarih: 'Tarih',
  tc_no: 'TC Kimlik No',
  ad_soyad: 'Ad Soyad',
  adres: 'Adres',
  telefon: 'Telefon',
  imza: 'İmza',
  tutar: 'Tutar (₺)',
  vergi_no: 'Vergi No',
  iban: 'IBAN',
  sozlesme_no: 'Sözleşme No',
};

const fieldTypes: Record<string, string> = {
  tarih: 'date',
  tc_no: 'text',
  telefon: 'tel',
  tutar: 'number',
  iban: 'text',
};

export const ValidatorModal: React.FC<ValidatorModalProps> = ({
  isOpen,
  onClose,
  validatorData,
  onSubmit,
}) => {
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  if (!isOpen) return null;

  const handleChange = (field: string, value: string) => {
    setFieldValues((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit(fieldValues);
      setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
      }, 1500);
    } catch {
      // handle error silently
    } finally {
      setIsSubmitting(false);
    }
  };

  const allFilled = validatorData.missing_fields.every((f) => fieldValues[f]?.trim());

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[200] flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-[#1a1d24] rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 w-full max-w-lg animate-in slide-in-from-bottom-4 duration-300">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 dark:bg-amber-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Eksik Bilgi Tespiti</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {validatorData.document_type
                  ? `"${validatorData.document_type}" belgesinde`
                  : 'Belgede'}{' '}
                {validatorData.missing_fields.length} eksik alan bulundu.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4">
          {isSuccess ? (
            <div className="flex flex-col items-center gap-3 py-8 animate-in zoom-in duration-300">
              <CheckCircle className="w-12 h-12 text-emerald-500" />
              <p className="font-semibold text-slate-800 dark:text-slate-200">Bilgiler kaydedildi!</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3">
                {validatorData.missing_fields.map((field) => (
                  <div key={field} className="flex flex-col gap-1.5">
                    <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
                      {fieldLabels[field] ?? field}
                    </label>
                    <input
                      type={fieldTypes[field] ?? 'text'}
                      placeholder={`${fieldLabels[field] ?? field} giriniz...`}
                      value={fieldValues[field] ?? ''}
                      onChange={(e) => handleChange(field, e.target.value)}
                      className="w-full bg-slate-50 dark:bg-[#12141a] border border-slate-200 dark:border-slate-700 focus:border-indigo-500 dark:focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/50 rounded-xl px-3 py-2.5 text-sm text-slate-800 dark:text-slate-200 outline-none transition-all placeholder:text-slate-400"
                    />
                  </div>
                ))}
              </div>

              <div className="flex gap-3 mt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  İptal
                </button>
                <button
                  type="submit"
                  disabled={!allFilled || isSubmitting}
                  className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
                >
                  {isSubmitting ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Gönderiliyor...</>
                  ) : (
                    'Bilgileri Tamamla'
                  )}
                </button>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  );
};
