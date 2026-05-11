import React, { useState, useEffect, useRef } from 'react';
import { Search, Upload, Camera, FileText, Loader2, CheckCircle, XCircle, Menu, X, MessageSquare, Trash2, StickyNote, Sparkles, Calendar as CalendarIcon, Send, Bot, User, Paperclip, Sun, Moon, ChevronLeft, ChevronRight, PlusCircle, Pin, Plus, Clock, ExternalLink, ChevronDown, ChevronUp, LogOut, Edit2, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { ActionModal } from './components/ActionModal';
import { ValidatorModal, ValidatorResponse } from './components/ValidatorModal';
import { AuditorReport, AuditorResponse } from './components/AuditorReport';
import { useGoogleLogin, googleLogout } from '@react-oauth/google';
import { jwtDecode } from "jwt-decode";

// --- MOCK DATA (backend'den gelene kadar) ---
const mockValidatorResponse: ValidatorResponse = {
  is_complete: false,
  document_type: 'Kira Sözleşmesi',
  confidence: 0.87,
  missing_fields: ['tarih', 'tc_no', 'iban', 'imza'],
};

const mockAuditorResponse: AuditorResponse = {
  risk_score: 8,
  executive_summary:
    'Sözleşme ciddi eksiklikler içermektedir. Yüksek risk skoru, kiracı aleyhine hükümler ve yasal standartların altında kalan maddeler nedeniyle oluşmuştur. İmzalanmadan önce hukuki danışmanlık alınması şiddetle önerilir.',
  timestamp: new Date().toISOString(),
  changes: [
    {
      type: 'risk',
      title: 'Tek Taraflı Fesih Maddesi',
      description: 'Madde 7.2, kiraya verenin herhangi bir gerekçe göstermeksizin 15 gün içinde sözleşmeyi feshedebileceğini belirtmektedir. Bu durum kiracı açısından yüksek risk oluşturmaktadır.',
      severity: 'high',
    },
    {
      type: 'degisiklik',
      title: 'Kira Artış Oranı Değiştirilmiş',
      description: 'Standart sözleşmedeki %25 kira artış sınırı kaldırılmış, yerine "piyasa koşullarına göre belirlenir" ifadesi eklenmiştir.',
      severity: 'high',
    },
    {
      type: 'silme',
      title: 'Depozito İade Maddesi Silinmiş',
      description: 'Orijinal taslakta yer alan 30 günlük depozito iade süresi kaldırılmış ve yerine herhangi bir süre sınırı konmamıştır.',
      severity: 'medium',
    },
    {
      type: 'ekleme',
      title: 'Yeni Bakım ve Onarım Yükümlülüğü',
      description: '10.000 TL altındaki tüm bakım ve onarım masraflarının kiracıya ait olduğu yeni bir madde eklenmiştir.',
      severity: 'medium',
    },
  ],
  missing_clauses: [
    'Zorunlu afet/deprem sigorta maddesi eksik',
    'Tahliye protokolü tanımlanmamış',
    'Anlaşmazlık çözüm mekanizması (arabuluculuk) belirtilmemiş',
    'Alt kiralama yasağı maddesi yok',
  ],
};

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

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  timestamp: string;
  pinned?: boolean;
}

interface ChatMessage {
  id: string;
  type: 'user' | 'bot';
  content: string;
  kaynaklar?: Source[];
  loading?: boolean;
  error?: string;
  buttonsType?: 'soru' | 'foto' | 'pdf';
  fileContext?: string;
}

interface Note {
  id: string;
  content: string;
  timestamp: string;
  title?: string;
  pinned?: boolean;
}

interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  source: string;
}

interface UserProfile {
  email: string;
  name: string;
  picture: string;
  access_token?: string;
}

