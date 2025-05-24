#!/usr/bin/env python3
"""
Setup and Testing Script for Enhanced Bittensor Staking Miner
Comprehensive setup, testing, and deployment automation

Features:
- Environment validation
- Strategy testing and backtesting
- Performance monitoring
- Deployment automation
"""

import os
import sys
import time
import subprocess
import pandas as pd
from datetime import datetime
from dynamic_strategy_optimizer import DynamicStrategyOptimizer

def check_environment():
    """Check if the environment is properly set up"""
    print("=== ENVIRONMENT CHECK ===")
    
    # Check Python version
    python_version = sys.version_info
    print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version.major < 3 or python_version.minor < 8:
        print("❌ Python 3.8+ required")
        return False
    else:
        print("✅ Python version OK")
    
    # Check required packages
    required_packages = [
        'bittensor', 'pandas', 'numpy', 'requests', 'sqlalchemy'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"Missing packages: {missing_packages}")
        return False
    
    # Check Staking module
    try:
        import Sταking
        print("✅ Staking module available")
    except ImportError:
        print("❌ Staking module not found - run 'pip install -e .' first")
        return False
    
    # Check database
    db_path = 'Sταking/core/db/daily.db'
    if os.path.exists(db_path) and os.path.getsize(db_path) > 1000:
        print("✅ Market database available")
    else:
        print("❌ Market database missing or empty")
        return False
    
    print("✅ Environment check passed!")
    return True

def test_strategy_optimizer():
    """Test the dynamic strategy optimizer"""
    print("\n=== TESTING STRATEGY OPTIMIZER ===")
    
    try:
        # Initialize optimizer
        optimizer = DynamicStrategyOptimizer(
            lookback_days=30,
            rebalance_threshold=0.05,
            max_allocation=0.25
        )
        
        print("✅ Optimizer initialized")
        
        # Test market data fetching
        df = optimizer.fetch_market_data()
        if df.empty:
            print("❌ No market data fetched")
            return False
        
        print(f"✅ Fetched {len(df)} market data records")
        print(f"   Available subnets: {len(df['netuid'].unique())}")
        print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
        
        # Test performance calculation
        metrics = optimizer.calculate_performance_metrics(df)
        if not metrics:
            print("❌ No performance metrics calculated")
            return False
        
        print(f"✅ Calculated metrics for {len(metrics)} subnets")
        
        # Test strategy generation
        strategy = optimizer.generate_strategy()
        if not strategy:
            print("❌ No strategy generated")
            return False
        
        print("✅ Strategy generated successfully")
        print(f"   Allocated subnets: {len(strategy)}")
        print(f"   Total allocation: {sum(strategy.values()):.1%}")
        
        # Display top allocations
        sorted_strategy = sorted(strategy.items(), key=lambda x: x[1], reverse=True)
        print("   Top allocations:")
        for netuid, allocation in sorted_strategy[:5]:
            if allocation > 0.01:
                print(f"     Subnet {netuid}: {allocation:.1%}")
        
        return True
        
    except Exception as e:
        print(f"❌ Strategy optimizer test failed: {e}")
        return False

def run_backtest():
    """Run a backtest of the strategy"""
    print("\n=== RUNNING BACKTEST ===")
    
    try:
        # Create a test strategy file
        test_strategy_csv = "test_strategy.csv"
        
        # Generate test strategy using optimizer
        optimizer = DynamicStrategyOptimizer()
        strategy = optimizer.generate_strategy()
        
        if not strategy:
            print("❌ Could not generate strategy for backtest")
            return False
        
        # Create CSV for backtesting
        with open(test_strategy_csv, 'w') as f:
            f.write("uid,date,time,block,init,fund,strat,notes\n")
            
            # Create strategy entry for backtesting (use recent date for better results)
            # Convert numpy types to regular Python types to avoid parsing issues
            clean_strategy = {}
            for k, v in strategy.items():
                # Convert numpy types to regular Python types
                clean_k = int(k) if hasattr(k, 'item') else int(k)
                clean_v = float(v) if hasattr(v, 'item') else float(v)
                clean_strategy[clean_k] = clean_v
            
            strategy_str = str(clean_strategy).replace(' ', '')
            f.write(f"999,2025-05-01,00:00:01,5600000,1,1000,\"{strategy_str}\",optimized_strategy\n")
        
        print(f"✅ Created test strategy: {strategy}")
        
        # Run simulation
        print("Running backtest simulation...")
        cmd = f"python3 -m Sταking.core.simst {test_strategy_csv}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Backtest completed successfully")
            print("\nBacktest Results:")
            print(result.stdout)
            
            # Parse results for key metrics
            lines = result.stdout.split('\n')
            for line in lines:
                if 'rolling window days:' in line:
                    print(f"   {line.strip()}")
                elif '999' in line and 'uid' not in line:
                    parts = line.split()
                    if len(parts) >= 6:
                        print(f"   Score: {parts[5]}")
                        print(f"   APY: {parts[6]}")
                        print(f"   Risk: {parts[9]}")
        else:
            print(f"❌ Backtest failed: {result.stderr}")
            return False
        
        # Cleanup
        if os.path.exists(test_strategy_csv):
            os.remove(test_strategy_csv)
        
        return True
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        return False

