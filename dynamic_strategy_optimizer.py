#!/usr/bin/env python3
"""
Dynamic Staking Strategy Optimizer for Bittensor Subnet 88
Real-time adaptive strategy that rebalances based on market conditions

Features:
- Real-time performance analysis via API calls
- Dynamic allocation adjustment
- Risk-based position sizing
- Scoring mechanism optimization
- Automatic rebalancing triggers
"""

import os
import sys
import json
import time
import sqlite3
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import Sταking.core.api as api
from Sταking.core.const import *

class DynamicStrategyOptimizer:
    def __init__(self, lookback_days=30, rebalance_threshold=0.05, max_allocation=0.25):
        """
        Initialize the dynamic strategy optimizer
        
        Args:
            lookback_days: Days of historical data to analyze
            rebalance_threshold: Minimum change to trigger rebalancing
            max_allocation: Maximum allocation to any single subnet
        """
        self.lookback_days = lookback_days
        self.rebalance_threshold = rebalance_threshold
        self.max_allocation = max_allocation
        self.min_allocation = 0.02  # Minimum 2% allocation
        self.cash_allocation = 0.05  # Emergency cash reserve
        
        # Performance tracking
        self.performance_history = {}
        self.risk_metrics = {}
        self.last_rebalance = None
        
        # Strategy parameters
        self.target_sharpe = 0.1
        self.max_drawdown_limit = 0.8  # 80% max drawdown tolerance
        self.min_subnets = 5  # Minimum diversification
        self.max_subnets = 10  # Maximum complexity
        
    def fetch_market_data(self):
        """Fetch latest market data from database and API"""
        try:
            # Get database connection
            db_path = 'Sταking/core/db/daily.db'
            conn = sqlite3.connect(db_path)
            
            # Calculate date range
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime('%Y-%m-%d')
            
            # Fetch recent data
            query = f"""
            SELECT netuid, date, price, emission, weight, tao_in, alpha_in
            FROM bndaily 
            WHERE date >= '{start_date}' AND date <= '{end_date}'
            ORDER BY netuid, date
            """
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            print(f"Fetched {len(df)} records for {len(df['netuid'].unique())} subnets")
            return df
            
        except Exception as e:
            print(f"Error fetching market data: {e}")
            return pd.DataFrame()
    
    def calculate_performance_metrics(self, df):
        """Calculate comprehensive performance metrics for each subnet"""
        metrics = {}
        
        for netuid in df['netuid'].unique():
            subnet_data = df[df['netuid'] == netuid].copy()
            
            if len(subnet_data) < 5:  # Need minimum data points
                continue
                
            subnet_data = subnet_data.sort_values('date')
            prices = subnet_data['price'].values
            
            # Skip if no price data
            if len(prices) == 0 or np.all(prices == 0):
                continue
            
            # Calculate returns
            returns = np.diff(prices) / prices[:-1]
            returns = returns[np.isfinite(returns)]  # Remove inf/nan
            
            if len(returns) == 0:
                continue
            
            # Performance metrics
            total_return = (prices[-1] - prices[0]) / prices[0] if prices[0] > 0 else 0
            volatility = np.std(returns) if len(returns) > 1 else 0
            sharpe = np.mean(returns) / volatility if volatility > 0 else 0
            
            # Risk metrics
            cumulative = np.cumprod(1 + returns)
            peak = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - peak) / peak
            max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
            
            # Scoring-specific metrics
            positive_days = np.sum(returns > 0)
            total_days = len(returns)
            win_rate = positive_days / total_days if total_days > 0 else 0
            
            avg_win = np.mean(returns[returns > 0]) if positive_days > 0 else 0
            avg_loss = np.mean(returns[returns < 0]) if (total_days - positive_days) > 0 else 0
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            # Kelly criterion
            kelly = win_rate - (1 - win_rate) / profit_factor if profit_factor > 0 else 0
            
            # Emission and weight data
            avg_emission = subnet_data['emission'].mean()
            avg_weight = subnet_data['weight'].mean()
            
            # Composite score (similar to subnet scoring)
            mar = total_return / max(abs(max_drawdown), 0.01)  # MAR ratio
            lsr = np.sum(returns) / np.sum(np.abs(returns)) if np.sum(np.abs(returns)) > 0 else 0
            odds = 50 + kelly / 2 * 100
            daily_return = (1 + total_return) ** (1/total_days) - 1 if total_days > 0 else 0
            
            composite_score = mar * lsr * odds * daily_return * 100
            
            metrics[netuid] = {
                'total_return': total_return,
                'volatility': volatility,
                'sharpe': sharpe,
                'max_drawdown': abs(max_drawdown),
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'kelly': kelly,
                'mar': mar,
                'lsr': lsr,
                'odds': odds,
                'daily_return': daily_return,
                'composite_score': composite_score,
                'emission': avg_emission,
                'weight': avg_weight,
                'current_price': prices[-1],
                'data_points': len(returns)
            }
        
        return metrics
    
    def rank_subnets(self, metrics):
        """Rank subnets based on multiple criteria"""
        if not metrics:
            return []
        
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(metrics).T
        
        # Filter out problematic subnets
        df = df[df['data_points'] >= 5]  # Minimum data requirement
        df = df[df['max_drawdown'] <= self.max_drawdown_limit]  # Risk limit
        df = df[df['volatility'] < 5.0]  # Extreme volatility filter
        
        # Scoring weights (tuned for the subnet's scoring mechanism)
        weights = {
            'composite_score': 0.30,  # Primary scoring metric
            'sharpe': 0.25,           # Risk-adjusted return
            'mar': 0.20,              # Return/risk ratio
            'win_rate': 0.15,         # Consistency
            'emission': 0.10          # Steady income
        }
        
        # Normalize metrics (0-1 scale)
        for metric in weights.keys():
            if metric in df.columns:
                max_val = df[metric].max()
                min_val = df[metric].min()
                if max_val > min_val:
                    df[f'{metric}_norm'] = (df[metric] - min_val) / (max_val - min_val)
                else:
                    df[f'{metric}_norm'] = 0.5
        
        # Calculate weighted score
        df['weighted_score'] = 0
        for metric, weight in weights.items():
            if f'{metric}_norm' in df.columns:
                df['weighted_score'] += df[f'{metric}_norm'] * weight
        
        # Sort by weighted score
        df = df.sort_values('weighted_score', ascending=False)
        
        return df.index.tolist()
    
    def calculate_optimal_allocation(self, ranked_subnets, metrics):
        """Calculate optimal allocation using risk-parity and momentum"""
        if not ranked_subnets or not metrics:
            return {}
        
        # Select top subnets
        selected_subnets = ranked_subnets[:self.max_subnets]
        
        # Risk-parity allocation
        allocations = {}
        total_risk_budget = 1.0 - self.cash_allocation
        
        # Calculate inverse volatility weights
        inv_vol_weights = {}
        total_inv_vol = 0
        
        for netuid in selected_subnets:
            if netuid in metrics:
                vol = max(metrics[netuid]['volatility'], 0.01)  # Minimum volatility
                inv_vol = 1.0 / vol
                inv_vol_weights[netuid] = inv_vol
                total_inv_vol += inv_vol
        
        # Normalize and apply constraints
        for netuid in selected_subnets:
            if netuid in inv_vol_weights and total_inv_vol > 0:
                base_allocation = (inv_vol_weights[netuid] / total_inv_vol) * total_risk_budget
                
                # Apply min/max constraints
                allocation = max(self.min_allocation, min(self.max_allocation, base_allocation))
                allocations[netuid] = allocation
        
        # Normalize to ensure sum <= 1.0 - cash_allocation
        total_allocated = sum(allocations.values())
        if total_allocated > total_risk_budget:
            scale_factor = total_risk_budget / total_allocated
            allocations = {k: v * scale_factor for k, v in allocations.items()}
        
        # Add cash if needed
        remaining = 1.0 - sum(allocations.values())
        if remaining > 0.01:  # If significant cash remaining
            allocations[0] = remaining
        
        return allocations
    
    def should_rebalance(self, current_strategy, new_strategy):
        """Determine if rebalancing is needed"""
        if not current_strategy or not new_strategy:
            return True
        
        # Check if enough time has passed
        if self.last_rebalance:
            hours_since_rebalance = (datetime.now() - self.last_rebalance).total_seconds() / 3600
            if hours_since_rebalance < 6:  # Minimum 6 hours between rebalances
                return False
        
        # Calculate allocation differences
        all_subnets = set(current_strategy.keys()) | set(new_strategy.keys())
        max_diff = 0
        
        for subnet in all_subnets:
            current_alloc = current_strategy.get(subnet, 0)
            new_alloc = new_strategy.get(subnet, 0)
            diff = abs(new_alloc - current_alloc)
            max_diff = max(max_diff, diff)
        
        return max_diff >= self.rebalance_threshold
    
    def generate_strategy(self):
        """Generate optimized strategy based on current market conditions"""
        print("=== DYNAMIC STRATEGY OPTIMIZATION ===")
        print(f"Timestamp: {datetime.now()}")
        
        # Fetch and analyze market data
        df = self.fetch_market_data()
        if df.empty:
            print("No market data available")
            return {}
        
        # Calculate performance metrics
        print("Calculating performance metrics...")
        metrics = self.calculate_performance_metrics(df)
        
        if not metrics:
            print("No valid metrics calculated")
            return {}
        
        print(f"Analyzed {len(metrics)} subnets")
        
        # Rank subnets
        ranked_subnets = self.rank_subnets(metrics)
        print(f"Top 10 ranked subnets: {ranked_subnets[:10]}")
        
        # Calculate optimal allocation
        strategy = self.calculate_optimal_allocation(ranked_subnets, metrics)
        
        # Display strategy
        print("\n=== OPTIMIZED STRATEGY ===")
        total_allocation = 0
        for netuid, allocation in sorted(strategy.items(), key=lambda x: x[1], reverse=True):
            if allocation > 0.01:  # Only show significant allocations
                metric = metrics.get(netuid, {})
                print(f"Subnet {netuid:3d}: {allocation:6.1%} | "
                      f"Score: {metric.get('composite_score', 0):8.1f} | "
                      f"Sharpe: {metric.get('sharpe', 0):5.2f} | "
                      f"Return: {metric.get('total_return', 0):6.1%}")
                total_allocation += allocation
        
        print(f"\nTotal Allocation: {total_allocation:.1%}")
        
        return strategy
    
    def save_strategy_to_file(self, strategy, hotkey_ss58):
        """Save strategy to the appropriate file for the miner"""
        if not strategy:
            print("No strategy to save")
            return False
        
        strategy_file = f"Sταking/strat/{hotkey_ss58}"
        
        try:
            # Format strategy as Python dict
            strategy_dict = {int(k): float(v) for k, v in strategy.items() if v > 0.001}
            
            with open(strategy_file, 'w') as f:
                f.write("{\n")
                for netuid, allocation in sorted(strategy_dict.items(), key=lambda x: x[1], reverse=True):
                    f.write(f"    {netuid}: {allocation:.4f},\n")
                f.write("}\n")
            
            print(f"Strategy saved to {strategy_file}")
            self.last_rebalance = datetime.now()
            return True
            
        except Exception as e:
            print(f"Error saving strategy: {e}")
            return False

