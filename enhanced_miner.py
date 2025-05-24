#!/usr/bin/env python3
"""
Enhanced Miner for Bittensor Subnet 88 (Staking)
Integrates dynamic strategy optimization with the base miner functionality

Features:
- Automatic strategy optimization based on real-time market data
- Intelligent rebalancing triggers
- Risk management and performance monitoring
- Seamless integration with existing miner infrastructure
"""

import time
import typing
import os
import sys
import subprocess
import pandas as pd
import bittensor as bt
import Sταking.core.api as api
import Sταking.core.etc as etc
from dynamic_strategy_optimizer import DynamicStrategyOptimizer

# Bittensor Miner Template:
import neurons.template as template
from neurons.template.base.miner import BaseMinerNeuron


class EnhancedMiner(BaseMinerNeuron):
    """
    Enhanced miner with dynamic strategy optimization capabilities
    """

    def __init__(self, config=None):
        super(EnhancedMiner, self).__init__(config=config)
        
        # Initialize strategy optimizer
        self.strategy_optimizer = DynamicStrategyOptimizer(
            lookback_days=30,
            rebalance_threshold=0.05,  # 5% change threshold
            max_allocation=0.25        # 25% max per subnet
        )
        
        # Strategy management
        self.last_optimization = None
        self.optimization_interval = 3600  # 1 hour between optimizations
        self.emergency_rebalance_threshold = 0.15  # 15% for emergency rebalancing
        
        # Performance tracking
        self.performance_log = []
        self.strategy_history = []
        
        bt.logging.info("Enhanced miner initialized with dynamic strategy optimization")

    async def forward(
        self, synapse: template.protocol.Strategy
    ) -> template.protocol.Strategy:
        """
        Enhanced forward function that handles strategy requests
        """
        # The original template implementation
        synapse.strategy_output = synapse.strategy_input * 2
        return synapse

    def optimize_strategy(self, force_rebalance=False):
        """
        Run strategy optimization and update strategy file if needed
        """
        try:
            bt.logging.info("Running strategy optimization...")
            
            # Get current hotkey
            ss58 = self.wallet.hotkey.ss58_address
            
            # Load current strategy
            current_strategy = {}
            strategy_file = f"Sταking/strat/{ss58}"
            
            if os.path.exists(strategy_file):
                try:
                    with open(strategy_file, 'r') as f:
                        current_strategy = eval(f.read())
                    bt.logging.info(f"Current strategy: {current_strategy}")
                except Exception as e:
                    bt.logging.warning(f"Could not load current strategy: {e}")
            
            # Generate new optimized strategy
            new_strategy = self.strategy_optimizer.generate_strategy()
            
            if not new_strategy:
                bt.logging.warning("No strategy generated")
                return False
            
            # Check if rebalancing is needed
            should_rebalance = force_rebalance or self.strategy_optimizer.should_rebalance(
                current_strategy, new_strategy
            )
            
            if should_rebalance:
                bt.logging.info("Rebalancing triggered - updating strategy")
                
                # Save new strategy
                success = self.strategy_optimizer.save_strategy_to_file(new_strategy, ss58)
                
                if success:
                    # Log the change
                    self.strategy_history.append({
                        'timestamp': time.time(),
                        'old_strategy': current_strategy,
                        'new_strategy': new_strategy,
                        'reason': 'forced' if force_rebalance else 'automatic'
                    })
                    
                    bt.logging.success(f"Strategy updated successfully: {new_strategy}")
                    self.last_optimization = time.time()
                    return True
                else:
                    bt.logging.error("Failed to save strategy")
                    return False
            else:
                bt.logging.info("No rebalancing needed - strategy is optimal")
                self.last_optimization = time.time()
                return False
                
        except Exception as e:
            bt.logging.error(f"Strategy optimization failed: {e}")
            return False

    def monitor_performance(self):
        """
        Monitor current strategy performance and trigger emergency rebalancing if needed
        """
        try:
            # Fetch recent PnL data
            pl = api.pnl()
            if len(pl) == 0:
                return
            
            # Get our miner's recent performance
            ss58 = self.wallet.hotkey.ss58_address
            our_data = pl[pl['hotkey'] == ss58] if 'hotkey' in pl.columns else pd.DataFrame()
            
            if len(our_data) > 0:
                # Calculate recent performance metrics
                recent_data = our_data.tail(7)  # Last 7 days
                
                if len(recent_data) > 1:
                    recent_return = (recent_data['swap_close'].iloc[-1] - recent_data['swap_close'].iloc[0]) / recent_data['swap_close'].iloc[0]
                    
                    # Log performance
                    self.performance_log.append({
                        'timestamp': time.time(),
                        'return_7d': recent_return,
                        'current_value': recent_data['swap_close'].iloc[-1]
                    })
                    
                    # Keep only last 30 entries
                    if len(self.performance_log) > 30:
                        self.performance_log = self.performance_log[-30:]
                    
                    # Check for emergency rebalancing
                    if recent_return < -self.emergency_rebalance_threshold:
                        bt.logging.warning(f"Poor performance detected: {recent_return:.2%} - triggering emergency rebalancing")
                        self.optimize_strategy(force_rebalance=True)
                        
        except Exception as e:
            bt.logging.error(f"Performance monitoring failed: {e}")

    def should_optimize(self):
        """
        Determine if strategy optimization should run
        """
        if self.last_optimization is None:
            return True
        
        time_since_last = time.time() - self.last_optimization
        return time_since_last >= self.optimization_interval

    async def blacklist(
        self, synapse: template.protocol.Strategy
    ) -> typing.Tuple[bool, str]:
        """
        Enhanced blacklist function with additional security measures
        """
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

        # Get UID of the sender
        try:
            uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        except ValueError:
            bt.logging.trace(f"Blacklisting unregistered hotkey {synapse.dendrite.hotkey}")
            return True, "Unrecognized hotkey"

        # Check if sender is registered
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            bt.logging.trace(f"Blacklisting unregistered hotkey {synapse.dendrite.hotkey}")
            return True, "Unrecognized hotkey"

        # Check validator permit if required
        if self.config.blacklist.force_validator_permit:
            if not self.metagraph.validator_permit[uid]:
                bt.logging.warning(f"Blacklisting non-validator hotkey {synapse.dendrite.hotkey}")
                return True, "Non-validator hotkey"

        bt.logging.trace(f"Not blacklisting recognized hotkey {synapse.dendrite.hotkey}")
        return False, "Hotkey recognized!"

    async def priority(self, synapse: template.protocol.Strategy) -> float:
        """
        Enhanced priority function
        """
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return 0.0

        try:
            caller_uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
            priority = float(self.metagraph.S[caller_uid])
            bt.logging.trace(f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}")
            return priority
        except ValueError:
            bt.logging.warning(f"Could not find UID for hotkey {synapse.dendrite.hotkey}")
            return 0.0


