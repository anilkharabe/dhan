import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Performance from './pages/Performance';
import KiteTradingPage from './pages/KiteTradingPage';
import Backtest from './pages/Backtest';
import Scanner from './pages/Scanner';
import './App.css';

function AppContent() {
  const location = useLocation();
  const isKite = location.pathname === '/kite';

  // Kite terminal renders full-screen without the Layout wrapper
  if (isKite) {
    return (
      <Routes>
        <Route path="/kite" element={<KiteTradingPage />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
