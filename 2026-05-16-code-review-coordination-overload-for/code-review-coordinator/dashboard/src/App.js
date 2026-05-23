import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import MetricsBar from './components/MetricsBar';
import ReviewerBoard from './components/ReviewerBoard';
import PRQueue from './components/PRQueue';
import PRList from './components/PRList';
import ActivityFeed from './components/ActivityFeed';
import AssignmentsView from './components/AssignmentsView';
import './App.css';

export default function App() {
  const [tab, setTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [reviewers, setReviewers] = useState([]);
  const [prs, setPRs] = useState([]);
  const [queue, setQueue] = useState({ queue_length: 0, prs: [] });
  const [events, setEvents] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [m, r, p, q, e, a] = await Promise.all([
        api.getMetrics(),
        api.getReviewers(),
        api.getPRs(),
        api.getQueue(),
        api.getEvents(),
        api.getAssignments(),
      ]);
      setMetrics(m);
      setReviewers(Array.isArray(r) ? r : []);
      setPRs(Array.isArray(p) ? p : []);
      setQueue(q || { queue_length: 0, prs: [] });
      setEvents(Array.isArray(e) ? e : []);
      setAssignments(Array.isArray(a) ? a : []);
      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 15000);
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
        {[
          ['overview',    `📊 Overview`],
          ['reviewers',   `👥 Reviewers (${reviewers.length})`],
          ['prs',         `📋 Pull Requests (${prs.length})`],
          ['queue',       `⏳ Queue (${queue.queue_length})`],
          ['assignments', `🎯 Assignments (${assignments.length})`],
          ['activity',   `📝 Activity`],
        ].map(([t, label]) => (
          <button
            key={t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {label}
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
        {tab === 'assignments' && <AssignmentsView assignments={assignments} />}
        {tab === 'activity' && <ActivityFeed events={events} />}
      </main>
    </div>
  );
}