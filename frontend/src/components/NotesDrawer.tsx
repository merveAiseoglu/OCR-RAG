import React, { useState, useEffect, useRef } from 'react';
import { X, Trash2, Loader2, Plus, StickyNote, Edit2 } from 'lucide-react';
import axios from 'axios';

const API_URL = 'http://localhost:8000';

interface Note {
  id: string;
  content: string;
  timestamp: string;
}

interface NotesDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const NotesDrawer: React.FC<NotesDrawerProps> = ({ isOpen, onClose }) => {
  const [notes, setNotes] = useState<Note[]>([]);
  const [newNote, setNewNote] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Editing state
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  const fetchNotes = async () => {
    setIsLoading(true);
    try {
      const res = await axios.get<Note[]>(`${API_URL}/api/notes`);
      setNotes(res.data);
    } catch (err) {
      console.error("Notları çekerken hata:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchNotes();
      // Reset edit state when opened
      setEditingNoteId(null);
      setEditingContent('');
    }
  }, [isOpen]);

  // Focus textarea when editing starts
  useEffect(() => {
    if (editingNoteId && editTextareaRef.current) {
      editTextareaRef.current.focus();
    }
  }, [editingNoteId]);

  const handleAddNote = async () => {
    if (!newNote.trim()) {
      setError('Lütfen boş bir not girmeyin.');
      return;
    }
    setError('');
    setIsSubmitting(true);
    try {
      const res = await axios.post<Note>(`${API_URL}/api/notes`, { content: newNote.trim() });
      setNotes((prev) => [...prev, res.data]);
      setNewNote('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Not eklenirken bir hata oluştu.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteNote = async (id: string) => {
    try {
      // Optimistic delete
      setNotes((prev) => prev.filter(note => note.id !== id));
      await axios.delete(`${API_URL}/api/notes/${id}`);
    } catch (err) {
      console.error("Not silinirken hata:", err);
      // Revert on error
      fetchNotes();
    }
  };

  const handleStartEdit = (note: Note) => {
    setEditingNoteId(note.id);
    setEditingContent(note.content);
  };

  const handleCancelEdit = () => {
    setEditingNoteId(null);
    setEditingContent('');
  };

  const handleUpdateNote = async (id: string) => {
    if (!editingContent.trim()) {
      setError('Not içeriği boş olamaz.');
      return;
    }
    setIsUpdating(true);
    try {
      await axios.put(`${API_URL}/api/notes/update/${id}`, { content: editingContent.trim() });
      setNotes((prev) => 
        prev.map(n => n.id === id ? { ...n, content: editingContent.trim() } : n)
      );
      setEditingNoteId(null);
      setEditingContent('');
    } catch (err: any) {
      console.error("Not güncellenirken hata:", err);
      setError(err.response?.data?.detail || 'Not güncellenirken bir hata oluştu.');
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-40 z-40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Drawer Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-80 sm:w-96 bg-gray-50 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
      >
        <div className="p-5 border-b border-gray-200 flex justify-between items-center bg-white shadow-sm">
          <h2 className="font-bold text-gray-800 flex items-center text-lg">
            <StickyNote className="w-5 h-5 mr-2 text-yellow-500" /> Notlarım
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-red-500 transition-colors">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
            </div>
          ) : notes.length === 0 ? (
            <div className="text-center text-gray-400 mt-10">
              <StickyNote className="w-12 h-12 mx-auto mb-3 opacity-20" />
              <p className="text-sm">Henüz bir not eklemediniz.</p>
            </div>
          ) : (
            notes.map((note) => (
              <div key={note.id} className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 relative group hover:shadow-md transition-shadow">
                {editingNoteId === note.id ? (
                  <div className="flex flex-col gap-2">
                    <textarea
                      ref={editTextareaRef}
                      value={editingContent}
                      onChange={(e) => setEditingContent(e.target.value)}
                      className="w-full text-sm text-gray-700 p-2 border border-purple-300 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 min-h-[80px] resize-y"
                    />
                    <div className="flex justify-end gap-2 mt-1">
                      <button 
                        onClick={handleCancelEdit}
                        disabled={isUpdating}
                        className="text-xs bg-gray-100 text-gray-600 px-3 py-1.5 rounded hover:bg-gray-200 transition-colors"
                      >
                        İptal
                      </button>
                      <button 
                        onClick={() => handleUpdateNote(note.id)}
                        disabled={isUpdating}
                        className="text-xs bg-purple-600 text-white px-3 py-1.5 rounded hover:bg-purple-700 transition-colors flex items-center"
                      >
                        {isUpdating ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : 'Kaydet'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="text-gray-700 text-sm whitespace-pre-wrap">{note.content}</p>
                    <div className="mt-3 flex justify-between items-center">
                      <span className="text-xs text-gray-400 font-medium">
                        {new Date(note.timestamp).toLocaleString('tr-TR', {
                          day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
                        })}
                      </span>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => handleStartEdit(note)}
                          className="text-gray-400 hover:text-blue-500 p-1.5 rounded-lg hover:bg-blue-50"
                          title="Düzenle"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteNote(note.id)}
                          className="text-gray-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-red-50"
                          title="Sil"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))
          )}
        </div>

        {/* Add Note Section */}
        <div className="p-4 bg-white border-t border-gray-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
          {error && <p className="text-red-500 text-xs mb-2">{error}</p>}
          <textarea
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAddNote();
              }
            }}
            placeholder="Yeni not ekle... (Enter ile kaydet)"
            className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:border-yellow-400 focus:outline-none focus:ring-2 focus:ring-yellow-200 min-h-[80px] resize-none"
          />
          <button
            onClick={handleAddNote}
            disabled={isSubmitting}
            className="mt-3 w-full bg-yellow-400 hover:bg-yellow-500 text-yellow-900 font-bold py-2.5 rounded-lg transition-colors flex items-center justify-center disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Plus className="w-5 h-5 mr-1" /> Kaydet</>}
          </button>
        </div>
      </div>
    </>
  );
};
