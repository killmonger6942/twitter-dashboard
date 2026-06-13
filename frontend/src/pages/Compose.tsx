import { useEffect, useState } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import type { Account, ContentItem } from '../lib/api';

export default function Compose() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [tweetText, setTweetText] = useState('');
  const [contentType, setContentType] = useState('tweet');
  const [targetUrl, setTargetUrl] = useState('');
  const [posting, setPosting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [recentPosts, setRecentPosts] = useState<ContentItem[]>([]);

  const [direction, setDirection] = useState('');
  const [generating, setGenerating] = useState(false);
  const [drafts, setDrafts] = useState<string[]>([]);
  const [personaName, setPersonaName] = useState('');

  useEffect(() => {
    api.accounts.list().then(accts => {
      const loggedIn = accts.filter(a => a.is_logged_in);
      setAccounts(loggedIn);
      if (loggedIn.length > 0) setSelectedAccount(loggedIn[0].id);
    });
    api.content.list().then(setRecentPosts).catch(() => {});
  }, []);

  const selectedHasPersona = accounts.find(a => a.id === selectedAccount)?.persona_id;

  const handleGenerate = async () => {
    if (!selectedAccount) return;
    setGenerating(true);
    setError('');
    setDrafts([]);
    try {
      const res = await api.content.generate(selectedAccount, direction);
      setDrafts(res.drafts);
      setPersonaName(res.persona_name);
    } catch (e: any) {
      setError(e.message);
    }
    setGenerating(false);
  };

  const handlePost = async () => {
    if (!selectedAccount || !tweetText.trim()) return;
    setPosting(true);
    setError('');
    setResult(null);

    try {
      const content = await api.content.create({
        account_id: selectedAccount,
        content_type: contentType,
        body: tweetText.trim(),
        target_tweet_url: targetUrl || undefined,
      });

      const postResult = await api.content.post(content.id);
      setResult(postResult);
      setTweetText('');
      setTargetUrl('');
      setDrafts([]);

      api.content.list().then(setRecentPosts).catch(() => {});
    } catch (e: any) {
      setError(e.message);
    }
    setPosting(false);
  };

  const charCount = tweetText.length;
  const isOverLimit = charCount > 280;

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-6">Compose</h2>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 p-3 rounded-lg mb-4">
          {error}
          <button onClick={() => setError('')} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      <div className="bg-neutral-800 border border-neutral-700 rounded-lg p-4 space-y-4">
        <div className="flex gap-3">
          <select
            value={selectedAccount}
            onChange={e => setSelectedAccount(e.target.value)}
            className="bg-neutral-700 border border-neutral-600 rounded-lg px-3 py-2 text-white"
          >
            {accounts.map(a => (
              <option key={a.id} value={a.id}>@{a.username}</option>
            ))}
            {accounts.length === 0 && <option value="">No accounts logged in</option>}
          </select>

          <select
            value={contentType}
            onChange={e => setContentType(e.target.value)}
            className="bg-neutral-700 border border-neutral-600 rounded-lg px-3 py-2 text-white"
          >
            <option value="tweet">Tweet</option>
            <option value="reply">Reply</option>
            <option value="like">Like</option>
            <option value="retweet">Retweet</option>
            <option value="follow">Follow</option>
          </select>
        </div>

        {(contentType === 'reply' || contentType === 'like' || contentType === 'retweet' || contentType === 'follow') && (
          <input
            type="text"
            placeholder={contentType === 'follow' ? 'Profile URL' : 'Tweet URL'}
            value={targetUrl}
            onChange={e => setTargetUrl(e.target.value)}
            className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-2 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500"
          />
        )}

        {selectedHasPersona && contentType === 'tweet' && (
          <div className="bg-neutral-750 border border-neutral-600 rounded-lg p-3 space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Topic hint (optional) e.g. 'something about AI agents'"
                value={direction}
                onChange={e => setDirection(e.target.value)}
                className="flex-1 bg-neutral-700 border border-neutral-600 rounded-lg px-3 py-2 text-white text-sm placeholder-neutral-500 focus:outline-none focus:border-purple-500"
              />
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium whitespace-nowrap"
              >
                {generating ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Sparkles size={16} />
                )}
                {generating ? 'Generating...' : 'AI Generate'}
              </button>
            </div>

            {drafts.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs text-neutral-400">
                  Generated by <span className="text-purple-400">{personaName}</span> — click to use:
                </p>
                {drafts.map((draft, i) => (
                  <button
                    key={i}
                    onClick={() => { setTweetText(draft); setDrafts([]); }}
                    className="w-full text-left bg-neutral-700 hover:bg-neutral-600 border border-neutral-600 hover:border-purple-500 rounded-lg p-3 text-sm text-neutral-200 transition-colors"
                  >
                    {draft}
                    <span className="block text-xs text-neutral-500 mt-1">{draft.length}/280</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {(contentType === 'tweet' || contentType === 'reply') && (
          <>
            <textarea
              placeholder="What's happening?"
              value={tweetText}
              onChange={e => setTweetText(e.target.value)}
              rows={4}
              className="w-full bg-neutral-700 border border-neutral-600 rounded-lg px-4 py-3 text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 resize-none"
            />
            <div className="flex justify-between items-center">
              <span className={`text-sm ${isOverLimit ? 'text-red-400' : 'text-neutral-400'}`}>
                {charCount}/280
              </span>
            </div>
          </>
        )}

        <button
          onClick={handlePost}
          disabled={posting || !selectedAccount || (contentType !== 'like' && contentType !== 'retweet' && contentType !== 'follow' && !tweetText.trim())}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-lg flex items-center justify-center gap-2 font-medium"
        >
          {posting ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              Posting via Computer Use...
            </>
          ) : (
            <>
              <Send size={18} />
              {contentType === 'tweet' ? 'Post Tweet' :
               contentType === 'reply' ? 'Post Reply' :
               contentType === 'like' ? 'Like Tweet' :
               contentType === 'retweet' ? 'Retweet' : 'Follow'}
            </>
          )}
        </button>
      </div>

      {result && (
        <div className="mt-4 bg-green-900/30 border border-green-700 rounded-lg p-4">
          <p className="text-green-300 font-medium">Posted successfully!</p>
          {result.computer_use_result && (
            <div className="text-sm text-neutral-400 mt-2 space-y-1">
              <p>Actions: {result.computer_use_result.actions_count}</p>
              <p>Cost: ${(result.computer_use_result.cost_cents / 100).toFixed(4)}</p>
              <p>Duration: {(result.computer_use_result.duration_ms / 1000).toFixed(1)}s</p>
            </div>
          )}
        </div>
      )}

      {recentPosts.length > 0 && (
        <div className="mt-8">
          <h3 className="text-lg font-semibold mb-3">Recent Activity</h3>
          <div className="space-y-2">
            {recentPosts.slice(0, 10).map(item => (
              <div key={item.id} className="bg-neutral-800 border border-neutral-700 rounded-lg p-3 flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      item.status === 'posted' ? 'bg-green-900 text-green-300' :
                      item.status === 'failed' ? 'bg-red-900 text-red-300' :
                      item.status === 'posting' ? 'bg-yellow-900 text-yellow-300' :
                      'bg-neutral-700 text-neutral-300'
                    }`}>
                      {item.status}
                    </span>
                    <span className="text-xs text-neutral-500">{item.content_type}</span>
                  </div>
                  <p className="text-sm text-neutral-300 truncate">{item.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
