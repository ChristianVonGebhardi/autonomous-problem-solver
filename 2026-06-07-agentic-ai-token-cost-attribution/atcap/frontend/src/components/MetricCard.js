import React from 'react';
import styles from './MetricCard.module.css';

export default function MetricCard({ title, value, subtitle, trend, color = 'blue', icon }) {
  const trendPositive = trend > 0;

  return (
    <div className={`${styles.card} ${styles[color]}`}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        {icon && <span className={styles.icon}>{icon}</span>}
      </div>
      <div className={styles.value}>{value}</div>
      {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
      {trend !== undefined && (
        <div className={`${styles.trend} ${trendPositive ? styles.up : styles.down}`}>
          {trendPositive ? '↑' : '↓'} {Math.abs(trend).toFixed(1)}% vs last period
        </div>
      )}
    </div>
  );
}