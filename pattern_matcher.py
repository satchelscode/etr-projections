"""
Historical Pattern Matcher
Uses actual ETR projection patterns from similar injury situations
"""

import json
import os
import pandas as pd
import numpy as np

class HistoricalPatternMatcher:
    def __init__(self, patterns_file='models/historical_patterns.json'):
        self.patterns = self.load_patterns(patterns_file)
    
    def load_patterns(self, patterns_file):
        """Load historical injury impact patterns"""
        try:
            if os.path.exists(patterns_file):
                with open(patterns_file, 'r') as f:
                    patterns = json.load(f)
                print(f"✅ Loaded historical patterns for {len(patterns)} teams")
                return patterns
            else:
                print(f"⚠️  No patterns file found at {patterns_file}")
                return {}
        except Exception as e:
            print(f"❌ Error loading patterns: {e}")
            return {}
    
    def find_similar_situation(self, team, missing_players, active_players):
        """
        Find historical games with similar missing player situations
        
        Args:
            team: Team code (e.g., 'CLE')
            missing_players: List of players out tonight
            active_players: List of players playing tonight
            
        Returns:
            dict of {player_name: recommended_adjustment_multiplier}
        """
        
        if team not in self.patterns:
            return {}
        
        team_patterns = self.patterns[team]
        adjustments = {}
        
        # For each missing player, check if we have historical pattern
        for missing_player in missing_players:
            if missing_player in team_patterns:
                # Found historical pattern for this specific player being out!
                teammate_impacts = team_patterns[missing_player]
                
                print(f"\n📊 Found historical pattern: {missing_player} OUT")
                print(f"   Based on {len(teammate_impacts)} teammates affected")
                
                # Apply learned adjustments to active players
                for active_player in active_players:
                    if active_player in teammate_impacts:
                        impact_data = teammate_impacts[active_player]
                        
                        # Calculate multiplier from historical data
                        # If player went from 20 PRA to 25 PRA, multiplier = 25/20 = 1.25
                        with_value = impact_data['with_player']
                        without_value = impact_data['without_player']
                        
                        if with_value > 0:
                            multiplier = without_value / with_value
                            
                            # Cap extreme multipliers
                            multiplier = max(0.90, min(1.50, multiplier))
                            
                            # Only apply if meaningful change (>3%)
                            if abs(multiplier - 1.0) > 0.03:
                                # Blend with existing adjustment if any
                                if active_player in adjustments:
                                    adjustments[active_player] = (adjustments[active_player] + multiplier) / 2
                                else:
                                    adjustments[active_player] = multiplier
                                
                                pct = (multiplier - 1) * 100
                                confidence = "high" if impact_data['sample_size_without'] >= 2 else "medium"
                                print(f"   {active_player}: {multiplier:.3f}x ({pct:+.0f}%) [{confidence} confidence]")
        
        return adjustments
    
    def apply_pattern_adjustments(self, base_projection, player_name, multiplier):
        """
        Apply historical pattern multiplier to base projection
        
        Args:
            base_projection: dict of projected stats
            player_name: Player name
            multiplier: Adjustment multiplier from historical patterns
            
        Returns:
            dict of adjusted projections
        """
        
        adjusted = base_projection.copy()
        
        # Apply multiplier to key stats
        for stat in ['Points', 'Rebounds', 'Assists', 'Steals', 'Blocks', 'Three Pointers Made']:
            if stat in adjusted:
                adjusted[stat] = adjusted[stat] * multiplier
        
        # Recalculate PRA
        adjusted['PRA'] = adjusted['Points'] + adjusted['Rebounds'] + adjusted['Assists']
        
        return adjusted

