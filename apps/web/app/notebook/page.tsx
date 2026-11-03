"use client";

import React, { useEffect, useRef, useState } from "react";
import { api, type ResearchNote, type NoteCreateRequest } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtDate(d: string): string {
  return new Date(d).toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function TagPill({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <span
      onClick={onClick}
      className={`text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400 border border-gray-600/40 ${onClick ? "cursor-pointer hover:bg-gray-600" : ""}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// New note form
// ---------------------------------------------------------------------------
function NewNoteForm({ onCreated }: { onCreated: (note: ResearchNote) => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<NoteCreateRequest>({ title: "" });
  const [tagsInput, setTagsInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setTimeout(() => titleRef.current?.focus(), 50);
  }, [open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) { setErr("Judul wajib diisi"); return; }
    setSaving(true);
    setErr(null);
    const tags = tagsInput.split(/[\s,]+/).map(t => t.trim()).filter(Boolean);
    try {
      const note = await api.notebook.create({ ...form, tags: tags.length ? tags : undefined });
      setOpen(false);
      setForm({ title: "" });
      setTagsInput("");
      onCreated(note);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return (
    <button
      onClick={() => setOpen(true)}
      className="text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded-lg transition-colors"
    >
      + Catatan Baru
    </button>
  );

  return (
    <form onSubmit={submit} className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-4 space-y-3">
      <p className="text-xs font-medium text-gray-300">Catatan Baru</p>
      {err && <p className="text-xs text-red-400">{err}</p>}
      <input
        ref={titleRef}
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        placeholder="Judul *"
        value={form.title}
        onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
      />
      <div className="grid grid-cols-2 gap-3">
        <input
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
          placeholder="Ticker (mis. BBCA)"
          value={form.canonical_symbol ?? ""}
          onChange={e => setForm(f => ({ ...f, canonical_symbol: e.target.value || undefined }))}
        />
        <input
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
          placeholder="Tags (spasi/koma)"
          value={tagsInput}
          onChange={e => setTagsInput(e.target.value)}
        />
      </div>
      <textarea
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500 h-28 resize-none"
        placeholder="Isi catatan..."
        value={form.body ?? ""}
        onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
      />
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs px-3 py-1.5 text-gray-500 hover:text-gray-300 transition-colors"
        >
          Batal
        </button>
        <button
          type="submit"
          disabled={saving}
          className="text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {saving ? "Menyimpan..." : "Simpan"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Note editor (inline edit)
// ---------------------------------------------------------------------------
function NoteEditor({
  note,
  onSaved,
  onDeleted,
  onClose,
}: {
  note: ResearchNote;
  onSaved: (n: ResearchNote) => void;
  onDeleted: (id: string) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(note.title);
  const [body, setBody] = useState(note.body);
  const [tagsInput, setTagsInput] = useState(note.tags.join(", "));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!title.trim()) { setErr("Judul wajib diisi"); return; }
    setSaving(true);
    setErr(null);
    const tags = tagsInput.split(/[\s,]+/).map(t => t.trim()).filter(Boolean);
    try {
      const updated = await api.notebook.update(note.id, { title, body, tags });
      onSaved(updated);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  }

  async function del() {
    if (!confirm("Hapus catatan ini?")) return;
    setDeleting(true);
    try {
      await api.notebook.delete(note.id);
      onDeleted(note.id);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Gagal menghapus");
      setDeleting(false);
    }
  }

  return (
    <div className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-4 space-y-3">
      {err && <p className="text-xs text-red-400">{err}</p>}
      <input
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500 font-medium"
        value={title}
        onChange={e => setTitle(e.target.value)}
      />
      <textarea
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500 h-40 resize-y"
        value={body}
        onChange={e => setBody(e.target.value)}
      />
      <input
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        placeholder="Tags (spasi/koma)"
        value={tagsInput}
        onChange={e => setTagsInput(e.target.value)}
      />
      <div className="flex gap-2 justify-between">
        <button
          onClick={del}
          disabled={deleting}
          className="text-xs px-2 py-1 text-red-500 hover:text-red-400 disabled:opacity-50 transition-colors"
        >
          {deleting ? "Menghapus..." : "Hapus"}
        </button>
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="text-xs px-3 py-1.5 text-gray-500 hover:text-gray-300 transition-colors"
          >
            Tutup
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {saving ? "Menyimpan..." : "Simpan"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Note card (list view)
// ---------------------------------------------------------------------------
function NoteCard({
  note,
  onEdit,
}: {
  note: ResearchNote;
  onEdit: () => void;
}) {
  const preview = note.body.slice(0, 120) + (note.body.length > 120 ? "…" : "");
  const ticker = note.canonical_symbol?.split(":")?.[1] ?? note.canonical_symbol;

  return (
    <button
      onClick={onEdit}
      className="w-full text-left bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 hover:border-gray-600/60 transition-colors space-y-1.5"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-gray-100">{note.title}</p>
        {ticker && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 bg-blue-900/30 text-blue-400 border border-blue-800/30 rounded shrink-0">
            {ticker}
          </span>
        )}
      </div>
      {preview && <p className="text-xs text-gray-500 line-clamp-2">{preview}</p>}
      <div className="flex flex-wrap gap-1 items-center">
        {note.tags.map(t => <TagPill key={t} label={t} />)}
        <span className="text-[10px] text-gray-600 ml-auto">{fmtDate(note.updated_at)}</span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function NotebookPage() {
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.notebook.list({ limit: 100 })
      .then(setNotes)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  // All unique tags
  const allTags = Array.from(new Set(notes.flatMap(n => n.tags))).sort();

  // Filter locally
  const visible = notes.filter(n => {
    if (tagFilter && !n.tags.includes(tagFilter)) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!n.title.toLowerCase().includes(s) && !n.body.toLowerCase().includes(s)) return false;
    }
    return true;
  });

  const editNote = editId ? notes.find(n => n.id === editId) ?? null : null;

  function onCreated(note: ResearchNote) {
    setNotes(prev => [note, ...prev]);
    setEditId(note.id);
  }

  function onSaved(updated: ResearchNote) {
    setNotes(prev => prev.map(n => n.id === updated.id ? updated : n));
    setEditId(null);
  }

  function onDeleted(id: string) {
    setNotes(prev => prev.filter(n => n.id !== id));
    setEditId(null);
  }

  return (
    <div className="p-6 space-y-4 max-w-2xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Notebook Riset</h1>
        <p className="text-xs text-gray-500 mt-0.5">Catatan ide, analisis, dan insight investasi</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {/* Search + New */}
      <div className="flex gap-2">
        <input
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
          placeholder="Cari catatan..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <NewNoteForm onCreated={onCreated} />
      </div>

      {/* Tag filter */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setTagFilter(null)}
            className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${!tagFilter ? "bg-gray-600 text-gray-200 border-gray-500" : "bg-transparent text-gray-500 border-gray-700 hover:border-gray-500"}`}
          >
            Semua
          </button>
          {allTags.map(t => (
            <button
              key={t}
              onClick={() => setTagFilter(tagFilter === t ? null : t)}
              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${tagFilter === t ? "bg-gray-600 text-gray-200 border-gray-500" : "bg-transparent text-gray-500 border-gray-700 hover:border-gray-500"}`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {/* Editor (when a note is selected) */}
      {editNote && (
        <NoteEditor
          note={editNote}
          onSaved={onSaved}
          onDeleted={onDeleted}
          onClose={() => setEditId(null)}
        />
      )}

      {/* Note list */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 bg-gray-800 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className="text-center py-12 text-gray-600 text-sm">
          {search || tagFilter ? "Tidak ada catatan yang cocok" : "Belum ada catatan — buat yang pertama!"}
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map(n => (
            <NoteCard key={n.id} note={n} onEdit={() => setEditId(n.id === editId ? null : n.id)} />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-600">{notes.length} catatan total</p>
    </div>
  );
}
