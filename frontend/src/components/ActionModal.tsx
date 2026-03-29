import { useState } from 'react';
import axios from 'axios';
import { Calendar, CheckSquare, Loader2, X } from 'lucide-react';

interface ActionModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  type: 'calendar' | 'tasks';
  data: any;
}

const API_URL = 'http://localhost:8000';

export function ActionModal({ isOpen, onClose, title, type, data }: ActionModalProps) {
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  if (!isOpen) return null;

  const handleAction = async () => {
    setLoading(true);
    setSuccessMsg('');
    try {
      if (type === 'calendar') {
        const response = await axios.post(`${API_URL}/api/takvime-ekle`, {
          task_id: "modal_" + Date.now().toString(),
          action: "calendar_event",
          task_title: data.baslik || title,
          task_date: data.tarih || ""
        });
        
        if (response.data && response.data.status === "error") {
          alert(`Hata:\n${response.data.message}`);
        } else {
          setSuccessMsg('Takvime başarıyla eklendi!');
          setTimeout(() => {
            onClose();
            setSuccessMsg('');
          }, 2000);
        }
      } else {
        const response = await axios.post(`${API_URL}/api/action/tasks/add`, data);
        setSuccessMsg(response.data.message || 'Görev başarıyla eklendi!');
        setTimeout(() => {
          onClose();
          setSuccessMsg('');
        }, 2000);
      }
    } catch (error: any) {
      console.error("Aksiyon hatası:", error);
      alert(`Bir hata oluştu:\n${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-[60] flex items-center justify-center animate-in fade-in duration-200">
      <div className="bg-white rounded-lg p-6 max-w-sm w-full shadow-2xl scale-100 transition-transform">
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center space-x-2">
            {type === 'calendar' ? (
              <Calendar className="w-6 h-6 text-blue-500" />
            ) : (
              <CheckSquare className="w-6 h-6 text-green-500" />
            )}
            <h3 className="text-xl font-bold text-gray-800">{type === 'calendar' ? 'Takvime Ekle' : 'Görev Olarak Ekle'}</h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-gray-600 mb-6">
          AI ajanı şu aksiyonu öneriyor: <br />
          <strong className="text-gray-800">{title}</strong> <br />
          Onaylıyor musunuz?
        </p>

        {successMsg && (
          <div className="mb-4 bg-green-50 text-green-700 p-3 rounded-lg text-sm border border-green-200">
            {successMsg}
          </div>
        )}

        <div className="flex space-x-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 py-2 px-4 bg-gray-100 font-medium text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            Vazgeç
          </button>
          <button
            onClick={handleAction}
            disabled={loading || !!successMsg}
            className={`flex-1 flex items-center justify-center py-2 px-4 text-white font-medium rounded-lg transition-colors disabled:opacity-50 ${type === 'calendar' ? 'bg-blue-600 hover:bg-blue-700' : 'bg-green-600 hover:bg-green-700'}`}
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Evet, Ekle'}
          </button>
        </div>
      </div>
    </div>
  );
}
