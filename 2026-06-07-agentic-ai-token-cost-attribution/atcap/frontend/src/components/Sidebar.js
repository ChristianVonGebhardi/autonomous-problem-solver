import React from 'react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: '📊' },
  { id: 'costs', label: 'Cost Breakdown', icon: '💰' },
  { id: 'budgets', label: 'Budget Policies', icon: '🎯' },
  { id: 'alerts', label: 'Alerts', icon: '🔔' },
  { id: 'roi', label: 'ROI Correlation', icon: '📈' },
  { id: 'pricing', label: 'Pricing Catalog', icon: '🏷️' },
];

export default function Sidebar({ activeView, onNavigate }) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>⚡</span>
        <div>
          <div className={styles.logoTitle}>ATCAP</div>
          <div className={styles.logoSub}>Token Cost Attribution</div>
        </div>
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map(item => (
          <button
            key={item.id}
            className={`${styles.navItem} ${activeView === item.id ? styles.active : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className={styles.navIcon}>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className={styles.footer}>
        <div className={styles.footerTag}>v0.1.0</div>
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
          className={styles.footerLink}
        >
          API Docs →
        </a>
      </div>
    </aside>
  );
}