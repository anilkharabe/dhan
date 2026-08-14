import { Link, useLocation } from 'react-router-dom';

const Layout = ({ children }) => {
    const location = useLocation();
    const isActive = (path) => location.pathname === path;

    return (
        <div className="min-h-screen bg-slate-50">
            {/* Navigation Bar */}
            <nav className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 z-50">
                <div className="max-w-[1440px] mx-auto px-6 h-full flex items-center justify-between">
                    <div className="flex items-center gap-8">
                        <h1 className="text-base font-bold text-gray-900 tracking-tight">
                            AlgoTrader
                        </h1>

                        <div className="flex items-center gap-1">
                            <Link
                                to="/"
                                className={`px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${isActive('/')
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                                    }`}
                            >
                                Dashboard
                            </Link>
                            <Link
                                to="/performance"
                                className={`px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${isActive('/performance')
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                                    }`}
                            >
                                Performance
                            </Link>
                            <Link
                                to="/backtest"
                                className={`px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${isActive('/backtest')
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                                    }`}
                            >
                                Backtesting
                            </Link>
                            <Link
                                to="/scanner"
                                className={`px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${isActive('/scanner')
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                                    }`}
                            >
                                Scanner
                            </Link>
                        </div>
                    </div>

                    <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-gray-400">
                        <span className={`w-1.5 h-1.5 rounded-full ${location.pathname === '/' ? 'bg-emerald-500' : 'bg-gray-300'}`}></span>
                        {location.pathname === '/' ? 'LIVE' : 'HISTORY'}
                    </div>
                </div>
            </nav>

            {/* Main Content Area */}
            <div className="pt-14">
                <div className="max-w-[1440px] mx-auto px-6 py-6">
                    {children}
                </div>
            </div>
        </div>
    );
};

export default Layout;
