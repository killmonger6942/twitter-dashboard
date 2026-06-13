import { useEffect, useState } from 'react';
import { Trash2, Play, CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import { api } from '../lib/api';
import type { ContentItem, Account } from '../lib/api';

export default function Queue() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [filter, setFilter] = useState('all');
  const [posting, setPosting] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    const [content, accts] = await Promise.all([
      api.content.list(),
      api.accounts.list(),
    ]);
    setItems(content);
    setAccounts(accts);
  };

  useEffect(() => { load(); }, []);

  const getUsername = (accountId: string) => {
    return accounts.find(a => a.id === accountId)?.username || 'unknown';
  };

  const postItem = async (id: string) => {
    setPosting(id);
    setError('');
    try {
      await api.content.post(id);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
    setPosting(null);
  };

  const deleteItem = async (id: string) => {
    await api.content.delete(id);
    await load();
  };

  const filtered = filter === 'all' ? items : items.filter(i => i.status === filter);

  const statusIcon = (status: string) => {
    switch (status) {
      case 'posted': return <CheckCircle size={16} className="text-green-500" />;
      case 'failed': return <XCircle size={16} className="text-red-500" />;
      case 'posting': return <Loader2 size={16} className="text-yellow-500 animate-spin" />;
      case 'scheduled': return <Clock size={16} className="text-blue-400" />;
      default: return <Clock size={16} className="text-neutral-500" />;
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Content Queue</h2>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {['all', 'draft', 'approved', 'scheduled', 'posted', 'failed'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm ${
              filter === s ? 'bg-blue-600 text-white' : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
            {s !== 'all' && ` (${items.filter(i => i.status === s).length})`}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {filtered.map(item => (
          <div key={item.id} className="bg-neutral-800 border border-neutral-700 rounded-lg p-4 flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                {statusIcon(item.status)}
                <span className="text-sm text-blue-400">@{getUsername(item.account_id)}</span>
                <span className="text-xs text-neutral-500">{item.content_type}</span>
                {item.posted_at && (
                  <span className="text-xs text-neutral-500">{new Date(item.posted_at).toLocaleString()}</span>
                )}
              </div>
              <p className="text-sm text-neutral-300">{item.body}</p>
              {item.error_message && (
                <p className="text-xs text-red-400 mt-1">{item.error_message}</p>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              {(item.status === 'draft' || item.status === 'approved') && (
                <button
                  onClick={() => postItem(item.id)}
                  disabled={posting === item.id}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 text-sm"
                >
                  {posting === item.id ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  Post
                </button>
              )}
              <button
                onClick={() => deleteItem(item.id)}
                className="bg-red-900/50 hover:bg-red-800 text-red-300 px-2 py-1.5 rounded-lg"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-neutral-500 text-center py-8">No content items.</p>
        )}
      </div>
    </div>
  );
}
