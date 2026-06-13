import { useEffect, useState } from 'react';
import { Plus, Save, Trash2, UserCircle, Sparkles, Loader2 } from 'lucide-react';
import { api } from '../lib/api';
import type { Persona, Account } from '../lib/api';

export default function Personas() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '', tone: '', topics: '', style_guide: '',
    posting_frequency: '3-5 per day', example_tweets: '',
  });
  const [error, setError] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [generating, setGenerating] = useState(false);

  const load = async () => {
    setPersonas(await api.personas.list());
    setAccounts(await api.accounts.list());
  };

  useEffect(() => { load(); }, []);

  const resetForm = () => {
    setForm({ name: '', tone: '', topics: '', style_guide: '', posting_frequency: '3-5 per day', example_tweets: '' });
    setEditing(null);
  };

  const startEdit = (p: Persona) => {
    setEditing(p.id);
    setForm({
      name: p.name,
      tone: p.tone,
      topics: p.topics.join(', '),
      style_guide: p.style_guide,
      posting_frequency: p.posting_frequency,
      example_tweets: p.example_tweets.join('\n'),
    });
  };

  const savePersona = async () => {
    if (!form.name.trim()) return;
    setError('');
    const data = {
      name: form.name,
      tone: form.tone,
      topics: form.topics.split(',').map(t => t.trim()).filter(Boolean),
      style_guide: form.style_guide,
      posting_frequency: form.posting_frequency,
      example_tweets: form.example_tweets.split('\n').map(t => t.trim()).filter(Boolean),
    };
    try {
      if (editing) {
        await api.personas.update(editing, data);
      } else {
        await api.personas.create(data);
      }
      resetForm();
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const generatePersona = async () => {
    if (!aiPrompt.trim()) return;
    setGenerating(true);
    setError('');
    try {
      const result = await api.personas.generate(aiPrompt.trim());
      setForm({
        name: result.name || '',
        tone: result.tone || '',
        topics: (result.topics || []).join(', '),
        style_guide: result.style_guide || '',
        posting_frequency: result.posting_frequency || '3-5 per day',
        example_tweets: (result.example_tweets || []).join('\n'),
      });
      setEditing(null);
      setAiPrompt('');
    } catch (e: any) {
      setError(e.message);
    }
    setGenerating(false);
  };

  const assignPersona = async (personaId: string, accountId: string) => {
    try {
      await api.personas.assign(personaId, accountId);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const deletePersona = async (id: string) => {
    if (!confirm('Delete this persona?')) return;
    await api.personas.delete(id);
    await load();
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Personas</h2>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 p-3 rounded-lg mb-4">
          {error}
          <button onClick={() => setError('')} className="ml-2 text-red-400 hover:text-red-200">x</button>
        </div>
      )}

      {/* AI Generate */}
      <div className="bg-neutral-800 border border-neutral-700 rounded-lg p-4 mb-4">
        <h3 className="font-semibold mb-3 flex items-center gap-2">
          <Sparkles size={16} className="text-amber-400" />
          Generate with AI
        </h3>
        <div className="flex gap-2">
          <input
            placeholder="Describe the persona... (e.g., sarcastic AI researcher who tweets about LLM failures)"
            value={aiPrompt}
            onChange={e => setAiPrompt(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && generatePersona()}
            className="flex-1 bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-amber-500"
          />
          <button
            onClick={generatePersona}
            disabled={generating || !aiPrompt.trim()}
            className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg flex items-center gap-2 shrink-0"
          >
            {generating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            Generate
          </button>
        </div>
        <p className="text-xs text-neutral-500 mt-2">AI will fill in the form below. Review and edit before saving.</p>
      </div>

      {/* Manual form */}
      <div className="bg-neutral-800 border border-neutral-700 rounded-lg p-4 mb-6">
        <h3 className="font-semibold mb-3">{editing ? 'Edit Persona' : 'New Persona'}</h3>
        <div className="space-y-3">
          <input
            placeholder="Persona name (e.g., Tech Contrarian)"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500"
          />
          <input
            placeholder="Tone (e.g., witty and irreverent)"
            value={form.tone}
            onChange={e => setForm({ ...form, tone: e.target.value })}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500"
          />
          <input
            placeholder="Topics (comma-separated, e.g., AI, startups, VC)"
            value={form.topics}
            onChange={e => setForm({ ...form, topics: e.target.value })}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500"
          />
          <textarea
            placeholder="Style guide (free-text voice instructions)"
            value={form.style_guide}
            onChange={e => setForm({ ...form, style_guide: e.target.value })}
            rows={3}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-3 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 resize-none"
          />
          <textarea
            placeholder="Example tweets (one per line)"
            value={form.example_tweets}
            onChange={e => setForm({ ...form, example_tweets: e.target.value })}
            rows={3}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-3 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={savePersona}
              disabled={!form.name.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg flex items-center gap-2"
            >
              {editing ? <Save size={16} /> : <Plus size={16} />}
              {editing ? 'Update' : 'Create'}
            </button>
            {editing && (
              <button onClick={resetForm} className="bg-neutral-700 hover:bg-neutral-600 text-white px-4 py-2 rounded-lg">
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {personas.map(p => {
          const assigned = accounts.filter(a => a.persona_id === p.id);
          const unassigned = accounts.filter(a => a.persona_id !== p.id);
          return (
            <div key={p.id} className="bg-neutral-800 border border-neutral-700 rounded-lg p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-semibold text-white flex items-center gap-2">
                    <UserCircle size={18} className="text-blue-400" />
                    {p.name}
                  </h4>
                  <p className="text-sm text-neutral-400 mt-1">{p.tone}</p>
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {p.topics.map(t => (
                      <span key={t} className="text-xs bg-neutral-700 text-neutral-300 px-2 py-0.5 rounded">{t}</span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => startEdit(p)} className="bg-neutral-700 hover:bg-neutral-600 text-white px-3 py-1.5 rounded-lg text-sm">Edit</button>
                  <button onClick={() => deletePersona(p.id)} className="bg-red-900/50 hover:bg-red-800 text-red-300 px-3 py-1.5 rounded-lg text-sm">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {assigned.length > 0 && (
                <div className="mt-3 pt-3 border-t border-neutral-700">
                  <span className="text-xs text-neutral-500">Assigned to: </span>
                  {assigned.map(a => (
                    <span key={a.id} className="text-xs text-blue-400 mr-2">@{a.username}</span>
                  ))}
                </div>
              )}

              {unassigned.length > 0 && (
                <div className="mt-2">
                  <select
                    defaultValue=""
                    onChange={e => { if (e.target.value) assignPersona(p.id, e.target.value); e.target.value = ''; }}
                    className="bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm text-neutral-300"
                  >
                    <option value="">Assign to account...</option>
                    {unassigned.map(a => (
                      <option key={a.id} value={a.id}>@{a.username}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
        {personas.length === 0 && (
          <p className="text-neutral-500 text-center py-8">No personas yet. Create one above or generate with AI.</p>
        )}
      </div>
    </div>
  );
}
