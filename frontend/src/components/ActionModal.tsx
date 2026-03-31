import { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar, CheckSquare, Loader2, X, StickyNote } from 'lucide-react';

interface ActionModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  type: 'calendar' | 'tasks' | 'notes';
  data: any;
}

const API_URL = 'http://localhost:8000';

export function ActionModal({ isOpen, onClose, title, type, data }: ActionModalProps) {
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  
  // Date Picker State
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    return data.tarih || new Date().toISOString().split('T')[0];
  });
  const [customDateMode, setCustomDateMode] = useState<boolean>(false);

  // Editable Title State
  const [editableTitle, setEditableTitle] = useState('');
  
  // Editable Content State for Notes
  const [editableContent, setEditableContent] = useState('');

  // Update states when new data comes in
  useEffect(() => {
    if (data.tarih) {
      setSelectedDate(data.tarih);
    } else if (data.availableDates && data.availableDates.length > 0) {
      setSelectedDate(data.availableDates[0]);
    }
    
    // Default to the agent's found text (baslik), or fallback to title
    setEditableTitle(data.baslik || title || '');
    
    // Set editable content for notes
    if (data.icerik) {
      setEditableContent(data.icerik);
    }
  }, [data, title, isOpen]);


  if (!isOpen) return null;

  const handleAction = async () => {
    setLoading(true);
    setSuccessMsg('');
    try {
      if (type === 'calendar') {
        const payloadDate = customDateMode ? selectedDate : (selectedDate || data.tarih || "");
        
        const response = await axios.post(`${API_URL}/api/action/calendar/add`, {
          task_id: "modal_" + Date.now().toString(),
          action: "calendar_event",
          task_title: editableTitle,
          task_date: payloadDate
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
      } else if (type === 'notes') {
        // Not gönderimi
        const finalContent = editableTitle ? `**${editableTitle}**\n\n${editableContent}` : editableContent;
        await axios.post(`${API_URL}/api/notes`, { content: finalContent });
        setSuccessMsg('Not başarıyla kaydedildi!');
        setTimeout(() => {
          onClose();
          setSuccessMsg('');
        }, 2000);
      } else {
        const payloadData = { ...data, baslik: editableTitle };
        const response = await axios.post(`${API_URL}/api/action/tasks/add`, payloadData);
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
            ) : type === 'notes' ? (
              <StickyNote className="w-6 h-6 text-purple-600" />
            ) : (
              <CheckSquare className="w-6 h-6 text-green-500" />
            )}
            <h3 className="text-xl font-bold text-gray-800">
              {type === 'calendar' ? 'Takvime Ekle' : type === 'notes' ? 'Notlara Kaydet' : 'Görev Olarak Ekle'}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mb-5">
          <label className="block text-sm font-semibold text-purple-700 mb-2">
            {type === 'calendar' ? 'Etkinlik Başlığı' : type === 'notes' ? 'Not Başlığı' : 'Görev Başlığı'}
          </label>
          <input 
            type="text"
            value={editableTitle}
            onChange={(e) => setEditableTitle(e.target.value)}
            className="w-full bg-purple-50 text-gray-800 font-medium p-3 rounded-lg border-none ring-1 ring-purple-100 hover:ring-purple-200 focus:ring-2 focus:ring-purple-500 focus:bg-white outline-none transition-all shadow-sm"
            placeholder="Bir başlık girin..."
          />
        </div>

        {type === 'notes' && (
          <div className="mb-6">
            <label className="block text-sm font-semibold text-purple-700 mb-2">Not İçeriği</label>
            <textarea
              value={editableContent}
              onChange={(e) => setEditableContent(e.target.value)}
              className="w-full bg-purple-50 text-gray-800 p-3 rounded-lg border-none ring-1 ring-purple-100 hover:ring-purple-200 focus:ring-2 focus:ring-purple-500 focus:bg-white outline-none transition-all shadow-sm min-h-[150px] resize-y"
              placeholder="Notunuzu buraya yazın veya düzenleyin..."
            />
          </div>
        )}

        {type === 'calendar' && (
          <div className="mb-6">
            <label className="block text-sm font-semibold text-gray-700 mb-2">Tarih Seçimi</label>
            {data.availableDates && data.availableDates.length > 1 && !customDateMode ? (
              <div className="flex flex-col gap-2 mb-3 bg-gray-50 p-3 rounded-lg border border-gray-200">
                <span className="text-xs text-gray-500 mb-1">Belgede birden fazla tarih bulundu. Lütfen birini seçin:</span>
                {data.availableDates.map((dateStr: string, idx: number) => (
                  <label key={idx} className="flex items-center space-x-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="dateSelection" 
                      value={dateStr}
                      checked={selectedDate === dateStr}
                      onChange={(e) => setSelectedDate(e.target.value)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-800">{dateStr}</span>
                  </label>
                ))}
                <button 
                  onClick={() => setCustomDateMode(true)}
                  className="text-xs text-blue-600 hover:text-blue-800 mt-2 text-left underline"
                >
                  Farklı bir tarih gir...
                </button>
              </div>
            ) : (
              <div className="flex flex-col">
                <input 
                  type="date" 
                  value={selectedDate} 
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full border-2 border-gray-300 rounded-lg p-2 focus:border-blue-500 focus:outline-none"
                />
                {data.availableDates && data.availableDates.length > 1 && customDateMode && (
                  <button 
                    onClick={() => setCustomDateMode(false)}
                    className="text-xs text-gray-500 hover:text-gray-700 mt-2 text-left underline"
                  >
                    Asistanın bulduğu tarihlere dön
                  </button>
                )}
              </div>
            )}
          </div>
        )}

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
            className={`flex-1 flex items-center justify-center py-2 px-4 text-white font-medium rounded-lg transition-colors disabled:opacity-50 ${
              type === 'calendar' ? 'bg-blue-600 hover:bg-blue-700' : 
              type === 'notes' ? 'bg-purple-600 hover:bg-purple-700' : 
              'bg-green-600 hover:bg-green-700'
            }`}
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Kaydet'}
          </button>
        </div>
      </div>
    </div>
  );
}
