
import React, { useState } from 'react';
import { apiService } from '../api';

const TokenExpiredModal = ({ isOpen, onClose }) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    if (!isOpen) return null;

    const handleGenerateToken = async () => {
        try {
            setLoading(true);
            setError(null);
            const result = await apiService.generateToken();
            if (result.success) {
                window.location.reload();
            } else {
                setError(result.message || "Automatic generation failed (PIN/TOTP not configured?). Enter a token manually below.");
                setShowManualEntry(true);
            }
        } catch (err) {
            console.error("Error generating token:", err);
            setError("Failed to generate token automatically. Enter a token manually below.");
            setShowManualEntry(true);
        } finally {
            setLoading(false);
        }
    };

    const [showManualEntry, setShowManualEntry] = useState(false);
    const [manualToken, setManualToken] = useState('');

    const handleSaveManualToken = async () => {
        if (!manualToken.trim()) return;

        try {
            setLoading(true);
            setError(null);
            const result = await apiService.saveToken(manualToken.trim());
            if (result.success) {
                setManualToken('');
                setShowManualEntry(false);
                // Close modal and force reload to refresh state
                window.location.reload();
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

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6 transform transition-all scale-100">
                <div className="text-center mb-6">
                    <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 dark:bg-red-900 mb-4">
                        <svg className="h-6 w-6 text-red-600 dark:text-red-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                        Access Token Expired
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Your Dhan access token has expired or is missing. You must regenerate it to continue trading.
                    </p>
                </div>

                {error && (
                    <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm rounded-md">
                        {error}
                    </div>
                )}

                {!showManualEntry ? (
                    <div className="flex flex-col gap-3">
                        <button
                            onClick={handleGenerateToken}
                            disabled={loading}
                            className="w-full inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {loading ? (
                                <>
                                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Generating...
                                </>
                            ) : (
                                'Regenerate Token Now'
                            )}
                        </button>

                        <button
                            onClick={() => setShowManualEntry(true)}
                            className="w-full inline-flex justify-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-600"
                        >
                            Enter Token Manually
                        </button>

                        <button
                            onClick={onClose}
                            className="w-full inline-flex justify-center px-4 py-2 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                        >
                            View Only Mode
                        </button>
                    </div>
                ) : (
                    <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-2">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Paste Access Token
                            </label>
                            <textarea
                                value={manualToken}
                                onChange={(e) => setManualToken(e.target.value)}
                                placeholder="Paste your token here..."
                                rows={3}
                                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                        </div>

                        <div className="flex gap-2">
                            <button
                                onClick={handleSaveManualToken}
                                disabled={loading || !manualToken.trim()}
                                className="flex-1 inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                {loading ? 'Saving...' : 'Save Token'}
                            </button>

                            <button
                                onClick={() => setShowManualEntry(false)}
                                className="px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-600"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TokenExpiredModal;