def run_enhanced_miner():
    """
    Main function to run the enhanced miner
    """
    bt.logging.enable_info()
    
    with EnhancedMiner() as miner:
        ss58 = miner.wallet.hotkey.ss58_address
        step = 0
        
        bt.logging.info(f"Enhanced miner starting for hotkey: {ss58}")
        
        # Initial strategy optimization
        bt.logging.info("Running initial strategy optimization...")
        miner.optimize_strategy(force_rebalance=True)
        
        while True:
            try:
                # Check if strategy file is new and needs submission
                if etc.isnew(ss58):
                    bt.logging.info("New strategy detected - submitting to API")
                    api.rev(ss58)
                    time.sleep(10)
                
                # Regular logging
                if step % 10 == 0:
                    bt.logging.info(f"Enhanced miner running... {time.time()}")
                
                # Strategy optimization check (every hour)
                if step % 3600 == 0 and miner.should_optimize():
                    bt.logging.info("Running scheduled strategy optimization")
                    miner.optimize_strategy()
                
                # Performance monitoring (every 10 minutes)
                if step % 600 == 0:
                    miner.monitor_performance()
                
                # Update check (every hour)
                if step % 3600 == 0:
                    try:
                        err = etc.update()
                        if err == 0:
                            bt.logging.info('Update available - restarting...')
                            exit()  # restart with pm2
                    except Exception as e:
                        bt.logging.warning(f"Update check failed: {e}")
                
                time.sleep(1)
                step += 1
                
            except KeyboardInterrupt:
                bt.logging.info("Received interrupt signal - shutting down gracefully")
                break
            except Exception as e:
                bt.logging.error(f"Unexpected error in main loop: {e}")
                time.sleep(10)  # Wait before continuing


if __name__ == "__main__":
    run_enhanced_miner()