function App() {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(() => {
    const saved = localStorage.getItem('userProfile');
    return saved ? JSON.parse(saved) : null;
  });

  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('isDarkMode');
    return saved !== null ? JSON.parse(saved) : true;
  });

  const [isLeftExpanded, setIsLeftExpanded] = useState(() => {
    const saved = localStorage.getItem('isLeftExpanded');
    return saved !== null ? JSON.parse(saved) : true;
  });

  const [isRightExpanded, setIsRightExpanded] = useState(() => {
    const saved = localStorage.getItem('isRightExpanded');
    return saved !== null ? JSON.parse(saved) : true;
  });

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);

  const [hasStartedChat, setHasStartedChat] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [history, setHistory] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const historyRef = useRef<ChatSession[]>([]);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  // Accordion State for Left Panel
  const [openAccordions, setOpenAccordions] = useState({ history: true, notes: false });

  const [notes, setNotes] = useState<Note[]>([]);
  const [newNote, setNewNote] = useState('');
  const [isNotesLoading, setIsNotesLoading] = useState(false);

  // Edit States
  const [editingHistoryId, setEditingHistoryId] = useState<string | null>(null);
  const [editingHistoryTitle, setEditingHistoryTitle] = useState('');
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingNoteContent, setEditingNoteContent] = useState('');

  // Calendar State for Right Panel
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [isCalendarLoading, setIsCalendarLoading] = useState(false);
  const [quickEventTitle, setQuickEventTitle] = useState('');
  const [quickEventDate, setQuickEventDate] = useState('');

  // Countdown State
  const [closestEvent, setClosestEvent] = useState<CalendarEvent | null>(null);
  const [countdownText, setCountdownText] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState('');
  const [modalType, setModalType] = useState<'calendar' | 'tasks' | 'notes'>('calendar');
  const [modalData, setModalData] = useState<any>({});

  const [proactiveFindings, setProactiveFindings] = useState<any[]>([]);
  const [asistanRaporu, setAsistanRaporu] = useState<any | null>(null);

  // --- AI Feature States ---
  const [validatorOpen, setValidatorOpen] = useState(false);
  const [auditorReportData, setAuditorReportData] = useState<AuditorResponse | null>(null);
  const [rightTab, setRightTab] = useState<'calendar' | 'validator' | 'auditor'>('calendar');

  const currentEmail = userProfile?.email || 'guest';
  const axiosInstance = axios.create({
    baseURL: API_URL,
    headers: {
      'X-User-Email': currentEmail,
      'x-google-token': userProfile?.access_token || ''
    }
  });

  // Sync theme
  useEffect(() => {
    localStorage.setItem('isDarkMode', JSON.stringify(isDarkMode));
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  useEffect(() => {
    localStorage.setItem('isLeftExpanded', JSON.stringify(isLeftExpanded));
  }, [isLeftExpanded]);

  useEffect(() => {
    localStorage.setItem('isRightExpanded', JSON.stringify(isRightExpanded));
  }, [isRightExpanded]);

  // Handle Login/Logout
  const handleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        // Access token ile kullanıcı profilini çek
        const userInfo = await axios.get('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${tokenResponse.access_token}` }
        });
        
        const profile = {
          email: userInfo.data.email,
          name: userInfo.data.name,
          picture: userInfo.data.picture,
          access_token: tokenResponse.access_token
        };
        
        setUserProfile(profile);
        localStorage.setItem('userProfile', JSON.stringify(profile));
        setShowLoginModal(false);

        // Akıllı Aktarım (Migrate Guest Data to the newly authenticated user)
        await axios.post(`${API_URL}/api/migrate-guest`, null, {
          headers: { 'X-User-Email': profile.email }
        });
        console.log("Guest data migrated successfully.");
      } catch (err) {
        console.error("Login / Migration hatası:", err);
      }
    },
    scope: 'https://www.googleapis.com/auth/calendar',
    onError: () => console.log('Login Failed')
  });

  const handleLogout = () => {
    googleLogout();
    setUserProfile(null);
    localStorage.removeItem('userProfile');
    setHistory([]);
    setNotes([]);
    setCalendarEvents([]);
    setHasStartedChat(false);
    setChatMessages([]);
  };

  // Initial Data Load (Loads for both guest and authenticated user)
  useEffect(() => {
    fetchHistory();
    fetchNotes();
    fetchCalendarEvents();

    const checkProactive = async () => {
      try {
        const response = await axiosInstance.get(`/api/agent/proactive-search`);
        if (response.data && response.data.bulunanlar && response.data.bulunanlar.length > 0) {
          setProactiveFindings(response.data.bulunanlar);
        }
      } catch (error) {}
    };
    
    checkProactive();
    const interval = setInterval(checkProactive, 60000);
    return () => clearInterval(interval);
  }, [userProfile]); // Runs when user changes (guest -> logged in, or logout)

  // Countdown Logic
  useEffect(() => {
    if (!closestEvent) {
      setCountdownText('');
      return;
    }

    const timer = setInterval(() => {
      const target = new Date(closestEvent.start).getTime();
      const now = new Date().getTime();
      const distance = target - now;

      if (distance < 0) {
        setCountdownText("Etkinlik başladı/geçti");
        clearInterval(timer);
        return;
      }

      const days = Math.floor(distance / (1000 * 60 * 60 * 24));
      const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((distance % (1000 * 60)) / 1000);

      setCountdownText(`${days}g : ${hours.toString().padStart(2, '0')}s : ${minutes.toString().padStart(2, '0')}dk : ${seconds.toString().padStart(2, '0')}sn`);
    }, 1000);

    return () => clearInterval(timer);
  }, [closestEvent]);

  // Update closest event when calendar updates
  useEffect(() => {
    if (calendarEvents.length > 0) {
      const now = new Date();
      const upcoming = calendarEvents
        .map(e => ({ ...e, dateObj: new Date(e.start) }))
        .filter(e => e.dateObj > now)
        .sort((a, b) => a.dateObj.getTime() - b.dateObj.getTime());
      
      if (upcoming.length > 0) {
        setClosestEvent(upcoming[0]);
      } else {
        setClosestEvent(null);
      }
    } else {
      setClosestEvent(null);
    }
  }, [calendarEvents]);


  useEffect(() => {
    if (asistanRaporu) {
      const timer = setTimeout(() => setAsistanRaporu(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [asistanRaporu]);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatMessages]);

  useEffect(() => {
    if (chatMessages.length > 0 && currentSessionId) {
      const prevHistory = historyRef.current;
      const sessionIndex = prevHistory.findIndex(h => h.id === currentSessionId);
      let updatedHistory = [...prevHistory];
      
      if (sessionIndex >= 0) {
        updatedHistory[sessionIndex] = {
          ...updatedHistory[sessionIndex],
          messages: chatMessages
        };
      } else {
        const firstUserMsg = chatMessages.find(m => m.type === 'user');
        const contentStr = firstUserMsg?.content ? String(firstUserMsg.content) : '';
        const contextStr = firstUserMsg?.fileContext ? String(firstUserMsg.fileContext) : '';
        const title = contentStr || contextStr || 'Yeni Sohbet';
        
        const newSession: ChatSession = {
          id: currentSessionId,
          title: title.substring(0, 40) + (title.length > 40 ? '...' : ''),
          messages: chatMessages,
          timestamp: new Date().toISOString()
        };
        updatedHistory = [newSession, ...updatedHistory];
      }
      
      setHistory(updatedHistory);
      axiosInstance.post(`/api/history`, updatedHistory).catch(() => {});
    }
  }, [chatMessages, currentSessionId]);

  const fetchHistory = async () => {
    try {
      const res = await axiosInstance.get(`/api/history`);
      if (Array.isArray(res.data)) {
        const migrated = res.data.map((item: any) => {
          if (item.soru && item.response) { // Migration format
            return {
              id: item.id,
              title: item.soru.substring(0, 40),
              timestamp: item.timestamp,
              messages: [
                { id: item.id + '_u', type: 'user', content: item.soru },
                { id: item.id + '_b', type: 'bot', content: item.response?.cevap || '', kaynaklar: item.response?.kaynaklar, buttonsType: 'soru' }
              ]
            } as ChatSession;
          }
          return item as ChatSession;
        });
        setHistory(migrated);
      }
    } catch (err) {
      console.error("Geçmiş çekilirken hata:", err);
    }
  };

  const fetchNotes = async () => {
    setIsNotesLoading(true);
    try {
      const res = await axiosInstance.get<Note[]>(`/api/notes`);
      setNotes(res.data);
    } catch (err) {
      console.error("Notları çekerken hata:", err);
    } finally {
      setIsNotesLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    if (!userProfile) {
      setShowLoginModal(true);
      return;
    }
    
    try {
      const res = await axiosInstance.post<Note>(`/api/notes`, { content: newNote.trim() });
      setNotes((prev) => [res.data, ...prev]);
      setNewNote('');
    } catch (err) {
      console.error("Not eklenirken hata:", err);
    }
  };

  const fetchCalendarEvents = async () => {
    setIsCalendarLoading(true);
    try {
      const res = await axiosInstance.get(`/api/calendar/events`);
      if (res.data && res.data.events) {
        setCalendarEvents(res.data.events);
      }
    } catch (err) {
      console.error("Takvim çekilirken hata:", err);
    } finally {
      setIsCalendarLoading(false);
    }
  };

  const handleQuickAddEvent = async () => {
    if (!quickEventTitle.trim()) return;
    if (!userProfile) {
      setShowLoginModal(true);
      return;
    }
    
    setIsCalendarLoading(true);
    try {
      await axiosInstance.post(`/api/action/calendar/add`, {
        task_id: "quick_add_" + Date.now(),
        action: "calendar_event",
        task_title: quickEventTitle,
        task_date: quickEventDate || null
      });
      setQuickEventTitle('');
      setQuickEventDate('');
      fetchCalendarEvents();
    } catch (err) {
      console.error("Takvime eklerken hata:", err);
    } finally {
      setIsCalendarLoading(false);
    }
  };

  const loadHistoryItem = (session: ChatSession) => {
    setHasStartedChat(true);
    setCurrentSessionId(session.id);
    setChatMessages(session.messages || []);
    setIsMobileMenuOpen(false);
  };

  const deleteHistoryItem = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = history.filter(h => h.id !== id);
    setHistory(updated);
    historyRef.current = updated;
    try {
      await axiosInstance.post(`/api/history`, updated);
    } catch (err) {}
    
    if (currentSessionId === id) {
      startNewChat();
    }
  };

  const handleUpdateHistoryItem = async (id: string, updates: Partial<ChatSession>, e?: React.MouseEvent) => {
    if(e) e.stopPropagation();
    const updated = history.map(h => h.id === id ? { ...h, ...updates } : h);
    setHistory(updated);
    historyRef.current = updated;
    try {
      await axiosInstance.post(`/api/history`, updated);
    } catch (err) {}
  };

  const handleDeleteNote = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await axiosInstance.delete(`/api/notes/${id}`);
      setNotes((prev) => prev.filter(n => n.id !== id));
    } catch (err) {
      console.error("Not silinirken hata:", err);
    }
  };

  const handleUpdateNote = async (id: string, updates: Partial<Note>, e?: React.MouseEvent) => {
    if(e) e.stopPropagation();
    try {
      await axiosInstance.put(`/api/notes/update/${id}`, updates);
      setNotes((prev) => prev.map(n => n.id === id ? { ...n, ...updates } : n));
    } catch (err) {
      console.error("Not güncellenirken hata:", err);
    }
  };

  const startNewChat = () => {
    setHasStartedChat(false);
    setChatMessages([]);
    setCurrentSessionId(null);
    setInputValue('');
    setAsistanRaporu(null);
    setIsMobileMenuOpen(false);
  };

  const handleSoruSor = async () => {
    if (selectedFile) {
      if (selectedFile.name.toLowerCase().endsWith('.pdf')) {
        handlePdfYukle(selectedFile);
      } else {
        handleFotoAnaliz(selectedFile);
      }
      setSelectedFile(null);
      return;
    }

    const text = inputValue.trim();
    if (!text) return;

    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = Date.now().toString();
      setCurrentSessionId(sessionId);
    }

    setHasStartedChat(true);
    setInputValue('');
    setAsistanRaporu(null);

    const userId = Date.now().toString();
    setChatMessages(prev => [...prev, { id: userId, type: 'user', content: text }]);

    const botId = (Date.now() + 1).toString();
    setChatMessages(prev => [...prev, { id: botId, type: 'bot', content: '', loading: true }]);

    // Fire & forget
    axios.post('http://10.114.10.152:8001/agent/proactive-search', { sohbet_gecmisi: [text] })
      .then(resp => {
        const sonuc = resp.data.arama_sonuclari || resp.data.rapor;
        if (sonuc) setAsistanRaporu(sonuc);
      }).catch(() => {});

    try {
      const response = await axiosInstance.post<QueryResponse>(`/sor`, {
        soru: text,
        top_k: 15
      });
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, content: response.data.cevap, kaynaklar: response.data.kaynaklar, buttonsType: 'soru' }
          : msg
      ));
    } catch (error: any) {
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, error: error.response?.data?.detail || 'Bağlantı hatası oluştu' }
          : msg
      ));
    }
  };

  const handleFotoAnaliz = async (file: File) => {
    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = Date.now().toString();
      setCurrentSessionId(sessionId);
    }
    setHasStartedChat(true);
    const userText = inputValue.trim();
    const backendText = userText || 'Bu belgede ne yazıyor?';
    setInputValue('');

    const userId = Date.now().toString();
    setChatMessages(prev => [...prev, { id: userId, type: 'user', content: userText, fileContext: `📷 ${file.name}` }]);

    const botId = (Date.now() + 1).toString();
    setChatMessages(prev => [...prev, { id: botId, type: 'bot', content: '', loading: true }]);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('soru', backendText);

      const response = await axiosInstance.post<OCRResponse>(
        `/sor/fotograf`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, content: response.data.cevap, buttonsType: 'foto' }
          : msg
      ));
    } catch (error: any) {
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, error: error.response?.data?.detail || 'Fotoğraf analizi şu an aktif değil.' }
          : msg
      ));
    }
  };

  const handlePdfYukle = async (file: File) => {
    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = Date.now().toString();
      setCurrentSessionId(sessionId);
    }
    setHasStartedChat(true);
    const userText = inputValue.trim();
    setInputValue('');
    
    const userId = Date.now().toString();
    setChatMessages(prev => [...prev, { id: userId, type: 'user', content: userText || 'Lütfen bu belgeyi sisteme yükle ve analiz et.', fileContext: `📄 ${file.name}` }]);

    const botId = (Date.now() + 1).toString();
    setChatMessages(prev => [...prev, { id: botId, type: 'bot', content: '', loading: true }]);

    if (!file.name.endsWith('.pdf')) {
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, error: 'Sadece PDF dosyaları yüklenebilir!' }
          : msg
      ));
      return;
    }

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await axiosInstance.post<UploadResponse>(
        `/yukle`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 300000
        }
      );
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, content: `✅ ${response.data.mesaj}`, buttonsType: 'pdf' }
          : msg
      ));
    } catch (error: any) {
      const errMsg = error.code === 'ECONNABORTED' 
        ? 'İşlem sunucuda devam ediyor olabilir ancak yanıt süresi doldu.' 
        : (error.response?.data?.detail || 'Sunucuyla bağlantı kurulurken hata oluştu');
      setChatMessages(prev => prev.map(msg =>
        msg.id === botId
          ? { ...msg, loading: false, error: errMsg }
          : msg
      ));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSoruSor();
    }
  };

  const isWarningColor = closestEvent && new Date(closestEvent.start).getTime() - new Date().getTime() < 1000 * 60 * 60 * 24; // Less than 1 day
  const countdownColorClass = isWarningColor 
    ? 'border-orange-500 shadow-orange-500/20' 
    : 'border-indigo-500/50 shadow-indigo-500/10';

  return (
    <div className="flex h-screen bg-white dark:bg-[#0f1115] text-slate-900 dark:text-slate-300 overflow-hidden font-sans selection:bg-indigo-500/30 transition-colors duration-300">
      
      {/* Login Prompt Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 p-8 rounded-3xl shadow-2xl max-w-sm w-full mx-4 text-center transform animate-in zoom-in-95 duration-200">
            <div className="w-16 h-16 mx-auto bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-full flex items-center justify-center mb-4">
              <User className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Giriş Yapmalısın</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Verilerini kalıcı olarak saklamak ve Google Takvimine erişmek için güvenli şekilde giriş yap.</p>
            <div className="flex justify-center mb-4">
              <button
                onClick={() => handleLogin()}
                className="bg-white dark:bg-[#252a36] border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-[#2a303d] text-slate-700 dark:text-slate-200 font-semibold py-2 px-6 rounded-full shadow-sm flex items-center gap-3 transition-colors"
              >
                <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-5 h-5" />
                Google ile Giriş Yap
              </button>
            </div>
            <button onClick={() => setShowLoginModal(false)} className="text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
              Şimdilik Atla
            </button>
          </div>
        </div>
      )}

      {/* Toast Notifications */}
      {asistanRaporu && (
        <div className="fixed top-6 right-6 z-[150] w-80 bg-white/95 dark:bg-[#1a1d24]/95 backdrop-blur-xl border border-slate-200 dark:border-slate-700/50 rounded-2xl shadow-2xl p-5 transform transition-all animate-in slide-in-from-right-8 ease-out duration-300">
          <div className="flex justify-between items-start mb-3 border-b border-slate-200 dark:border-slate-700/50 pb-2">
            <h3 className="font-bold flex items-center text-indigo-600 dark:text-indigo-400 text-sm">
              <Sparkles className="w-4 h-4 mr-2 animate-pulse" /> Ajan Raporu
            </h3>
            <button onClick={() => setAsistanRaporu(null)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="text-sm leading-relaxed mb-4 text-slate-600 dark:text-slate-300 flex flex-col gap-2">
            {typeof asistanRaporu === 'object' ? (
              Object.entries(asistanRaporu).map(([key, value]) => (
                <div key={key}>
                  <strong className="block text-indigo-600 dark:text-indigo-400/80">{key}:</strong>
                  <p>{String(value)}</p>
                </div>
              ))
            ) : (
              <p>{String(asistanRaporu)}</p>
            )}
          </div>
        </div>
      )}



      {/* ValidatorModal */}
      <ValidatorModal
        isOpen={validatorOpen}
        onClose={() => setValidatorOpen(false)}
        validatorData={mockValidatorResponse}
        onSubmit={async (fields) => {
          console.log('Validator form submitted:', fields);
          // TODO: POST to /api/validator/complete with fields
        }}
      />



      <ActionModal isOpen={modalOpen} onClose={() => { setModalOpen(false); fetchCalendarEvents(); }} title={modalTitle} type={modalType} data={modalData} />

      {/* Left Sidebar (Accordions) */}
      <div className={`fixed lg:static top-0 left-0 h-full bg-slate-50 dark:bg-[#12141a] border-r border-slate-200 dark:border-slate-800/50 z-50 transform transition-all duration-300 ease-in-out ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'} ${isLeftExpanded ? 'w-80' : 'w-20'} flex flex-col`}>
        
        {/* Header & Toggle */}
        <div className={`p-4 flex items-center border-b border-slate-200 dark:border-slate-800/50 h-[72px] transition-all duration-300 ${isLeftExpanded ? 'justify-between' : 'justify-center border-transparent'}`}>
          {isLeftExpanded && (
            <button 
              onClick={startNewChat}
              className="flex-1 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white rounded-xl py-2.5 px-4 flex items-center justify-center font-semibold text-sm shadow-md hover:shadow-lg transition-all animate-in fade-in group"
            >
              <PlusCircle className="w-5 h-5 mr-2 group-hover:rotate-90 transition-transform" /> Yeni Sohbet
            </button>
          )}
          
          <button onClick={() => setIsLeftExpanded(!isLeftExpanded)} className={`p-1.5 text-slate-400 hover:text-slate-800 dark:hover:text-white rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors ${isLeftExpanded ? 'ml-2' : ''}`}>
            {isLeftExpanded ? <ChevronLeft className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Accordion Container */}
        <div className={`flex-1 overflow-y-auto scrollbar-hide flex flex-col transition-all duration-300 ${!isLeftExpanded ? 'items-center justify-center gap-y-6 pb-20' : ''}`}>
          
          {!isLeftExpanded && (
            <div className="relative group">
              <button 
                onClick={startNewChat}
                className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-3 rounded-xl shadow-md hover:shadow-lg transition-all duration-300 flex items-center justify-center"
              >
                <PlusCircle className="w-5 h-5" />
              </button>
              <span className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-2 py-1 bg-slate-800 dark:bg-slate-700 text-white text-xs rounded opacity-0 translate-x-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 whitespace-nowrap z-50 pointer-events-none shadow-lg">Yeni Sohbet</span>
            </div>
          )}

          {/* History Accordion */}
          <div className={`${isLeftExpanded ? 'border-b border-slate-200 dark:border-slate-800/50 w-full' : 'relative group'} flex flex-col min-h-0 transition-all duration-300`}>
            <button 
              onClick={() => { if(isLeftExpanded) setOpenAccordions(p => ({ ...p, history: !p.history })); }}
              className={isLeftExpanded 
                ? "p-4 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-[#1a1d24] transition-colors w-full"
                : "p-3 rounded-xl bg-slate-100 dark:bg-[#1a1d24] hover:bg-slate-200 dark:hover:bg-slate-800/80 transition-all duration-300 text-slate-500 hover:text-indigo-500 shadow-sm flex items-center justify-center"
              }
            >
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-indigo-500" />
                {isLeftExpanded && <span className="font-semibold text-slate-700 dark:text-slate-300 text-sm whitespace-nowrap overflow-hidden">Geçmiş Sohbetler</span>}
              </div>
              {isLeftExpanded && (openAccordions.history ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />)}
            </button>
            {!isLeftExpanded && (
               <span className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-2 py-1 bg-slate-800 dark:bg-slate-700 text-white text-xs rounded opacity-0 translate-x-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 whitespace-nowrap z-50 pointer-events-none shadow-lg">Geçmiş Sohbetler</span>
            )}
            
            {isLeftExpanded && openAccordions.history && (
              <div className="p-2 space-y-1 max-h-64 overflow-y-auto scrollbar-hide animate-in slide-in-from-top-2">
                {history.length === 0 ? (
                  <p className="text-center text-slate-400 text-xs py-4">Henüz bir geçmiş yok.</p>
                ) : (
                  [...history].sort((a,b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)).map((item) => (
                    <div 
                      key={item.id} 
                      onClick={() => { if(editingHistoryId !== item.id) loadHistoryItem(item); }} 
                      className={`p-2.5 bg-white dark:bg-[#1a1d24] border ${item.pinned ? 'border-indigo-300 dark:border-indigo-500/50' : 'border-slate-200 dark:border-slate-800/50'} rounded-lg cursor-pointer hover:border-indigo-400 transition-all group flex flex-col gap-2`}
                    >
                      <div className="flex items-center justify-between">
                        {editingHistoryId === item.id ? (
                          <input
                            type="text"
                            value={editingHistoryTitle}
                            onChange={(e) => setEditingHistoryTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                handleUpdateHistoryItem(item.id, { title: editingHistoryTitle });
                                setEditingHistoryId(null);
                              }
                            }}
                            onBlur={() => {
                               handleUpdateHistoryItem(item.id, { title: editingHistoryTitle });
                               setEditingHistoryId(null);
                            }}
                            autoFocus
                            className="flex-1 bg-slate-50 dark:bg-[#12141a] text-sm text-slate-800 dark:text-slate-200 px-2 py-1 rounded outline-none border border-indigo-400"
                            onClick={(e) => e.stopPropagation()}
                          />
                        ) : (
                          <p className="text-sm text-slate-700 dark:text-slate-300 truncate flex-1 mr-2">{item.title}</p>
                        )}
                        
                        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity gap-1" onClick={(e) => e.stopPropagation()}>
                          <button onClick={() => { setEditingHistoryId(item.id); setEditingHistoryTitle(item.title); }} className="p-1 text-slate-400 hover:text-indigo-500 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => handleUpdateHistoryItem(item.id, { pinned: !item.pinned })} className={`p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 ${item.pinned ? 'text-indigo-500' : 'text-slate-400 hover:text-indigo-500'}`}>
                            <Pin className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={(e) => deleteHistoryItem(item.id, e)} className="p-1 text-slate-400 hover:text-red-500 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Notes Accordion */}
          <div className={`${isLeftExpanded ? 'border-b border-slate-200 dark:border-slate-800/50 w-full' : 'relative group'} flex flex-col min-h-0 transition-all duration-300`}>
            <button 
              onClick={() => { if(isLeftExpanded) setOpenAccordions(p => ({ ...p, notes: !p.notes })); }}
              className={isLeftExpanded 
                ? "p-4 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-[#1a1d24] transition-colors w-full"
                : "p-3 rounded-xl bg-slate-100 dark:bg-[#1a1d24] hover:bg-slate-200 dark:hover:bg-slate-800/80 transition-all duration-300 text-slate-500 hover:text-purple-500 shadow-sm flex items-center justify-center"
              }
            >
              <div className="flex items-center gap-2">
                <StickyNote className="w-5 h-5 text-purple-500" />
                {isLeftExpanded && <span className="font-semibold text-slate-700 dark:text-slate-300 text-sm whitespace-nowrap overflow-hidden">Notlarım</span>}
              </div>
              {isLeftExpanded && (openAccordions.notes ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />)}
            </button>
            {!isLeftExpanded && (
               <span className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-2 py-1 bg-slate-800 dark:bg-slate-700 text-white text-xs rounded opacity-0 translate-x-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 whitespace-nowrap z-50 pointer-events-none shadow-lg">Notlarım</span>
            )}
            
            {isLeftExpanded && openAccordions.notes && (
              <div className="p-3 bg-slate-50 dark:bg-[#12141a] flex flex-col gap-3 animate-in slide-in-from-top-2">
                <div className="flex items-center bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-700 rounded-lg p-1 shadow-sm focus-within:ring-1 focus-within:ring-purple-500">
                  <input 
                    type="text" 
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
                    placeholder="Hızlı not ekle..."
                    className="flex-1 bg-transparent text-sm text-slate-800 dark:text-slate-200 px-2 py-1 outline-none"
                  />
                  <button onClick={handleAddNote} disabled={!newNote.trim()} className="p-1.5 bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-md hover:bg-purple-100 disabled:opacity-50">
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto scrollbar-hide">
                  {isNotesLoading ? (
                    <div className="flex justify-center p-2"><Loader2 className="w-4 h-4 animate-spin text-purple-400" /></div>
                  ) : notes.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center py-2">Henüz not yok.</p>
                  ) : (
                    [...notes].sort((a,b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)).map((n) => (
                      <div key={n.id} className={`bg-white dark:bg-[#1a1d24] p-3 rounded-lg border ${n.pinned ? 'border-purple-300 dark:border-purple-500/50' : 'border-slate-200 dark:border-slate-800/80'} shadow-sm text-xs text-slate-700 dark:text-slate-300 flex flex-col gap-2 group`}>
                        {editingNoteId === n.id ? (
                          <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="text"
                              value={editingNoteContent}
                              onChange={(e) => setEditingNoteContent(e.target.value)}
                              className="bg-slate-50 dark:bg-[#12141a] text-slate-800 dark:text-slate-200 px-2 py-1 rounded outline-none border border-purple-400 w-full"
                              autoFocus
                            />
                            <div className="flex justify-end gap-2">
                              <button onClick={() => setEditingNoteId(null)} className="text-slate-400 hover:text-slate-600 text-[10px]">İptal</button>
                              <button onClick={() => { handleUpdateNote(n.id, { content: editingNoteContent }); setEditingNoteId(null); }} className="text-purple-600 hover:text-purple-800 font-bold text-[10px]">Kaydet</button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex flex-col gap-1">
                            {n.title && <span className="font-bold">{n.title}</span>}
                            <span className="whitespace-pre-wrap leading-relaxed cursor-pointer" onClick={() => { setEditingNoteId(n.id); setEditingNoteContent(n.content); }}>
                              {n.content}
                            </span>
                          </div>
                        )}
                        <div className="flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity gap-1">
                          <button onClick={() => { setEditingNoteId(n.id); setEditingNoteContent(n.content); }} className="p-1 text-slate-400 hover:text-purple-500 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => handleUpdateNote(n.id, { pinned: !n.pinned })} className={`p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 ${n.pinned ? 'text-purple-500' : 'text-slate-400 hover:text-purple-500'}`}>
                            <Pin className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={(e) => handleDeleteNote(n.id, e)} className="p-1 text-slate-400 hover:text-red-500 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative h-full">
        {/* Header */}
        <header className="p-4 flex justify-between items-center z-10 bg-transparent h-[72px]">
          <div className="flex items-center">
            <button onClick={() => setIsMobileMenuOpen(true)} className="lg:hidden p-2 -ml-2 mr-2 text-slate-400 hover:text-slate-800 dark:hover:text-white rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors">
              <Menu className="w-6 h-6" />
            </button>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-wide flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
                <Search className="w-4 h-4 text-white" />
              </div>
              TR-DocuQuery
            </h1>
          </div>
          <div className="flex items-center gap-4">
            
            {/* User Profile Area or Guest Login Button */}
            {userProfile ? (
              <div className="flex items-center gap-3 bg-white dark:bg-[#1a1d24] pl-2 pr-4 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 shadow-sm animate-in fade-in">
                <img src={userProfile.picture} alt="Profile" className="w-8 h-8 rounded-full shadow-sm" />
                <div className="flex flex-col hidden sm:flex">
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-200 leading-tight">{userProfile.name}</span>
                  <span className="text-[10px] text-slate-500">{userProfile.email}</span>
                </div>
                <button onClick={handleLogout} className="ml-2 p-1.5 text-slate-400 hover:text-red-500 bg-slate-50 dark:bg-[#12141a] rounded-full transition-colors" title="Çıkış Yap">
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="animate-in fade-in">
                <button
                  onClick={() => handleLogin()}
                  className="bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-[#252a36] text-slate-700 dark:text-slate-200 font-semibold py-1.5 px-4 rounded-full shadow-sm flex items-center gap-2 transition-colors text-sm"
                >
                  <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="w-4 h-4" />
                  Giriş Yap
                </button>
              </div>
            )}

            <button 
              onClick={() => setIsDarkMode(!isDarkMode)} 
              className="p-2.5 rounded-full bg-slate-100 dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-all shadow-sm"
              title={isDarkMode ? "Açık Tema" : "Koyu Tema"}
            >
              {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
          </div>
        </header>

        {/* Scrollable Chat Area */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 lg:px-16 pb-40 scrollbar-hide" ref={chatScrollRef}>
          {!hasStartedChat ? (
            <div className="flex flex-col items-center justify-center min-h-[70vh] animate-in fade-in slide-in-from-bottom-8 duration-700">
              <div className="w-16 h-16 bg-white dark:bg-gradient-to-br dark:from-slate-800 dark:to-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl flex items-center justify-center mb-8 shadow-xl">
                <Sparkles className="w-8 h-8 text-indigo-500 dark:text-indigo-400" />
              </div>
              <h2 className="text-3xl md:text-4xl font-semibold text-slate-900 dark:text-white mb-3 tracking-tight text-center">
                Hoş Geldin{userProfile ? `, ${userProfile.name.split(' ')[0]}` : ''}
              </h2>
              <p className="text-slate-500 dark:text-slate-400 mb-10">Nereden başlamak istersin?</p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-4xl">
                <button onClick={() => fileInputRef.current?.click()} className="bg-slate-100 dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 hover:border-indigo-400 dark:hover:border-slate-600 rounded-2xl p-6 flex flex-col items-center justify-center gap-4 transition-all hover:bg-slate-50 dark:hover:bg-[#20242c] shadow-sm hover:shadow-md dark:shadow-none group">
                  <div className="p-4 bg-white dark:bg-[#252a36] rounded-2xl group-hover:scale-110 group-hover:bg-indigo-50 transition-all border border-slate-100 dark:border-none shadow-sm">
                    <Camera className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
                  </div>
                  <span className="font-medium text-lg text-slate-900 dark:text-slate-200">Fotoğraf Analizi</span>
                </button>
                <button onClick={() => pdfInputRef.current?.click()} className="bg-slate-100 dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 hover:border-emerald-400 dark:hover:border-slate-600 rounded-2xl p-6 flex flex-col items-center justify-center gap-4 transition-all hover:bg-slate-50 dark:hover:bg-[#20242c] shadow-sm hover:shadow-md dark:shadow-none group">
                  <div className="p-4 bg-white dark:bg-[#252a36] rounded-2xl group-hover:scale-110 group-hover:bg-emerald-50 transition-all border border-slate-100 dark:border-none shadow-sm">
                    <FileText className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <span className="font-medium text-lg text-slate-900 dark:text-slate-200">Belge Sorgulama</span>
                </button>
                <button onClick={() => inputRef.current?.focus()} className="bg-slate-100 dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 hover:border-purple-400 dark:hover:border-slate-600 rounded-2xl p-6 flex flex-col items-center justify-center gap-4 transition-all hover:bg-slate-50 dark:hover:bg-[#20242c] shadow-sm hover:shadow-md dark:shadow-none group">
                  <div className="p-4 bg-white dark:bg-[#252a36] rounded-2xl group-hover:scale-110 group-hover:bg-purple-50 transition-all border border-slate-100 dark:border-none shadow-sm">
                    <MessageSquare className="w-8 h-8 text-purple-600 dark:text-purple-400" />
                  </div>
                  <span className="font-medium text-lg text-slate-900 dark:text-slate-200">Soru Sor</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto py-8 space-y-8">
              {/* Auditor Report (shown when demo is triggered) */}
              {auditorReportData && (
                <AuditorReport data={auditorReportData} />
              )}
              {chatMessages.map((msg) => (
                <div key={msg.id} className={`flex gap-4 ${msg.type === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
                  
                  {msg.type === 'bot' && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 mt-1 shadow-md">
                      <Bot className="w-5 h-5 text-white" />
                    </div>
                  )}

                  <div className={`max-w-[80%] ${msg.type === 'user' ? 'order-1' : 'order-2'}`}>
                    {msg.type === 'user' && msg.fileContext && (
                      <div className="mb-2 px-3 py-1.5 bg-slate-100 dark:bg-[#252a36] rounded-lg text-xs font-medium inline-block border border-slate-200 dark:border-slate-700/50">
                        {msg.fileContext}
                      </div>
                    )}
                    <div className={`p-4 rounded-2xl shadow-sm ${msg.type === 'user' ? 'bg-slate-100 dark:bg-[#252a36] border border-slate-200 dark:border-slate-800/50 rounded-tr-sm' : 'bg-white dark:bg-transparent border border-slate-200 dark:border-slate-800/50 rounded-tl-sm'}`}>
                      {msg.loading ? (
                        <div className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Analiz ediliyor...</div>
                      ) : msg.error ? (
                        <div className="text-red-500 flex items-start gap-2"><XCircle className="w-5 h-5" /><p>{msg.error}</p></div>
                      ) : (
                        <div className="whitespace-pre-wrap leading-relaxed text-[15px]">{msg.content}</div>
                      )}
                    </div>
                  </div>

                  {msg.type === 'user' && (
                    <img src={userProfile?.picture || `https://ui-avatars.com/api/?name=Guest&background=random`} alt="User" className="w-8 h-8 rounded-full border border-slate-300 dark:border-slate-700 mt-1 order-2 shadow-sm" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white dark:from-[#0f1115] dark:via-[#0f1115] to-transparent pt-10 pb-6 px-4">
          <div className="max-w-4xl mx-auto relative flex flex-col gap-2">
            
            {/* Selected File Thumbnail Preview */}
            {selectedFile && (
              <div className="flex items-center gap-3 bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-700 w-fit p-2 rounded-xl shadow-sm animate-in fade-in slide-in-from-bottom-2">
                {selectedFile.type.startsWith('image/') ? (
                  <img src={URL.createObjectURL(selectedFile)} alt="preview" className="w-12 h-12 object-cover rounded-md border border-slate-200 dark:border-slate-700" />
                ) : (
                  <div className="w-12 h-12 flex items-center justify-center bg-slate-100 dark:bg-[#252a36] rounded-md border border-slate-200 dark:border-slate-700">
                    <FileText className="w-6 h-6 text-emerald-500" />
                  </div>
                )}
                <div className="flex flex-col max-w-[200px]">
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">{selectedFile.name}</span>
                  <span className="text-[10px] text-slate-500">{(selectedFile.size / 1024).toFixed(1)} KB</span>
                </div>
                <button 
                  onClick={() => setSelectedFile(null)}
                  className="ml-2 p-1.5 text-slate-400 hover:text-red-500 bg-slate-50 dark:bg-[#252a36] rounded-full transition-colors border border-slate-200 dark:border-slate-700"
                  title="Dosyayı Kaldır"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <div className="bg-slate-50 dark:bg-[#1a1d24] border border-slate-300 dark:border-slate-700 rounded-2xl p-1.5 flex items-end shadow-lg focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 transition-all">
              <div className="flex gap-1 p-2">
                <button onClick={() => pdfInputRef.current?.click()} className="p-2 text-slate-500 hover:text-slate-800 dark:hover:text-white rounded-xl hover:bg-slate-200 transition-colors"><Paperclip className="w-5 h-5" /></button>
                <button onClick={() => fileInputRef.current?.click()} className="p-2 text-slate-500 hover:text-slate-800 dark:hover:text-white rounded-xl hover:bg-slate-200 transition-colors"><Camera className="w-5 h-5" /></button>
              </div>
              <textarea 
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Bir şeyler sorun veya dosya yükleyin..."
                className="flex-1 bg-transparent border-none focus:outline-none resize-none text-slate-900 dark:text-white p-3 max-h-32 min-h-[48px] text-[15px]"
                rows={1}
                style={{ height: 'auto' }}
                onInput={(e) => {
                  const t = e.target as HTMLTextAreaElement;
                  t.style.height = 'auto';
                  t.style.height = `${Math.min(t.scrollHeight, 128)}px`;
                }}
              />
              <button 
                onClick={handleSoruSor}
                disabled={!inputValue.trim() && !selectedFile}
                className={`p-3 rounded-xl transition-all m-1 flex items-center justify-center ${inputValue.trim() || selectedFile ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md hover:shadow-lg' : 'bg-slate-200 dark:bg-[#252a36] text-slate-400 cursor-not-allowed'}`}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* File Inputs */}
        <input ref={fileInputRef} type="file" accept="image/*" onChange={(e) => { if(e.target.files?.[0]) { setSelectedFile(e.target.files[0]); if(inputRef.current) inputRef.current.focus(); } }} className="hidden" />
        <input ref={pdfInputRef} type="file" accept=".pdf" onChange={(e) => { if(e.target.files?.[0]) { setSelectedFile(e.target.files[0]); if(inputRef.current) inputRef.current.focus(); } }} className="hidden" />
      </div>

      {/* Right Sidebar — Tabbed */}
      <div className={`hidden xl:flex flex-col bg-slate-50/80 dark:bg-[#12141a]/80 backdrop-blur-xl border-l border-slate-200 dark:border-slate-800/50 z-20 transition-all duration-300 ease-in-out ${isRightExpanded ? 'w-[350px]' : 'w-20'}`}>

        {/* Header */}
        {isRightExpanded ? (
          /* ── EXPANDED: tab buttons + collapse arrow ── */
          <div className="h-[72px] flex items-center px-3 gap-1 border-b border-slate-200 dark:border-slate-800/50">
            {([
              { key: 'calendar',  icon: <CalendarIcon className="w-4 h-4" />, label: 'Takvim' },
              { key: 'validator', icon: <AlertTriangle className="w-4 h-4" />, label: 'Eksik Bilgi' },
              { key: 'auditor',   icon: <FileText className="w-4 h-4" />,      label: 'Sözleşme' },
            ] as const).map(({ key, icon, label }) => (
              <button
                key={key}
                onClick={() => setRightTab(key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-all duration-200 ${
                  rightTab === key
                    ? 'bg-white dark:bg-[#1a1d24] text-indigo-600 dark:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-700'
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-white/50 dark:hover:bg-white/5'
                }`}
              >
                {icon}{label}
              </button>
            ))}
            {/* Collapse arrow */}
            <button
              onClick={() => setIsRightExpanded(false)}
              className="ml-1 p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-white rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
              title="Paneli Kapat"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        ) : (
          /* ── COLLAPSED: expand arrow at top, icons centered ── */
          <div className="flex flex-col items-center h-full">
            {/* Expand arrow — pinned to top */}
            <button
              onClick={() => setIsRightExpanded(true)}
              className="w-12 h-[72px] flex items-center justify-center text-slate-400 hover:text-indigo-500 hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-all duration-200 border-b border-slate-200 dark:border-slate-800/50 flex-shrink-0"
              title="Paneli Aç"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            {/* Tab icons — centered in remaining space */}
            <div className="flex-1 flex flex-col items-center justify-center gap-4">
              {([
                { key: 'calendar',  icon: <CalendarIcon className="w-5 h-5" />,   label: 'Takvim',      color: 'text-emerald-500' },
                { key: 'validator', icon: <AlertTriangle className="w-5 h-5" />,  label: 'Eksik Bilgi', color: 'text-purple-500'  },
                { key: 'auditor',   icon: <FileText className="w-5 h-5" />,        label: 'Sözleşme',   color: 'text-indigo-500'  },
              ] as const).map(({ key, icon, label, color }) => (
                <div key={key} className="relative group">
                  <button
                    onClick={() => { setRightTab(key); setIsRightExpanded(true); }}
                    className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-200 shadow-sm ${
                      rightTab === key
                        ? 'bg-white dark:bg-[#1a1d24] ring-1 ring-slate-300 dark:ring-slate-700'
                        : 'bg-slate-100 dark:bg-[#1a1d24] hover:bg-slate-200 dark:hover:bg-slate-800/80'
                    } ${color}`}
                  >
                    {icon}
                  </button>
                  <span className="absolute right-full top-1/2 -translate-y-1/2 mr-3 px-2 py-1 bg-slate-800 dark:bg-slate-700 text-white text-xs rounded opacity-0 group-hover:opacity-100 group-hover:-translate-x-1 transition-all duration-200 whitespace-nowrap z-50 pointer-events-none shadow-lg">
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto scrollbar-hide p-4 flex flex-col gap-6">

          {/* ── TAB: CALENDAR (original code — untouched) ── */}
          {(rightTab === 'calendar' || !isRightExpanded) && isRightExpanded && (
            <>
              {/* Google Takvim'i Aç */}
              <a
                href="https://calendar.google.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-700 hover:border-emerald-400 dark:hover:border-emerald-500/50 text-slate-700 dark:text-slate-200 py-2 px-3 rounded-lg flex items-center justify-center gap-2 text-xs font-bold transition-all shadow-sm group animate-in slide-in-from-right-4"
              >
                <CalendarIcon className="w-4 h-4 text-emerald-500" />
                Google Takvim'i Aç
                <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-emerald-500 transition-colors ml-1" />
              </a>

              {/* Hızlı Ekle Formu */}
              <div className="bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm animate-in slide-in-from-right-4">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                  <PlusCircle className="w-4 h-4 text-emerald-500" /> Hızlı Etkinlik Ekle
                </h3>
                <div className="flex flex-col gap-3">
                  <input
                    type="text"
                    placeholder="Etkinlik Başlığı"
                    value={quickEventTitle}
                    onChange={(e) => setQuickEventTitle(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-[#12141a] text-slate-800 dark:text-slate-200 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                  <input
                    type="date"
                    value={quickEventDate}
                    onChange={(e) => setQuickEventDate(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-[#12141a] text-slate-800 dark:text-slate-200 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                  <button
                    onClick={handleQuickAddEvent}
                    disabled={!quickEventTitle.trim() || isCalendarLoading}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm py-2 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center"
                  >
                    {isCalendarLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Kaydet ve Senkronize Et'}
                  </button>
                </div>
              </div>

              {/* Yaklaşan Etkinlikler Listesi */}
              <div>
                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <CalendarIcon className="w-4 h-4 text-slate-400" /> Senkronize Takvim
                </h3>
                <div className="space-y-2">
                  {isCalendarLoading && calendarEvents.length === 0 ? (
                    <div className="flex justify-center p-4"><Loader2 className="w-5 h-5 animate-spin text-emerald-400" /></div>
                  ) : calendarEvents.length === 0 ? (
                    <div className="text-center bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 rounded-xl p-6">
                      <CalendarIcon className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
                      <p className="text-sm text-slate-500">Yaklaşan etkinlik yok.</p>
                    </div>
                  ) : (
                    calendarEvents.map((ev, idx) => {
                      const d = new Date(ev.start);
                      const isPast = d < new Date();
                      return (
                        <div key={idx} className={`p-3 bg-white dark:bg-[#1a1d24] border ${isPast ? 'border-slate-200 dark:border-slate-800 opacity-60' : 'border-emerald-200 dark:border-emerald-500/30'} rounded-xl shadow-sm flex flex-col gap-1`}>
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-slate-800 dark:text-slate-200 line-clamp-1">{ev.title}</span>
                            {ev.source === 'google' && <span className="text-[9px] bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded uppercase font-bold">Google</span>}
                          </div>
                          <span className="text-xs text-slate-500">
                            {d.toLocaleString('tr-TR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </>
          )}

          {/* ── TAB: VALIDATOR ── */}
          {rightTab === 'validator' && isRightExpanded && (
            <div className="flex flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-8 h-8 bg-purple-100 dark:bg-purple-500/20 rounded-lg flex items-center justify-center">
                  <Search className="w-4 h-4 text-purple-500" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">Eksik Bilgi Analizi</h2>
                  <p className="text-[11px] text-slate-500">Belgede eksik alanları tamamla</p>
                </div>
              </div>
              {!mockValidatorResponse.is_complete ? (
                <div className="flex flex-col gap-3">
                  {mockValidatorResponse.missing_fields.map((field) => {
                    const labels: Record<string, string> = { tarih: 'Tarih', tc_no: 'TC Kimlik No', iban: 'IBAN', imza: 'İmza', ad_soyad: 'Ad Soyad', telefon: 'Telefon', tutar: 'Tutar (₺)' };
                    const types: Record<string, string> = { tarih: 'date', tc_no: 'text', iban: 'text', telefon: 'tel', tutar: 'number' };
                    return (
                      <div key={field} className="flex flex-col gap-1.5">
                        <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{labels[field] ?? field}</label>
                        <input
                          type={types[field] ?? 'text'}
                          placeholder={`${labels[field] ?? field} giriniz...`}
                          className="w-full bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-700 focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-slate-200 outline-none transition-all"
                        />
                      </div>
                    );
                  })}
                  <button className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold transition-colors mt-1">
                    Bilgileri Tamamla
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 py-8">
                  <CheckCircle className="w-10 h-10 text-emerald-500" />
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Belge eksiksiz!</p>
                </div>
              )}
            </div>
          )}

          {/* ── TAB: AUDITOR ── */}
          {rightTab === 'auditor' && isRightExpanded && (
            <div className="flex flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-8 h-8 bg-indigo-100 dark:bg-indigo-500/20 rounded-lg flex items-center justify-center">
                  <FileText className="w-4 h-4 text-indigo-500" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">Sözleşme Denetçisi</h2>
                  <p className="text-[11px] text-slate-500">Risk analizi ve eksik maddeler</p>
                </div>
              </div>
              <AuditorReport data={mockAuditorResponse} />
            </div>
          )}
        </div>

        {/* Countdown strip — only calendar tab or mini-bar */}
        {closestEvent && (
          <div className="border-t border-slate-200 dark:border-slate-800/50 bg-slate-50/80 dark:bg-[#12141a]/80 backdrop-blur-md p-4 flex flex-col items-center justify-center transition-all duration-300 w-full z-10 shrink-0">
            {isRightExpanded ? (
              <div className="w-full flex flex-col gap-1.5 animate-in fade-in duration-300">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">{closestEvent.title}</span>
                </div>
                <div className="text-[13px] font-mono font-bold text-slate-700 dark:text-slate-300 bg-white dark:bg-[#1a1d24] border border-slate-200 dark:border-slate-800 py-1.5 px-2 rounded-lg text-center w-full">
                  {countdownText || "Hesaplanıyor..."}
                </div>
              </div>
            ) : (
              <div className="relative group w-full flex justify-center animate-in fade-in duration-300">
                <div className="p-2 bg-white dark:bg-[#1a1d24] border border-emerald-200 dark:border-emerald-500/30 rounded-xl flex items-center justify-center text-emerald-500">
                  <Clock className="w-5 h-5 animate-pulse" />
                </div>
                <div className="absolute right-full top-1/2 -translate-y-1/2 mr-4 px-2 py-1.5 bg-slate-800 dark:bg-slate-700 text-white text-xs rounded opacity-0 translate-x-0 group-hover:opacity-100 group-hover:-translate-x-1 transition-all duration-300 whitespace-nowrap z-50 pointer-events-none shadow-lg flex flex-col gap-1">
                  <span className="font-bold text-[10px] text-emerald-400 uppercase">{closestEvent.title}</span>
                  <span>{countdownText || "Hesaplanıyor..."}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
