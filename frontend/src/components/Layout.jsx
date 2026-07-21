import { Link, useLocation } from 'react-router-dom';

const Layout = ({ children }) => {
    const location = useLocation();
    const isActive = (path) => location.pathname === path;

    return (
        <div className="min-h-screen bg-slate-50">
            {/* Navigation Bar */}
            <nav className="fixed top-0 left-0 right-0 h-16 bg-white/80 backdrop-blur-md border-b border-gray-200 z-50">
                <div className="max-w-7xl mx-auto px-4 h-full flex items-center justify-between">
                    <div className="flex items-center gap-8">
                        <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                            AlgoTrader
                        </h1>

                        <div className="flex items-center gap-2">
                            <Link
                                to="/"
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/')
                                    ? 'bg-blue-50 text-blue-600'
                                    : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                Live Dashboard
                            </Link>
                            <Link
                                to="/performance"
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/performance')
                                    ? 'bg-blue-50 text-blue-600'
                                    : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                Performance
                            </Link>
                            <Link
                                to="/backtest"
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/backtest')
                                    ? 'bg-purple-50 text-purple-600'
                                    : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                📊 Backtesting
                            </Link>
                            <Link
                                to="/kite"
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/kite')
                                    ? 'bg-indigo-50 text-indigo-600'
                                    : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                🖥️ Kite Terminal
                            </Link>
                        </div>
                    </div>

                    <div className="text-xs text-gray-500 font-mono">
                        {location.pathname === '/' ? 'LIVE' : 'HISTORY'}
                    </div>
                </div>
            </nav>

            {/* Main Content Area */}
            <div className="pt-16">
                {children}
            </div>
        </div>
    );
};

export default Layout;
