
import React, { useState, useEffect } from 'react';
import { apiService } from '../api';

const TokenStatus = () => {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showManualEntry, setShowManualEntry] = useState(false);
    const [manualToken, setManualToken] = useState('');

    const fetchStatus = async () => {
        try {
            const data = await apiService.getTokenStatus();
            setStatus(data);
            setError(null);
        } catch (err) {
            console.error("Error fetching token status:", err);
            setError("Failed to check token status");
        }
    };

    useEffect(() => {
        fetchStatus();
        // Refresh status every minute
        const interval = setInterval(fetchStatus, 60000);
        return () => clearInterval(interval);
    }, []);

    const handleGenerateToken = async () => {
        try {
            setLoading(true);
            setError(null);
            const result = await apiService.generateToken();
            if (result.success) {
                fetchStatus(); // Refresh status immediately
            } else {
                setError(result.message || "Automatic generation failed (PIN/TOTP not configured?). Use manual entry below.");
                setShowManualEntry(true);
            }
        } catch (err) {
            console.error("Error generating token:", err);
            setError("Failed to generate token automatically. Use manual entry below.");
            setShowManualEntry(true);
        } finally {
            setLoading(false);
        }
    };

    const handleSaveManualToken = async () => {
        if (!manualToken.trim()) {
            setError("Please enter a token");
            return;
        }

        try {
            setLoading(true);
            setError(null);
            const result = await apiService.saveToken(manualToken.trim());
            if (result.success) {
                setManualToken('');
                setShowManualEntry(false);
                fetchStatus(); // Refresh status immediately
            } else {
                setError(result.message || "Failed to save token");
            }
        } catch (err) {
            console.error("Error saving token:", err);
            setError("Failed to save token");
        } finally {
            setLoading(false);
        }
    };

    if (!status && !showManualEntry) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-4 flex items-center justify-between animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setShowManualEntry(true)}
                        className="px-3 py-1 text-sm font-medium text-blue-600 hover:text-blue-800 transition-colors"
                    >
                        Enter Manually
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-4">
                    {status ? (
                        <>
                            <div className={`w-3 h-3 rounded-full ${status.is_valid ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`}></div>
                            <div>
                                <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
                                    Access Token:
                                    <span className={status.is_valid ? 'text-green-600' : 'text-red-600 font-bold'}>
                                        {status.is_valid ? 'VALID' : 'EXPIRED/INVALID'}
                                    </span>
                                    {status.message && (
                                        <span className="text-[10px] bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded text-gray-500">
                                            {status.message}
                                        </span>
                                    )}
                                </h3>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    Last Generated: {status.generated_at || 'Unknown'} ({status.age_hours}h ago)
                                </p>
                            </div>
                        </>
                    ) : (
                        <div className="animate-pulse">
                            <div className="h-4 bg-gray-200 rounded w-32 mb-2"></div>
                            <div className="h-3 bg-gray-200 rounded w-24"></div>
                        </div>
                    )}
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={() => setShowManualEntry(!showManualEntry)}
                        className="px-3 py-1 text-sm font-medium text-blue-600 hover:text-blue-800 transition-colors"
                    >
                        {showManualEntry ? 'Cancel Manual Entry' : 'Enter Manually'}
                    </button>

                    {!showManualEntry && (
                        <button
                            onClick={handleGenerateToken}
                            disabled={loading}
                            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                            {loading ? 'Generating...' : 'Regenerate Token'}
                        </button>
                    )}
                </div>
            </div>

            {showManualEntry && (
                <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200 animate-in fade-in slide-in-from-top-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                        Paste Access Token
                    </label>
                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={manualToken}
                            onChange={(e) => setManualToken(e.target.value)}
                            placeholder="eyJraW..."
                            className="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                        />
                        <button
                            onClick={handleSaveManualToken}
                            disabled={loading || !manualToken.trim()}
                            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
                        >
                            {loading ? 'Saving...' : 'Save Token'}
                        </button>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                        Get this token from the Dhan web portal: My Profile → DhanHQ Trading APIs → Generate Token.
                    </p>
                </div>
            )}

            {error && (
                <div className="text-red-500 text-xs mt-2">
                    {error}
                </div>
            )}
        </div>
    );
};

export default TokenStatus;
