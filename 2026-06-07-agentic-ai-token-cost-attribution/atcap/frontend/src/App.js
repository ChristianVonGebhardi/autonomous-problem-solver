import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import OverviewDashboard from './components/OverviewDashboard';
import CostBreakdown from './components/CostBreakdown';
import BudgetManager from './components/BudgetManager';
import ROICorrelation from './components/ROICorrelation';
import PricingCatalog from './components/PricingCatalog';
import AlertsPanel from './components/AlertsPanel';
import styles from './App.module.css';

const VIEWS = {
  overview: OverviewDashboard,
  costs: CostBreakdown,
  budgets: BudgetManager,
  roi: ROICorrelation,
  pricing: PricingCatalog,
  alerts: AlertsPanel,
};

export default function App() {
  const [activeView, setActiveView] = useState('overview');
  const View = VIEWS[activeView] || OverviewDashboard;

  return (
    <div className={styles.app}>
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className={styles.main}>
        <View />
      </main>
    </div>
  );
}