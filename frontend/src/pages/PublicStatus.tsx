import { useEffect, useState } from 'react';
import { Users, UserPlus, MessageSquare, CheckCircle2, XCircle, RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

// Read-only public status board. It NEVER talks to the backend or imports the
// control API -- it only fetches a static JSON snapshot published to a public
// GitHub repo. There is intentionally no way to trigger any action from here.

const STATUS_URL = import.meta.env.VITE_STATUS_URL as string | undefined;
const POLL_MS = 60_000;

interface Snapshot {
  generated_at: string;
  refresh_minutes: number;
  totals: { accounts: number; logged_in: number; active: number; total_followers: number };
  accounts: AccountBlock[];
}

interface AccountBlock {
  id: string;
  username: string;
  display_name: string;
  is_logged_in: boolean;
  is_active: boolean;
  behavior_enabled: boolean;
  campaign_enabled: boolean;
  profile: {
    current: { followers: number; following: number; tweets: number };
    growth: { followers?: number; following?: number; tweets?: number };
    history: Array<{ date: string; followers: number; following: number; tweets: number }>;
  };
  actions_7d: Record<string, { total: number; done: number; failed: number }>;
  campaign: { total: number; followed: number; remaining: number; failed: number; progress: number };
  recent: Array<{ action_type: string; status: string; time: string | null; source: string }>;
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function num(n: number): string {
  return n.toLocaleString();
}

function Stat({ icon: Icon, label, value, delta }: { icon: any; label: string; value: number; delta?: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-lg bg-neutral-800 text-neutral-300">
        <Icon size={18} />
      </div>
      <div>
        <div className="text-xs text-neutral-500">{label}</div>
        <div className="text-lg font-semibold text-white flex items-baseline gap-1.5">
          {num(value)}
          {delta !== undefined && delta !== 0 && (
            <span className={`text-xs font-medium ${delta > 0 ? 'text-green-400' : 'text-red-400'}`}>
              {delta > 0 ? '+' : ''}{num(delta)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function AccountCard({ a }: { a: AccountBlock }) {
  const history = a.profile.history.map(h => ({ date: h.date.slice(5), followers: h.followers }));
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <a
            href={`https://x.com/${a.username}`}
            target="_blank"
            rel="noreferrer"
            className="text-white font-semibold hover:text-blue-400"
          >
            @{a.username}
          </a>
          {a.display_name && <span className="text-neutral-500 text-sm ml-2">{a.display_name}</span>}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={`flex items-center gap-1 ${a.is_logged_in ? 'text-green-400' : 'text-neutral-500'}`}>
            <span className={`w-2 h-2 rounded-full ${a.is_logged_in ? 'bg-green-400' : 'bg-neutral-600'}`} />
            {a.is_logged_in ? 'logged in' : 'logged out'}
          </span>
          {a.behavior_enabled && <span className="px-2 py-0.5 rounded bg-blue-900/50 text-blue-300">auto</span>}
          {a.campaign_enabled && <span className="px-2 py-0.5 rounded bg-purple-900/50 text-purple-300">campaign</span>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <Stat icon={Users} label="Followers" value={a.profile.current.followers} delta={a.profile.growth.followers} />
        <Stat icon={UserPlus} label="Following" value={a.profile.current.following} delta={a.profile.growth.following} />
        <Stat icon={MessageSquare} label="Tweets" value={a.profile.current.tweets} delta={a.profile.growth.tweets} />
      </div>

      {history.length > 1 && (
        <div className="h-24 mb-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#737373' }} axisLine={false} tickLine={false} />
              <YAxis hide domain={['dataMin', 'dataMax']} />
              <Tooltip
                contentStyle={{ background: '#171717', border: '1px solid #404040', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#a3a3a3' }}
              />
              <Line type="monotone" dataKey="followers" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {a.campaign.total > 0 && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-neutral-400 mb-1">
            <span>Follow campaign</span>
            <span>{num(a.campaign.followed)} / {num(a.campaign.total)} ({a.campaign.progress}%)</span>
          </div>
          <div className="h-2 bg-neutral-800 rounded-full overflow-hidden">
            <div className="h-full bg-purple-500 rounded-full" style={{ width: `${a.campaign.progress}%` }} />
          </div>
        </div>
      )}

      {Object.keys(a.actions_7d).length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {Object.entries(a.actions_7d).map(([type, s]) => (
            <span key={type} className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-300">
              {type}: <span className="text-green-400">{s.done}</span>
              {s.failed > 0 && <span className="text-red-400"> / {s.failed}✗</span>}
            </span>
          ))}
        </div>
      )}

      {a.recent.length > 0 && (
        <div className="border-t border-neutral-800 pt-3 space-y-1.5">
          {a.recent.slice(0, 5).map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-neutral-400">
              {r.status === 'done' ? (
                <CheckCircle2 size={13} className="text-green-500 shrink-0" />
              ) : r.status === 'failed' ? (
                <XCircle size={13} className="text-red-500 shrink-0" />
              ) : (
                <span className="w-[13px] h-[13px] rounded-full bg-neutral-600 shrink-0" />
              )}
              <span className="text-neutral-300">{r.action_type}</span>
              <span className="text-neutral-600">·</span>
              <span className="truncate">{r.source}</span>
              <span className="ml-auto text-neutral-600">{r.time ? timeAgo(r.time) : ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PublicStatus() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!STATUS_URL) {
      setError('VITE_STATUS_URL is not configured for this deployment.');
      setLoading(false);
      return;
    }
    let active = true;
    const load = async () => {
      try {
        const res = await fetch(`${STATUS_URL}?t=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`Snapshot unavailable (${res.status})`);
        const json = (await res.json()) as Snapshot;
        if (active) {
          setData(json);
          setError('');
        }
      } catch (e: any) {
        if (active) setError(e.message || 'Failed to load status');
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const ageMin = data ? (Date.now() - new Date(data.generated_at).getTime()) / 60000 : Infinity;
  const stale = data ? ageMin > (data.refresh_minutes || 30) * 2 : false;

  return (
    <div className="min-h-screen bg-neutral-950 text-white">
      <div className="max-w-5xl mx-auto p-6">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Twitter Dashboard — Status</h1>
            <p className="text-neutral-500 text-sm">Read-only public view</p>
          </div>
          {data && (
            <div className="text-right">
              <div className={`flex items-center gap-1.5 justify-end text-sm font-medium ${stale ? 'text-amber-400' : 'text-green-400'}`}>
                <span className={`w-2 h-2 rounded-full ${stale ? 'bg-amber-400' : 'bg-green-400 animate-pulse'}`} />
                {stale ? 'Offline' : 'Live'}
              </div>
              <div className="text-xs text-neutral-500 flex items-center gap-1 justify-end mt-0.5">
                <RefreshCw size={11} /> updated {timeAgo(data.generated_at)}
              </div>
            </div>
          )}
        </header>

        {loading && <div className="text-neutral-500 text-sm">Loading status…</div>}

        {error && !data && (
          <div className="bg-red-900/40 border border-red-800 text-red-200 p-4 rounded-lg text-sm">{error}</div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
                <div className="text-xs text-neutral-500">Accounts</div>
                <div className="text-2xl font-bold">{data.totals.accounts}</div>
              </div>
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
                <div className="text-xs text-neutral-500">Logged in</div>
                <div className="text-2xl font-bold">{data.totals.logged_in}</div>
              </div>
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
                <div className="text-xs text-neutral-500">Active</div>
                <div className="text-2xl font-bold">{data.totals.active}</div>
              </div>
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
                <div className="text-xs text-neutral-500">Total followers</div>
                <div className="text-2xl font-bold">{num(data.totals.total_followers)}</div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {data.accounts.map(a => (
                <AccountCard key={a.id} a={a} />
              ))}
            </div>

            {data.accounts.length === 0 && (
              <div className="text-neutral-500 text-sm">No accounts yet.</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
