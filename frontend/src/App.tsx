import React, { useState, useEffect } from 'react';
import { Search, Upload, Camera, FileText, Loader2, CheckCircle, XCircle, Menu, X, MessageSquare, Trash2 } from 'lucide-react';
import axios from 'axios';
import { ProactiveNotification } from './components/ProactiveNotification';
import { ActionModal } from './components/ActionModal';

const API_URL = 'http://localhost:8000';

interface Source {
  source: string;
  page: number;
  type: string;
}

interface QueryResponse {
  cevap: string;
  kaynaklar: Source[];
}

interface UploadResponse {
  success: boolean;
  mesaj: string;
  chunk_sayisi: number;
}

interface OCRResponse {
  cevap: string;
  okunan_ham_veri: string;
}

// --- YENİ: Geçmiş Kaydı İçin Tip Tanımı ---
interface HistoryItem {
  id: string;
  soru: string;
  response: QueryResponse;
  timestamp: string;
}

type TabType = 'soru' | 'fotograf' | 'yukle';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('soru');

  // --- YENİ: Sidebar ve Geçmiş State'leri ---
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  // --- YENİ: Action Modal State'leri ---
  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState('');
  const [modalType, setModalType] = useState<'calendar' | 'tasks'>('calendar');
  const [modalData, setModalData] = useState<any>({});

  // --- YENİ: Mock Task State ---
  const [mockTask, setMockTask] = useState<any>(null);
  const [isTaskActionLoading, setIsTaskActionLoading] = useState(false);
  const [taskSuccessMessage, setTaskSuccessMessage] = useState('');

  // State
  const [soru, setSoru] = useState('');
  const [soruLoading, setSoruLoading] = useState(false);
  const [soruResponse, setSoruResponse] = useState<QueryResponse | null>(null);
  const [soruError, setSoruError] = useState('');

  const [fotoFile, setFotoFile] = useState<File | null>(null);
  const [fotoSoru, setFotoSoru] = useState('Bu belgede ne yazıyor?');
  const [fotoLoading, setFotoLoading] = useState(false);
  const [fotoResponse, setFotoResponse] = useState<OCRResponse | null>(null);
  const [fotoError, setFotoError] = useState('');

  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfSuccess, setPdfSuccess] = useState('');
  const [pdfError, setPdfError] = useState('');

  // --- YENİ: Uygulama açılınca geçmişi yükle ---
  useEffect(() => {
    const savedHistory = localStorage.getItem('chatHistory');
    if (savedHistory) {
      setHistory(JSON.parse(savedHistory));
    }

    // YENİ: Mock task çekme işlemi
    const fetchMockTask = async () => {
      try {
        const response = await axios.get(`${API_URL}/api/mock-task`);
        if (response.data && response.data.title) {
          setMockTask(response.data);
        }
      } catch (e) {
        console.error("Mock task fetch hatası", e);
      }
    };

    // UI yüklendikten 1.5 saniye sonra bildirimi göster
    setTimeout(fetchMockTask, 1500);

  }, []);

  // --- YENİ: Geçmişe Kaydetme Fonksiyonu ---
  const saveToHistory = (soruText: string, resp: QueryResponse) => {
    const newItem: HistoryItem = {
      id: Date.now().toString(),
      soru: soruText,
      response: resp,
      timestamp: new Date().toLocaleDateString('tr-TR')
    };

    const updatedHistory = [newItem, ...history];
    setHistory(updatedHistory);
    localStorage.setItem('chatHistory', JSON.stringify(updatedHistory));
  };

  // --- YENİ: Geçmişten Soru Seçme ---
  const loadHistoryItem = (item: HistoryItem) => {
    setSoru(item.soru);
    setSoruResponse(item.response);
    setActiveTab('soru'); // Soru sekmesine geç
    setIsSidebarOpen(false); // Menüyü kapat
  };

  // --- YENİ: Geçmişi Temizle ---
  const clearHistory = () => {
    if (window.confirm("Tüm geçmiş silinecek. Emin misiniz?")) {
      setHistory([]);
      localStorage.removeItem('chatHistory');
    }
  };

  // --- SORU SORMA ---
  const handleSoruSor = async () => {
    if (!soru.trim()) {
      setSoruError('Lütfen bir soru yazın!');
      return;
    }

    setSoruResponse(null);
    setSoruError('');
    setSoruLoading(true);

    try {
      const response = await axios.post<QueryResponse>(`${API_URL}/sor`, {
        soru: soru.trim(),
        top_k: 15
      });
      setSoruResponse(response.data);

      // --- YENİ: Başarılı olursa geçmişe kaydet ---
      saveToHistory(soru.trim(), response.data);

    } catch (error: any) {
      setSoruError(error.response?.data?.detail || 'Bağlantı hatası oluştu');
    } finally {
      setSoruLoading(false);
    }
  };

  // --- FOTOĞRAF ANALİZİ ---
  const handleFotoAnaliz = async () => {
    if (!fotoFile) {
      setFotoError('Lütfen bir fotoğraf seçin!');
      return;
    }
    setFotoLoading(true);
    setFotoError('');
    setFotoResponse(null);

    try {
      const formData = new FormData();
      formData.append('file', fotoFile);
      formData.append('soru', fotoSoru);

      const response = await axios.post<OCRResponse>(
        `${API_URL}/sor/fotograf`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      setFotoResponse(response.data);
    } catch (error: any) {
      setFotoError(error.response?.data?.detail || 'Fotoğraf analizi şu an aktif değil.');
    } finally {
      setFotoLoading(false);
    }
  };

  // --- PDF YÜKLEME ---
  const handlePdfYukle = async (e: React.MouseEvent) => {
    e.preventDefault();

    if (!pdfFile) {
      setPdfError('Lütfen bir PDF seçin!');
      return;
    }

    if (!pdfFile.name.endsWith('.pdf')) {
      setPdfError('Sadece PDF dosyaları yüklenebilir!');
      return;
    }

    setPdfLoading(true);
    setPdfError('');
    setPdfSuccess('');

    try {
      const formData = new FormData();
      formData.append('file', pdfFile);

      const response = await axios.post<UploadResponse>(
        `${API_URL}/yukle`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 300000
        }
      );

      setPdfSuccess(response.data.mesaj);
    } catch (error: any) {
      console.error(error);
      if (error.code === 'ECONNABORTED') {
        setPdfError('İşlem sunucuda devam ediyor olabilir ancak yanıt süresi doldu.');
      } else {
        setPdfError(error.response?.data?.detail || 'Sunucuyla bağlantı kurulurken hata oluştu');
      }
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 via-purple-700 to-indigo-800 p-4 md:p-8 relative">
      <ProactiveNotification />
      <ActionModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={modalTitle}
        type={modalType}
        data={modalData}
      />

      {/* --- YENİ: AI Notification Card --- */}
      {mockTask && (
        <div className="fixed bottom-6 right-6 bg-white rounded-xl shadow-2xl border-l-4 border-indigo-500 p-5 w-80 z-[100] transform transition-all duration-500 ease-out translate-y-0 opacity-100 flex flex-col gap-2">
          <div className="flex justify-between items-start mb-2">
            <h3 className="font-bold text-indigo-700 text-sm flex items-center gap-2 leading-tight">
              <span className="bg-indigo-100 text-indigo-800 p-1.5 rounded-full"><MessageSquare className="w-3.5 h-3.5" /></span>
              Yeni Etkinlik Bulundu: {mockTask.title}
            </h3>
            <button onClick={() => setMockTask(null)} className="text-gray-400 hover:text-red-500 transition-colors ml-2 shrink-0">
               <X className="w-5 h-5" />
            </button>
          </div>
          <div>
            <p className="text-xs text-gray-500 leading-relaxed">{mockTask.description} - {mockTask.date}</p>
          </div>
          <div className="flex space-x-2 mt-2">
            {!taskSuccessMessage ? (
              <>
                <button 
                  onClick={async () => {
                    setIsTaskActionLoading(true);
                    try {
                      await axios.post(`${API_URL}/api/execute-task`, {
                        task_id: mockTask.id,
                        action: "calendar_event",
                        task_title: mockTask.title
                      });
                      setTaskSuccessMessage('Takvime başarıyla eklendi!');
                      setTimeout(() => {
                        setMockTask(null);
                        setTaskSuccessMessage('');
                      }, 2000);
                    } catch (e) {
                      console.error("Task execute error:", e);
                    } finally {
                      setIsTaskActionLoading(false);
                    }
                  }} 
                  disabled={isTaskActionLoading}
                  className="flex-1 bg-blue-500 hover:bg-blue-600 text-white text-xs font-bold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-1 disabled:opacity-70"
                >
                  {isTaskActionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : '📅 Takvime Ekle'}
                </button>
                <button 
                  onClick={() => setMockTask(null)}
                  disabled={isTaskActionLoading}
                  className="flex-1 bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-bold py-2.5 px-4 rounded-lg transition-colors disabled:opacity-70"
                >
                  Yoksay
                </button>
              </>
            ) : (
              <div className="w-full bg-green-100 text-green-700 text-xs font-bold py-2.5 px-4 rounded-lg flex items-center justify-center gap-1">
                <CheckCircle className="w-4 h-4" />
                {taskSuccessMessage}
              </div>
            )}
          </div>
        </div>
      )}

      {/* --- YENİ: SIDEBAR (YAN MENÜ) --- */}
      {/* Overlay (Siyah Arkaplan) */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar Panel */}
      <div className={`fixed top-0 left-0 h-full w-80 bg-white shadow-2xl z-50 transform transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-5 border-b border-gray-200 flex justify-between items-center bg-purple-50">
          <h2 className="font-bold text-purple-700 flex items-center">
            <MessageSquare className="w-5 h-5 mr-2" /> Geçmiş Sohbetler
          </h2>
          <button onClick={() => setIsSidebarOpen(false)} className="text-gray-500 hover:text-red-500">
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="overflow-y-auto h-[calc(100%-130px)] p-4 space-y-3">
          {history.length === 0 ? (
            <p className="text-center text-gray-400 mt-10 text-sm">Henüz bir geçmiş yok.</p>
          ) : (
            history.map((item) => (
              <div
                key={item.id}
                onClick={() => loadHistoryItem(item)}
                className="p-3 bg-gray-50 border border-gray-100 rounded-lg cursor-pointer hover:bg-purple-50 hover:border-purple-200 transition-all group"
              >
                <p className="font-semibold text-gray-700 text-sm line-clamp-2 group-hover:text-purple-700">{item.soru}</p>
                <span className="text-xs text-gray-400 mt-1 block">{item.timestamp}</span>
              </div>
            ))
          )}
        </div>

        {history.length > 0 && (
          <div className="absolute bottom-0 w-full p-4 border-t border-gray-200 bg-white">
            <button
              onClick={clearHistory}
              className="w-full flex items-center justify-center text-red-500 hover:bg-red-50 p-2 rounded-lg transition-colors text-sm font-semibold"
            >
              <Trash2 className="w-4 h-4 mr-2" /> Geçmişi Temizle
            </button>
          </div>
        )}
      </div>

      <div className="max-w-5xl mx-auto bg-white rounded-2xl shadow-2xl overflow-hidden relative">

        {/* --- HEADER --- */}
        <div className="bg-gradient-to-r from-purple-600 to-indigo-700 text-white p-6 relative">

          {/* Hamburger Menu Butonu */}
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="absolute left-6 top-1/2 transform -translate-y-1/2 p-2 rounded-full hover:bg-white/20 transition-colors"
            title="Geçmişi Göster"
          >
            <Menu className="w-8 h-8 text-white" />
          </button>

          <div className="text-center">
            <h1 className="text-3xl md:text-4xl font-bold mb-2">TR-DocuQuery</h1>

          </div>
        </div>

        <div className="flex border-b border-gray-200">
          <button onClick={() => setActiveTab('soru')} className={`flex-1 py-4 px-6 text-center font-semibold transition-all ${activeTab === 'soru' ? 'text-purple-600 border-b-3 border-purple-600 bg-purple-50' : 'text-gray-600 hover:bg-gray-50'}`}>
            <FileText className="inline-block mr-2 w-5 h-5" /> Soru Sor
          </button>
          <button onClick={() => setActiveTab('fotograf')} className={`flex-1 py-4 px-6 text-center font-semibold transition-all ${activeTab === 'fotograf' ? 'text-purple-600 border-b-3 border-purple-600 bg-purple-50' : 'text-gray-600 hover:bg-gray-50'}`}>
            <Camera className="inline-block mr-2 w-5 h-5" /> Fotoğraf Analizi
          </button>
          <button onClick={() => setActiveTab('yukle')} className={`flex-1 py-4 px-6 text-center font-semibold transition-all ${activeTab === 'yukle' ? 'text-purple-600 border-b-3 border-purple-600 bg-purple-50' : 'text-gray-600 hover:bg-gray-50'}`}>
            <Upload className="inline-block mr-2 w-5 h-5" /> Belge Yükle
          </button>
        </div>

        <div className="p-8">
          {/* TAB 1: SORU */}
          {activeTab === 'soru' && (
            <div className="space-y-4">
              <div>
                <label className="block text-gray-700 font-semibold mb-2">Sorunuzu Yazın:</label>
                <textarea
                  value={soru}
                  onChange={(e) => setSoru(e.target.value)}
                  onKeyPress={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSoruSor(); } }}
                  placeholder="Örn: İzin hakları nelerdir?"
                  className="w-full border-2 border-gray-300 rounded-lg p-3 focus:border-purple-500 focus:outline-none min-h-[100px] resize-y"
                />
              </div>
              <button onClick={handleSoruSor} disabled={soruLoading} className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:from-purple-700 hover:to-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center">
                {soruLoading ? <><Loader2 className="animate-spin mr-2" /> Düşünülüyor...</> : <><Search className="mr-2" /> Cevapla</>}
              </button>
              {soruError && <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded"><p className="text-red-700"><XCircle className="inline mr-2" />{soruError}</p></div>}
              {soruResponse && (
                <div className="bg-purple-50 border-l-4 border-purple-500 p-6 rounded-lg animate-in fade-in duration-300">
                  <h3 className="text-purple-700 font-bold text-lg mb-3">💡 Cevap:</h3>
                  <p className="text-gray-800 mb-4 whitespace-pre-wrap">{soruResponse.cevap}</p>

                  {/* YENİ: MOCK AKSİYON BUTONLARI */}
                  <div className="flex space-x-2 mb-4">
                    <button
                      onClick={() => {
                        setModalTitle("Proje Teslimi");
                        setModalType('calendar');
                        setModalData({ baslik: "Proje Teslimi", tarih: "2024-06-15" });
                        setModalOpen(true);
                      }}
                      className="bg-blue-100 text-blue-700 font-semibold py-2 px-4 rounded-lg text-sm hover:bg-blue-200 transition-colors flex items-center"
                    >
                      📅 Takvime Ekle (Mock)
                    </button>
                    <button
                      onClick={() => {
                        setModalTitle("Şartname İncelemesi");
                        setModalType('tasks');
                        setModalData({ gorev: "Şartname İncelemesi", bitis_tarihi: "2024-06-15" });
                        setModalOpen(true);
                      }}
                      className="bg-green-100 text-green-700 font-semibold py-2 px-4 rounded-lg text-sm hover:bg-green-200 transition-colors flex items-center"
                    >
                      ✅ Görevlere Ekle (Mock)
                    </button>
                  </div>

                  {soruResponse.kaynaklar && soruResponse.kaynaklar.length > 0 && (
                    <div className="border-t border-purple-200 pt-4 mt-4">
                      <h4 className="font-semibold text-purple-700 mb-2">📚 Kaynaklar:</h4>
                      <div className="space-y-2">
                        {soruResponse.kaynaklar.map((kaynak, idx) => (
                          <div key={idx} className="bg-white p-3 rounded border border-purple-200">
                            <p className="text-sm text-gray-700">📄 <strong>{kaynak.source}</strong> (Sayfa: {kaynak.page}) - {kaynak.type}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: FOTOĞRAF */}
          {activeTab === 'fotograf' && (
            <div className="space-y-4">
              <div onClick={() => document.getElementById('foto-input')?.click()} className="border-2 border-dashed border-purple-400 rounded-lg p-8 text-center cursor-pointer hover:bg-purple-50">
                <Camera className="w-12 h-12 mx-auto text-purple-500 mb-2" />
                <p>Fotoğraf yüklemek için tıklayın</p>
                {fotoFile && <p className="text-purple-600 font-bold mt-2">✅ {fotoFile.name}</p>}
                <input id="foto-input" type="file" accept="image/*" onChange={(e) => setFotoFile(e.target.files?.[0] || null)} className="hidden" />
              </div>
              <input type="text" value={fotoSoru} onChange={(e) => setFotoSoru(e.target.value)} className="w-full border-2 border-gray-300 rounded-lg p-3" />
              <button onClick={handleFotoAnaliz} disabled={fotoLoading} className="w-full bg-indigo-600 text-white py-3 rounded-lg flex justify-center items-center">
                {fotoLoading ? <Loader2 className="animate-spin mr-2" /> : <Search className="mr-2" />} Analiz Et
              </button>
              {fotoResponse && <div className="bg-purple-50 p-6 rounded-lg mt-4"><p>{fotoResponse.cevap}</p></div>}
              {fotoError && <p className="text-red-500">{fotoError}</p>}
            </div>
          )}

          {/* TAB 3: PDF YUKLE */}
          {activeTab === 'yukle' && (
            <div className="space-y-4">
              <div onClick={() => document.getElementById('pdf-input')?.click()} className="border-2 border-dashed border-purple-400 rounded-lg p-8 text-center cursor-pointer hover:bg-purple-50">
                <FileText className="w-12 h-12 mx-auto text-purple-500 mb-2" />
                <p>PDF yüklemek için tıklayın</p>
                {pdfFile && <p className="text-purple-600 font-bold mt-2">✅ {pdfFile.name}</p>}
                <input id="pdf-input" type="file" accept=".pdf" onChange={(e) => setPdfFile(e.target.files?.[0] || null)} className="hidden" />
              </div>
              <button onClick={handlePdfYukle} disabled={pdfLoading} className="w-full bg-indigo-600 text-white py-3 rounded-lg flex justify-center items-center">
                {pdfLoading ? <><Loader2 className="animate-spin mr-2" /> İşleniyor...</> : <><Upload className="mr-2" /> Yükle ve İşle</>}
              </button>
              {pdfSuccess && <div className="bg-green-50 p-4 rounded text-green-700 flex items-center"><CheckCircle className="mr-2" />{pdfSuccess}</div>}
              {pdfError && <div className="bg-red-50 p-4 rounded text-red-700 flex items-center"><XCircle className="mr-2" />{pdfError}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;