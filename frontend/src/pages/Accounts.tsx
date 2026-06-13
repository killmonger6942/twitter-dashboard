import { useEffect, useState, useCallback } from 'react';
import { Plus, LogIn, CheckCircle, XCircle, Trash2, Camera, ChevronDown, ChevronUp, Play, Square, Loader2, RefreshCw, TrendingUp, TrendingDown, Users, UserPlus, MessageSquare } from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../lib/api';
import type { Account } from '../lib/api';

const ACTION_COLORS: Record<string, string> = {
  tweet: '#3b82f6',
  like: '#ef4444',
  retweet: '#22c55e',
  reply: '#a855f7',
  follow: '#f59e0b',
};

const ACTION_LABELS: Record<string, string> = {
  tweet: 'Tweets',
  like: 'Likes',
  retweet: 'Reposts',
  reply: 'Replies',
  follow: 'Follows',
};

function AccountAnalytics({ account }: { account: Account }) {
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<Record<string, { total: number; done: number; failed: number }>>({});
  const [timeline, setTimeline] = useState<any[]>([]);
  const [successRate, setSuccessRate] = useState<any[]>([]);
  const [campaign, setCampaign] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [engineStatus, setEngineStatus] = useState<any>(null);
  const [campaignStatus, setCampaignStatus] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [actionLoading, setActionLoading] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, t, sr, c, r, es, cs, p] = await Promise.all([
        api.analytics.summary(account.id, days),
        api.analytics.timeline(account.id, days),
        api.analytics.successRate(account.id, days),
        api.analytics.followCampaign(account.id),
        api.analytics.recent(account.id, 15),
        api.behavior.status(account.id).catch(() => null),
        api.behavior.followCampaignStatus(account.id).catch(() => null),
        api.analytics.profile(account.id).catch(() => null),
      ]);
      setSummary(s.actions);
      setTimeline(t);
      setSuccessRate(sr);
      setCampaign(c);
      setRecent(r);
      setEngineStatus(es);
      setCampaignStatus(cs);
      setProfile(p);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [account.id, days]);

  useEffect(() => { loadData(); }, [loadData]);

  const toggleEngine = async () => {
    setActionLoading('engine');
    try {
      if (engineStatus?.running) {
        await api.behavior.stop(account.id);
      } else {
        await api.behavior.start(account.id);
      }
      await loadData();
    } catch (e: any) {
      alert(e.message);
    }
    setActionLoading('');
  };

  const toggleCampaign = async () => {
    setActionLoading('campaign');
    try {
      if (campaignStatus?.running) {
        await api.behavior.followCampaignStop(account.id);
      } else {
        await api.behavior.followCampaignStart(account.id);
      }
      await loadData();
    } catch (e: any) {
      alert(e.message);
    }
    setActionLoading('');
  };

  const takeSnapshot = async () => {
    setActionLoading('snapshot');
    try {
      await api.analytics.snapshotProfile(account.id);
      await loadData();
    } catch (e: any) {
      alert(e.message);
    }
    setActionLoading('');
  };

  const summaryCards = ['tweet', 'like', 'retweet', 'reply', 'follow'].map((type) => ({
    type,
    label: ACTION_LABELS[type],
    done: summary[type]?.done || 0,
    failed: summary[type]?.failed || 0,
    color: ACTION_COLORS[type],
  }));

  return (
    <div className="mt-4 space-y-4">
      {/* Controls row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="bg-neutral-900 text-white border border-neutral-600 rounded-lg px-2 py-1 text-xs"
          >
            <option value={1}>24h</option>
            <option value={7}>7d</option>
            <option value={14}>14d</option>
            <option value={30}>30d</option>
          </select>
          <button
            onClick={loadData}
            className="p-1.5 bg-neutral-900 hover:bg-neutral-700 rounded-lg text-neutral-400 hover:text-white transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Engine controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${engineStatus?.running ? 'bg-green-500' : 'bg-neutral-600'}`} />
            <span className="text-xs text-neutral-400">Engine</span>
          </div>
          <button
            onClick={toggleEngine}
            disabled={actionLoading === 'engine'}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              engineStatus?.running
                ? 'bg-red-600/80 hover:bg-red-600 text-white'
                : 'bg-green-600/80 hover:bg-green-600 text-white'
            } disabled:opacity-50`}
          >
            {actionLoading === 'engine' ? <Loader2 size={10} className="animate-spin" /> :
              engineStatus?.running ? <><Square size={10} /> Stop</> : <><Play size={10} /> Start</>}
          </button>

          <div className="w-px h-4 bg-neutral-700 mx-1" />

          <div className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${campaignStatus?.running ? 'bg-green-500' : 'bg-neutral-600'}`} />
            <span className="text-xs text-neutral-400">Campaign</span>
          </div>
          <button
            onClick={toggleCampaign}
            disabled={actionLoading === 'campaign'}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              campaignStatus?.running
                ? 'bg-red-600/80 hover:bg-red-600 text-white'
                : 'bg-green-600/80 hover:bg-green-600 text-white'
            } disabled:opacity-50`}
          >
            {actionLoading === 'campaign' ? <Loader2 size={10} className="animate-spin" /> :
              campaignStatus?.running ? <><Square size={10} /> Stop</> : <><Play size={10} /> Start</>}
          </button>
        </div>
      </div>

      {/* Profile metrics */}
      <div className="bg-neutral-900 rounded-lg p-4 border border-neutral-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-white">Profile Stats</h3>
          <button
            onClick={takeSnapshot}
            disabled={actionLoading === 'snapshot'}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium bg-blue-600/80 hover:bg-blue-600 text-white transition-colors disabled:opacity-50"
          >
            {actionLoading === 'snapshot' ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
            Sync from Twitter
          </button>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {[
            { key: 'followers', label: 'Followers', icon: Users, color: '#3b82f6' },
            { key: 'following', label: 'Following', icon: UserPlus, color: '#22c55e' },
            { key: 'tweets', label: 'Tweets', icon: MessageSquare, color: '#a855f7' },
          ].map(({ key, label, icon: Icon, color }) => {
            const value = profile?.current?.[key] ?? 0;
            const change = profile?.growth?.[key];
            return (
              <div key={key} className="flex items-center gap-3">
                <div className="p-2 rounded-lg" style={{ backgroundColor: color + '22' }}>
                  <Icon size={18} style={{ color }} />
                </div>
                <div>
                  <div className="text-xl font-bold text-white">{value.toLocaleString()}</div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-neutral-400">{label}</span>
                    {change !== undefined && change !== 0 && (
                      <span className={`flex items-center gap-0.5 text-xs ${change > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {change > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                        {change > 0 ? '+' : ''}{change}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {profile?.history && profile.history.length > 1 && (
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={120}>
              <LineChart data={profile.history}>
                <XAxis dataKey="date" stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 10 }} />
                <YAxis stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#fff' }} />
                <Line type="monotone" dataKey="followers" stroke="#3b82f6" strokeWidth={2} dot={false} name="Followers" />
                <Line type="monotone" dataKey="following" stroke="#22c55e" strokeWidth={2} dot={false} name="Following" />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-2">
        {summaryCards.map((card) => (
          <div key={card.type} className="bg-neutral-900 rounded-lg p-3 border border-neutral-700">
            <div className="text-2xl font-bold text-white">{card.done}</div>
            <div className="text-xs font-medium" style={{ color: card.color }}>{card.label}</div>
            {card.failed > 0 && <div className="text-xs text-red-400">{card.failed} failed</div>}
          </div>
        ))}
      </div>

      {/* Timeline chart */}
      {timeline.length > 0 && (
        <div className="bg-neutral-900 rounded-lg p-4 border border-neutral-700">
          <h3 className="text-sm font-semibold text-white mb-3">Activity Timeline</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={timeline}>
              <XAxis dataKey="date" stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 11 }} />
              <YAxis stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#fff' }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {Object.entries(ACTION_COLORS).map(([key, color]) => (
                <Line key={key} type="monotone" dataKey={key} stroke={color} strokeWidth={2} dot={false} name={ACTION_LABELS[key] || key} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Success rate + Campaign side by side */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-neutral-900 rounded-lg p-4 border border-neutral-700">
          <h3 className="text-sm font-semibold text-white mb-3">Success Rate</h3>
          {successRate.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={successRate}>
                <XAxis dataKey="action_type" stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 11 }} />
                <YAxis stroke="#525252" tick={{ fill: '#a3a3a3', fontSize: 11 }} />
                <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#fff' }} />
                <Bar dataKey="done" fill="#22c55e" name="Done" radius={[3, 3, 0, 0]} />
                <Bar dataKey="failed" fill="#ef4444" name="Failed" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-neutral-500 text-xs">No data yet</p>}
        </div>

        <div className="bg-neutral-900 rounded-lg p-4 border border-neutral-700">
          <h3 className="text-sm font-semibold text-white mb-3">Follow Campaign</h3>
          {campaign && campaign.total > 0 ? (
            <div className="space-y-3">
              <div className="flex justify-between text-xs">
                <span className="text-neutral-400">Progress</span>
                <span className="text-white font-medium">{campaign.progress}%</span>
              </div>
              <div className="w-full bg-neutral-700 rounded-full h-2">
                <div className="bg-amber-500 h-2 rounded-full transition-all" style={{ width: `${campaign.progress}%` }} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <div className="text-lg font-bold text-white">{campaign.followed}</div>
                  <div className="text-neutral-400">Followed</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-white">{campaign.remaining}</div>
                  <div className="text-neutral-400">Remaining</div>
                </div>
                <div>
                  <div className="text-lg font-bold text-red-400">{campaign.failed}</div>
                  <div className="text-neutral-400">Failed</div>
                </div>
              </div>
            </div>
          ) : <p className="text-neutral-500 text-xs">No campaign data</p>}
        </div>
      </div>

      {/* Next action */}
      {engineStatus?.running && engineStatus?.next_action && (
        <div className="bg-neutral-900 rounded-lg px-4 py-2 border border-neutral-700 flex items-center gap-2 text-xs">
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-neutral-400">Next action:</span>
          <span className="text-white font-medium">{engineStatus.next_action.action_type}</span>
          <span className="text-neutral-500">@</span>
          <span className="text-neutral-300">{new Date(engineStatus.next_action.scheduled_time).toLocaleTimeString()}</span>
        </div>
      )}

      {/* Recent activity */}
      {recent.length > 0 && (
        <div className="bg-neutral-900 rounded-lg p-4 border border-neutral-700">
          <h3 className="text-sm font-semibold text-white mb-3">Recent Activity</h3>
          <div className="space-y-1">
            {recent.map((r, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5 border-b border-neutral-800 last:border-0 text-xs">
                <span className="text-neutral-500 w-32 shrink-0">
                  {r.time ? new Date(r.time).toLocaleString() : '-'}
                </span>
                <span className="px-1.5 py-0.5 rounded text-xs font-medium shrink-0"
                  style={{ backgroundColor: (ACTION_COLORS[r.action_type] || '#525252') + '22', color: ACTION_COLORS[r.action_type] || '#a3a3a3' }}>
                  {r.action_type}
                </span>
                <span className="text-neutral-500">{r.category || ''}</span>
                {r.source === 'manual' && <span className="text-neutral-600 text-[10px]">manual</span>}
                <span className={`ml-auto shrink-0 ${
                  r.status === 'done' ? 'text-green-400' : r.status === 'failed' ? 'text-red-400' : r.status === 'executing' ? 'text-blue-400' : 'text-neutral-500'
                }`}>{r.status}</span>
                {r.error_message && <span className="text-red-400 truncate max-w-32">{r.error_message}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [newUsername, setNewUsername] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [screenshot, setScreenshot] = useState<{ id: string; data: string } | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadAccounts = async () => {
    try {
      setAccounts(await api.accounts.list());
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => { loadAccounts(); }, []);

  const addAccount = async () => {
    if (!newUsername.trim()) return;
    setLoading(true);
    setError('');
    try {
      await api.accounts.add(newUsername.trim().replace('@', ''));
      setNewUsername('');
      await loadAccounts();
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const openLogin = async (id: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await api.accounts.login(id);
      alert(res.message);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const confirmLogin = async (id: string) => {
    setLoading(true);
    try {
      await api.accounts.confirmLogin(id);
      await loadAccounts();
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const viewScreenshot = async (id: string) => {
    try {
      const res = await api.accounts.screenshot(id);
      setScreenshot({ id, data: res.screenshot });
    } catch (e: any) {
      setError(e.message);
    }
  };

  const deleteAccount = async (id: string) => {
    if (!confirm('Delete this account?')) return;
    try {
      await api.accounts.delete(id);
      await loadAccounts();
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Accounts</h2>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 p-3 rounded-lg mb-4">
          {error}
          <button onClick={() => setError('')} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      <div className="flex gap-3 mb-6">
        <input
          type="text"
          placeholder="Twitter username (without @)"
          value={newUsername}
          onChange={e => setNewUsername(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addAccount()}
          className="flex-1 bg-neutral-800 border border-neutral-700 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500"
        />
        <button
          onClick={addAccount}
          disabled={loading || !newUsername.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg flex items-center gap-2"
        >
          <Plus size={18} /> Add
        </button>
      </div>

      <div className="space-y-3">
        {accounts.map(account => (
          <div key={account.id} className="bg-neutral-800 border border-neutral-700 rounded-lg overflow-hidden">
            <div className="p-4 flex items-center justify-between">
              <button
                onClick={() => setExpandedId(expandedId === account.id ? null : account.id)}
                className="flex items-center gap-3 text-left"
              >
                {account.is_logged_in
                  ? <CheckCircle size={20} className="text-green-500" />
                  : <XCircle size={20} className="text-red-500" />
                }
                <div>
                  <span className="font-medium text-white">@{account.username}</span>
                  <span className="text-neutral-400 text-sm ml-2">
                    {account.is_logged_in ? 'Connected' : 'Not logged in'}
                  </span>
                </div>
                {account.is_logged_in && (
                  expandedId === account.id
                    ? <ChevronUp size={16} className="text-neutral-400" />
                    : <ChevronDown size={16} className="text-neutral-400" />
                )}
              </button>
              <div className="flex gap-2">
                {!account.is_logged_in && (
                  <>
                    <button
                      onClick={() => openLogin(account.id)}
                      disabled={loading}
                      className="bg-neutral-700 hover:bg-neutral-600 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 text-sm"
                    >
                      <LogIn size={14} /> Login
                    </button>
                    <button
                      onClick={() => confirmLogin(account.id)}
                      disabled={loading}
                      className="bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 text-sm"
                    >
                      <CheckCircle size={14} /> Confirm
                    </button>
                  </>
                )}
                {account.is_logged_in && (
                  <button
                    onClick={() => viewScreenshot(account.id)}
                    className="bg-neutral-700 hover:bg-neutral-600 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 text-sm"
                  >
                    <Camera size={14} /> Screenshot
                  </button>
                )}
                <button
                  onClick={() => deleteAccount(account.id)}
                  className="bg-red-900/50 hover:bg-red-800 text-red-300 px-3 py-1.5 rounded-lg flex items-center gap-1 text-sm"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {expandedId === account.id && account.is_logged_in && (
              <div className="border-t border-neutral-700 px-4 pb-4">
                <AccountAnalytics account={account} />
              </div>
            )}
          </div>
        ))}
        {accounts.length === 0 && (
          <p className="text-neutral-500 text-center py-8">No accounts added yet. Add a Twitter username above.</p>
        )}
      </div>

      {screenshot && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50" onClick={() => setScreenshot(null)}>
          <div className="max-w-4xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <img src={`data:image/png;base64,${screenshot.data}`} alt="Browser screenshot" className="rounded-lg" />
            <button onClick={() => setScreenshot(null)} className="mt-3 bg-neutral-700 text-white px-4 py-2 rounded-lg w-full">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}