def main():
    """Main execution function"""
    if len(sys.argv) < 2:
        print("Usage: python dynamic_strategy_optimizer.py <hotkey_ss58>")
        print("Example: python dynamic_strategy_optimizer.py 5F4tQyWrhfGVcNhoqeiNsR6KjD4wMZ2kfhLj4oHYuyHbZAc3")
        return
    
    hotkey_ss58 = sys.argv[1]
    
    # Initialize optimizer
    optimizer = DynamicStrategyOptimizer(
        lookback_days=30,
        rebalance_threshold=0.05,  # 5% change threshold
        max_allocation=0.25        # 25% max per subnet
    )
    
    # Load current strategy if exists
    current_strategy = {}
    strategy_file = f"Sταking/strat/{hotkey_ss58}"
    if os.path.exists(strategy_file):
        try:
            with open(strategy_file, 'r') as f:
                current_strategy = eval(f.read())
            print(f"Loaded current strategy: {current_strategy}")
        except:
            print("Could not load current strategy")
    
    # Generate new strategy
    new_strategy = optimizer.generate_strategy()
    
    # Check if rebalancing is needed
    if optimizer.should_rebalance(current_strategy, new_strategy):
        print("\n=== REBALANCING TRIGGERED ===")
        optimizer.save_strategy_to_file(new_strategy, hotkey_ss58)
    else:
        print("\n=== NO REBALANCING NEEDED ===")
        print("Current strategy is still optimal")

if __name__ == "__main__":
    main()
