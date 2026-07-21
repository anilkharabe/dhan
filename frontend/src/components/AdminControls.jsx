import React, { useState } from 'react';
import apiService from '../api';

const AdminControls = ({ onRefresh }) => {
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);

    const handleResetPositions = async () => {
        if (!window.confirm("Are you sure you want to CLOSE ALL open positions? This will mark them as sold in the database.")) {
            return;
        }

        setLoading(true);
        setMessage(null);
        try {
            const response = await apiService.post('/admin/reset-positions');
            setMessage({ type: 'success', text: response.data.message });
            if (onRefresh) onRefresh();
        } catch (error) {
            console.error("Error resetting positions:", error);
            setMessage({ type: 'error', text: 'Failed to reset positions' });
        } finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    const handleClearToday = async () => {
        if (!window.confirm("Are you sure you want to DELETE ALL data for today? This cannot be undone.")) {
            return;
        }

        setLoading(true);
        setMessage(null);
        try {
            const response = await apiService.post('/admin/clear-today');
            setMessage({ type: 'success', text: response.data.message });
            if (onRefresh) onRefresh();
        } catch (error) {
            console.error("Error clearing today's data:", error);
            setMessage({ type: 'error', text: 'Failed to clear data' });
        } finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    return (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-sm font-semibold text-gray-700">System Controls</h3>
                    <p className="text-xs text-gray-500">Manual administrative actions</p>
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={handleResetPositions}
                        disabled={loading}
                        className="px-3 py-1.5 bg-amber-50 text-amber-600 hover:bg-amber-100 border border-amber-200 rounded text-xs font-medium transition-colors disabled:opacity-50"
                    >
                        Close All Positions
                    </button>

                    <button
                        onClick={handleClearToday}
                        disabled={loading}
                        className="px-3 py-1.5 bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 rounded text-xs font-medium transition-colors disabled:opacity-50"
                    >
                        Clear Today's Data
                    </button>
                </div>
            </div>

            {message && (
                <div className={`mt-2 text-xs px-2 py-1 rounded ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                    }`}>
                    {message.text}
                </div>
            )}
        </div>
    );
};

export default AdminControls;
