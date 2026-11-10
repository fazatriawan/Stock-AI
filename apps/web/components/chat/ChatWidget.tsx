"use client";

import { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { MessageCircle, X, Send, RefreshCw, Bot, User } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
}

const SUGGESTIONS = [
  "Apa itu RSI dan cara bacanya?",
  "Bagaimana cara baca P/L di portofolio?",
  "Apa perbedaan lot dan saham?",
  "Bagaimana cara kerja Rekomendasi?",
  "Apa itu PER dan PBV?",
];

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-blue-400/60 rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${
        isUser ? "bg-blue-600" : "bg-gray-700"
      }`}>
        {isUser
          ? <User size={12} className="text-white" />
          : <Bot size={12} className="text-blue-300" />}
      </div>
      <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
        isUser
          ? "bg-blue-600 text-white rounded-tr-sm"
          : "bg-gray-800 text-gray-200 rounded-tl-sm"
      }`}>
        {msg.pending ? <TypingDots /> : msg.content}
      </div>
    </div>
  );
}

export function ChatWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "Halo! Saya asisten Stock Intelligence 👋\n\nSaya bisa bantu kamu memahami fitur aplikasi ini, menjelaskan istilah keuangan, atau menjawab pertanyaan tentang portofoliomu. Tanyakan apa saja!",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, messages]);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text.trim() };
    const pendingMsg: Message = { role: "assistant", content: "", pending: true };

    setMessages(prev => [...prev, userMsg, pendingMsg]);
    setInput("");
    setLoading(true);

    // Riwayat untuk konteks (kecuali pesan pending)
    const history = messages
      .filter(m => !m.pending)
      .map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await api.chat.send({
        message: text.trim(),
        history,
        context: { page: pathname },
      });
      setMessages(prev => [
        ...prev.slice(0, -1), // hapus pending
        { role: "assistant", content: res.reply },
      ]);
    } catch {
      setMessages(prev => [
        ...prev.slice(0, -1),
        { role: "assistant", content: "Maaf, gagal menghubungi asisten. Periksa koneksi dan coba lagi." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`fixed bottom-5 right-5 z-50 w-13 h-13 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 ${
          open
            ? "bg-gray-700 hover:bg-gray-600 rotate-90"
            : "bg-blue-600 hover:bg-blue-500 shadow-blue-900/40"
        }`}
        style={{ width: 52, height: 52 }}
        aria-label="Buka asisten"
      >
        {open
          ? <X size={20} className="text-white" />
          : <MessageCircle size={20} className="text-white" />}
      </button>

      {/* Chat drawer */}
      {open && (
        <div className="fixed bottom-20 right-5 z-50 w-[360px] max-w-[calc(100vw-2.5rem)] h-[520px] max-h-[calc(100vh-100px)] bg-gray-900 border border-gray-700/60 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 border-b border-gray-800 bg-gray-900/95">
            <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-600/30 flex items-center justify-center">
              <Bot size={14} className="text-blue-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-100">Asisten Stock Intelligence</p>
              <p className="text-[10px] text-gray-500">Powered by Claude Opus · Bukan nasihat investasi</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="ml-auto text-gray-600 hover:text-gray-400 transition-colors"
            >
              <X size={15} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Quick suggestions — tampil hanya jika belum ada riwayat user */}
          {messages.filter(m => m.role === "user").length === 0 && (
            <div className="px-3 pb-2 flex gap-1.5 flex-wrap">
              {SUGGESTIONS.slice(0, 3).map(s => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="text-[11px] px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-full transition-colors border border-gray-700/50"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-3 pb-3 pt-2 border-t border-gray-800">
            <div className="flex items-center gap-2 bg-gray-800 border border-gray-700/60 rounded-xl px-3 py-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Tanyakan sesuatu..."
                disabled={loading}
                className="flex-1 bg-transparent text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={loading || !input.trim()}
                className="text-blue-400 hover:text-blue-300 disabled:opacity-30 transition-colors shrink-0"
              >
                {loading
                  ? <RefreshCw size={15} className="animate-spin" />
                  : <Send size={15} />}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