def create_example_strategy(hotkey_ss58):
    """Create an example strategy file"""
    print(f"\n=== CREATING EXAMPLE STRATEGY FOR {hotkey_ss58} ===")
    
    try:
        optimizer = DynamicStrategyOptimizer()
        strategy = optimizer.generate_strategy()
        
        if strategy:
            success = optimizer.save_strategy_to_file(strategy, hotkey_ss58)
            if success:
                print("✅ Example strategy created successfully")
                return True
        
        print("❌ Failed to create example strategy")
        return False
        
    except Exception as e:
        print(f"❌ Strategy creation failed: {e}")
        return False

def show_deployment_instructions():
    """Show deployment instructions"""
    print("\n=== DEPLOYMENT INSTRUCTIONS ===")
    print("""
🚀 ENHANCED MINER DEPLOYMENT

1. USING THE ENHANCED MINER:
   pm2 start enhanced_miner.py \\
       --name staking-enhanced-miner -- \\
       --wallet.name {coldkey} \\
       --wallet.hotkey {hotkey} \\
       --netuid 88

2. MANUAL STRATEGY OPTIMIZATION:
   python3 dynamic_strategy_optimizer.py {hotkey_ss58}

3. MONITORING:
   pm2 logs staking-enhanced-miner
   pm2 monit

4. FEATURES OF ENHANCED MINER:
   ✅ Automatic strategy optimization every hour
   ✅ Real-time performance monitoring
   ✅ Emergency rebalancing on poor performance
   ✅ Risk-adjusted allocation using modern portfolio theory
   ✅ Dynamic adaptation to market conditions

5. CONFIGURATION OPTIONS:
   - lookback_days: Historical data window (default: 30)
   - rebalance_threshold: Minimum change to trigger rebalancing (default: 5%)
   - max_allocation: Maximum allocation per subnet (default: 25%)
   - optimization_interval: Time between optimizations (default: 1 hour)

6. STRATEGY FILES:
   - Location: Sταking/strat/{hotkey_ss58}
   - Format: Python dictionary with subnet allocations
   - Auto-updated by enhanced miner

7. PERFORMANCE MONITORING:
   - Check dashboard: https://stakingalpha.com
   - Monitor logs for optimization events
   - Emergency rebalancing triggers on >15% losses

⚠️  IMPORTANT NOTES:
   - Ensure wallet is properly configured
   - Monitor initial performance closely
   - Strategy adapts to market conditions automatically
   - Keep system updated for latest optimizations
""")

def main():
    """Main setup and testing function"""
    print("🔧 ENHANCED BITTENSOR STAKING MINER SETUP")
    print("=" * 50)
    
    # Environment check
    if not check_environment():
        print("\n❌ Environment check failed. Please fix issues and try again.")
        return False
    
    # Test strategy optimizer
    if not test_strategy_optimizer():
        print("\n❌ Strategy optimizer test failed.")
        return False
    
    # Run backtest
    if not run_backtest():
        print("\n❌ Backtest failed.")
        return False
    
    # Get hotkey for example strategy
    hotkey_ss58 = input("\n📝 Enter your hotkey SS58 address (or press Enter to skip): ").strip()
    
    if hotkey_ss58:
        create_example_strategy(hotkey_ss58)
    
    # Show deployment instructions
    show_deployment_instructions()
    
    print("\n🎉 SETUP COMPLETED SUCCESSFULLY!")
    print("Your enhanced miner is ready for deployment.")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
