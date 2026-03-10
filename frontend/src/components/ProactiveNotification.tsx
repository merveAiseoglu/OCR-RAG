import { useEffect, useState } from 'react';
import axios from 'axios';
import { Bell, X } from 'lucide-react';

interface Finding {
  id: string;
  mesaj: string;
  tarih: string;
  tip: string;
}

const API_URL = 'http://localhost:8000';

export function ProactiveNotification() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // 15 saniyede bir yeni bildirim var mı diye kontrol et (Mocking proactive agent)
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_URL}/api/agent/proactive-search`);
        if (response.data && response.data.bulunanlar.length > 0) {
          setFindings(response.data.bulunanlar);
          setVisible(true);
        }
      } catch (error) {
        console.error("Proaktif arama hatası:", error);
      }
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  if (!visible || findings.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-bottom-5 fade-in duration-500">
      <div className="bg-white border-l-4 border-indigo-500 shadow-2xl rounded-r-lg p-4 max-w-sm flex items-start space-x-4">
        <div className="bg-indigo-100 p-2 rounded-full">
          <Bell className="w-6 h-6 text-indigo-600 animate-bounce" />
        </div>
        <div className="flex-1">
          <h4 className="font-bold text-gray-800">Senin için buldum 👋</h4>
          <p className="text-sm text-gray-600 mt-1">{findings[0].mesaj}</p>
          <span className="text-xs text-gray-400 mt-2 block">{findings[0].tarih}</span>
        </div>
        <button onClick={() => setVisible(false)} className="text-gray-400 hover:text-gray-600">
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
