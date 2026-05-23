import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import MetricsBar from './components/MetricsBar';
import ReviewerBoard from './components/ReviewerBoard';
import PRQueue from './components/PRQueue';
import PRList from './components/PRList';
import ActivityFeed from './components/ActivityFeed';
import './App.css';

export default function App() {
  const [tab, setTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [reviewers, setReviewers] = useState([]);
  const [prs, setPRs] = useState([]);
  const [queue, setQueue] = useState({ queue_length: 0, prs: [] });
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [m, r, p, q, e] = await Promise.all([
        api.getMetrics(),
        api.getReviewers(),
        api.getPRs(),
        api.getQueue(),
        api.getEvents(),
      ]);
      setMetrics(m);
      setReviewers(r || []);
      setPRs(p || []);
      setQueue(q || { queue_length: 0, prs: [] });
      setEvents(e || []);
      setError(null);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 15000); // Refresh every 15s
    return () => clearInterval(interval);
  }, [refresh]);

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner" />
        <p>Connecting to Code Review Coordinator...</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <span className="logo">⚡</span>
          <h1>Code Review Coordinator</h1>
        </div>
        <div className="header-right">
          {error && <span className="error-badge">⚠ {error}</span>}
          {lastRefresh && (
            <span className="refresh-time">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button className="refresh-btn" onClick={refresh}>↻ Refresh</button>
        </div>
      </header>

      {metrics && <MetricsBar metrics={metrics} queueLength={queue.queue_length} />}

      <nav className="tabs">
        {['overview', 'reviewers', 'prs', 'queue', 'activity'].map(t => (
          <button
            key={t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'overview' && '📊 Overview'}
            {t === 'reviewers' && `👥 Reviewers (${reviewers.length})`}
            {t === 'prs' && `📋 Pull Requests (${prs.length})`}
            {t === 'queue' && `⏳ Queue (${queue.queue_length})`}
            {t === 'activity' && '📝 Activity'}
          </button>
        ))}
      </nav>

      <main className="main-content">
        {tab === 'overview' && (
          <div className="overview-grid">
            <ReviewerBoard reviewers={reviewers} />
            <PRQueue queue={queue} onRefresh={refresh} />
          </div>
        )}
        {tab === 'reviewers' && <ReviewerBoard reviewers={reviewers} detailed />}
        {tab === 'prs' && <PRList prs={prs} reviewers={reviewers} onRefresh={refresh} />}
        {tab === 'queue' && <PRQueue queue={queue} onRefresh={refresh} detailed />}
        {tab === 'activity' && <ActivityFeed events={events} />}
      </main>
    </div>
  );
}