"""
Rule-based "AI analysis" for a single simulated/backtested trade.
Extracted out of the (now removed) option-buying backtest engine since the
credit-spread backtest still uses it to rate trades for the dashboard.
"""
from typing import Dict


def generate_ai_analysis(trade: Dict) -> Dict:
    """
    Generate a rule-based AI analysis for a trade based on indicator values.
    Returns a structured verdict with signal strength, quality rating, and insights.
    """
    rsi = trade.get('rsi', 0) or 0
    adx = trade.get('adx', 0) or 0
    volume_ratio = trade.get('volume_ratio', 0) or 0
    price_below_vwap = trade.get('price_below_vwap', False)
    oi_above_sma = trade.get('oi_above_sma', False)
    pnl = trade.get('pnl', 0) or 0
    pnl_pct = trade.get('pnl_percent', 0) or 0
    exit_reason = trade.get('exit_reason', '') or ''

    insights = []
    score = 0  # 0-100

    # -- Trend Strength (ADX) --------------------------------------
    if adx >= 30:
        insights.append({'type': 'positive', 'icon': '💪', 'text': f'Strong trend (ADX {adx:.0f} ≥ 30) — high-conviction directional move'})
        score += 25
    elif adx >= 20:
        insights.append({'type': 'neutral', 'icon': '📊', 'text': f'Moderate trend (ADX {adx:.0f}) — trend developing but not strong'})
        score += 15
    else:
        insights.append({'type': 'warning', 'icon': '⚠️', 'text': f'Weak trend (ADX {adx:.0f} < 20) — choppy market, higher SL risk'})
        score += 0

    # -- Momentum (RSI) ----------------------------------------------
    if rsi <= 20:
        insights.append({'type': 'warning', 'icon': '🔥', 'text': f'Oversold (RSI {rsi:.0f} ≤ 20) — momentum hot but reversal risk elevated'})
        score += 10
    elif rsi <= 40:
        insights.append({'type': 'positive', 'icon': '🚀', 'text': f'Strong momentum (RSI {rsi:.0f}) — well within bearish zone'})
        score += 25
    elif rsi <= 50:
        insights.append({'type': 'neutral', 'icon': '📈', 'text': f'Moderate momentum (RSI {rsi:.0f}) — borderline entry signal'})
        score += 12
    else:
        insights.append({'type': 'negative', 'icon': '❄️', 'text': f'Weak momentum (RSI {rsi:.0f} > 50) — momentum not confirming entry'})
        score += 0

    # -- Price vs VWAP -------------------------------------------------
    if price_below_vwap:
        insights.append({'type': 'positive', 'icon': '✅', 'text': 'Price below VWAP — bearish institutional flow confirmed'})
        score += 20
    else:
        insights.append({'type': 'negative', 'icon': '❌', 'text': 'Price above VWAP — entering against institutional flow (risky)'})

    # -- Open Interest Confirmation ------------------------------------
    if oi_above_sma:
        insights.append({'type': 'positive', 'icon': '📉', 'text': 'OI above SMA — writers building positions, bearish confirmation'})
        score += 15
    else:
        insights.append({'type': 'neutral', 'icon': '🔍', 'text': 'OI below SMA — unwinding, watch for reversal'})
        score += 5

    # -- Volume Confirmation -------------------------------------------
    if volume_ratio >= 150:
        insights.append({'type': 'positive', 'icon': '🔊', 'text': f'Exceptional volume ({volume_ratio:.0f}% of SMA) — strong institutional activity'})
        score += 15
    elif volume_ratio >= 120:
        insights.append({'type': 'positive', 'icon': '📢', 'text': f'Good volume ({volume_ratio:.0f}% of SMA) — confirms breakout signal'})
        score += 10
    elif volume_ratio >= 100:
        insights.append({'type': 'neutral', 'icon': '🔉', 'text': f'Adequate volume ({volume_ratio:.0f}% of SMA) — minimum threshold met'})
        score += 5
    elif volume_ratio > 0:
        insights.append({'type': 'warning', 'icon': '🔈', 'text': f'Low volume ({volume_ratio:.0f}% of SMA) — breakout credibility questionable'})

    # -- Outcome Analysis -----------------------------------------------
    if pnl > 0:
        if 'TARGET' in exit_reason.upper() or 'PROFIT' in exit_reason.upper():
            insights.append({'type': 'positive', 'icon': '🎯', 'text': f'Target hit cleanly (+{pnl_pct:.1f}%) — strategy executed as designed'})
        else:
            insights.append({'type': 'positive', 'icon': '💰', 'text': f'Profitable exit (+{pnl_pct:.1f}%) — managed well despite non-target exit'})
    elif pnl < 0:
        if 'SL' in exit_reason.upper() or 'STOP' in exit_reason.upper():
            insights.append({'type': 'negative', 'icon': '🛑', 'text': f'Stop loss triggered ({pnl_pct:.1f}%) — pre-defined risk absorbed'})
        else:
            insights.append({'type': 'negative', 'icon': '📉', 'text': f'Loss on exit ({pnl_pct:.1f}%) — review entry timing vs indicator alignment'})

    # -- Overall Rating ---------------------------------------------
    score = min(score, 100)
    if score >= 75:
        rating = 'A'
        rating_label = 'Excellent Setup'
        rating_color = 'emerald'
    elif score >= 55:
        rating = 'B'
        rating_label = 'Good Setup'
        rating_color = 'blue'
    elif score >= 35:
        rating = 'C'
        rating_label = 'Average Setup'
        rating_color = 'amber'
    else:
        rating = 'D'
        rating_label = 'Weak Setup'
        rating_color = 'red'

    # -- Summary sentence ---------------------------------------------
    summary_parts = []
    if adx >= 25:
        summary_parts.append('strong trend')
    if rsi <= 40:
        summary_parts.append('good momentum')
    if price_below_vwap:
        summary_parts.append('bearish institutional flow')
    if volume_ratio >= 120:
        summary_parts.append('volume confirmation')

    if summary_parts:
        summary = f"Entry had {', '.join(summary_parts)}. " + (
            f"{'Trade paid off well.' if pnl > 0 else 'Despite setup quality, trade hit SL — consider market context.'}"
        )
    else:
        summary = "Entry lacked multiple confirmations. " + (
            'Fortunate profitable outcome.' if pnl > 0 else 'Expected outcome given weak setup.'
        )

    return {
        'score': score,
        'rating': rating,
        'rating_label': rating_label,
        'rating_color': rating_color,
        'summary': summary,
        'insights': insights,
    }
