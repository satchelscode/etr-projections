from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import pickle
import gzip
import os
import math
from io import StringIO, BytesIO
import json
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)


class HistoricalPatternMatcher:
    """Learns from actual ETR projection patterns in similar situations"""
    
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
                print(f"⚠️  No patterns file found, using generic adjustments")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load patterns: {e}")
            return {}
    
    def find_similar_situation(self, team, missing_players, active_players):
        """
        Find historical games with similar missing player situations
        Returns dict of {player_name: recommended_multiplier}
        """
        if team not in self.patterns:
            return {}
        
        team_patterns = self.patterns[team]
        adjustments = {}
        
        for missing_player in missing_players:
            if missing_player in team_patterns:
                teammate_impacts = team_patterns[missing_player]
                
                print(f"\n📊 Found historical pattern: {missing_player} OUT")
                print(f"   Based on {len(teammate_impacts)} teammates analyzed")
                
                for active_player in active_players:
                    if active_player in teammate_impacts:
                        impact_data = teammate_impacts[active_player]
                        
                        with_value = impact_data['with_player']
                        without_value = impact_data['without_player']
                        
                        if with_value > 0:
                            multiplier = without_value / with_value
                            multiplier = max(0.90, min(1.50, multiplier))
                            
                            if abs(multiplier - 1.0) > 0.03:
                                if active_player in adjustments:
                                    adjustments[active_player] = (adjustments[active_player] + multiplier) / 2
                                else:
                                    adjustments[active_player] = multiplier
                                
                                pct = (multiplier - 1) * 100
                                confidence = "high" if impact_data.get('sample_size_without', 0) >= 2 else "medium"
                                print(f"   {active_player}: {multiplier:.3f}x ({pct:+.0f}%) [{confidence} confidence]")
        
        return adjustments


class NBAProjectionSystem:
    def __init__(self):
        self.models = {}
        self.player_averages = {}
        self.team_averages = {}
        self.opponent_adjustments = {}
        self.master_stats = None
        self.stat_columns = ['Points', 'Assists', 'Rebounds', 'Three Pointers Made',
                            'Turnovers', 'Steals', 'Blocks', 'PRA']
        self.load_models()
        self.team_caps = self.load_learned_caps()
        self.pattern_matcher = HistoricalPatternMatcher()
        self.etr_rates = self.load_etr_rates()
        self.learned_absence_impacts = self.load_learned_absence_impacts()
        self.opponent_defense = self.load_opponent_defense()
        self.redistribution_rates = self.load_redistribution_rates()
        self.tuning_params = self.load_tuning_params()
    
    def load_learned_caps(self):
        """Load team-specific caps from learned parameters file"""
        try:
            caps_file = 'models/learned_team_caps.json'
            if os.path.exists(caps_file):
                with open(caps_file, 'r') as f:
                    params = json.load(f)
                    team_caps = {team: data['cap'] for team, data in params['team_caps'].items()}
                    print(f"✅ Loaded learned caps for {len(team_caps)} teams (validation #{params['validation_count']})")
                    return team_caps
        except Exception as e:
            print(f"⚠️  Could not load learned caps: {e}")
        
        # Fallback to default caps
        return {
            'IND': 1.15,  # Reduce from 1.25 based on analysis
            'CLE': 1.25,
            'CHA': 1.25,
            'ATL': 1.30, 
            'BKN': 1.30, 
            'DAL': 1.30, 
            'LAC': 1.30, 
            'LAL': 1.25,  # Reduce from 1.30
            'WAS': 1.30,
        }
    
    def load_etr_rates(self):
        """Load ETR learned per-minute rates from historical projections"""
        try:
            rates_file = 'models/etr_learned_rates.json'
            if os.path.exists(rates_file):
                with open(rates_file, 'r') as f:
                    rates = json.load(f)
                    print(f"✅ Loaded ETR rates for {len(rates)} players")
                    return rates
            else:
                print("⚠️  No ETR rates file found, using ML predictions only")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load ETR rates: {e}")
            return {}
    
    def load_learned_absence_impacts(self):
        """Load learned absence impacts from ETR historical data"""
        try:
            impacts_file = 'models/learned_absence_impacts.json'
            if os.path.exists(impacts_file):
                with open(impacts_file, 'r') as f:
                    impacts = json.load(f)
                    print(f"✅ Loaded learned absence impacts for {len(impacts)} teams")
                    return impacts
            else:
                print("⚠️  No learned absence impacts file found")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load learned absence impacts: {e}")
            return {}
    
    def load_opponent_defense(self):
        """Load opponent defensive ratings from ETR historical data"""
        try:
            defense_file = 'models/opponent_defense_ratings.json'
            if os.path.exists(defense_file):
                with open(defense_file, 'r') as f:
                    defense = json.load(f)
                    print(f"✅ Loaded opponent defense ratings for {len(defense)} teams")
                    return defense
            else:
                print("⚠️  No opponent defense ratings file found")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load opponent defense ratings: {e}")
            return {}
    
    def load_historical_patterns(self):
        """Load historical injury impact patterns"""
        try:
            patterns_file = 'models/historical_patterns.json'
            if os.path.exists(patterns_file):
                with open(patterns_file, 'r') as f:
                    patterns = json.load(f)
                print(f"✅ Loaded historical patterns for {len(patterns)} teams")
                return patterns
            else:
                print(f"⚠️  No historical patterns found, using generic adjustments")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load historical patterns: {e}")
            return {}
    
    def find_historical_pattern(self, team, missing_players, active_players):
        """Find historical pattern adjustments for this exact situation"""
        
        if team not in self.historical_patterns:
            return {}
        
        team_patterns = self.historical_patterns[team]
        adjustments = {}
        
        for missing_player in missing_players:
            if missing_player in team_patterns:
                teammate_impacts = team_patterns[missing_player]
                
                print(f"\n📊 HISTORICAL PATTERN FOUND: {missing_player} OUT")
                print(f"   Learning from {len(teammate_impacts)} teammates")
                
                for active_player in active_players:
                    if active_player in teammate_impacts:
                        impact_data = teammate_impacts[active_player]
                        
                        with_value = impact_data['with_player']
                        without_value = impact_data['without_player']
                        
                        if with_value > 0:
                            multiplier = without_value / with_value
                            multiplier = max(0.90, min(1.50, multiplier))
                            
                            if abs(multiplier - 1.0) > 0.03:
                                if active_player in adjustments:
                                    adjustments[active_player] = (adjustments[active_player] + multiplier) / 2
                                else:
                                    adjustments[active_player] = multiplier
                                
                                pct = (multiplier - 1) * 100
                                sample_size = impact_data.get('sample_size_without', 0)
                                confidence = "HIGH" if sample_size >= 2 else "MED"
                                print(f"   ✅ {active_player}: {multiplier:.3f}x ({pct:+.0f}%) [{confidence}]")
        
        return adjustments
    
    def load_models(self):
        """Load ML models and supporting data"""
        try:
            print("📦 Loading compressed models...")
            
            # Try compressed first
            model_path = 'models/nba_models.pkl.gz'
            if os.path.exists(model_path):
                with gzip.open(model_path, 'rb') as f:
                    self.models = pickle.load(f)
            else:
                # Fallback to uncompressed
                model_path = 'models/nba_models.pkl'
                with open(model_path, 'rb') as f:
                    self.models = pickle.load(f)
            
            print(f"✓ Compressed models loaded. Stats: {list(self.models.keys())}")
            for stat in list(self.models.keys())[:2]:
                model_type = type(self.models[stat]).__name__
                print(f"   {stat}: Single model ({model_type})")
            
            # Load opponent adjustments
            opp_adj_path = 'models/opponent_adjustments.csv'
            if os.path.exists(opp_adj_path):
                opp_df = pd.read_csv(opp_adj_path, index_col=0)
                self.opponent_adjustments = opp_df.to_dict()
                print(f"✓ Opponent adjustments loaded ({len(opp_df)} teams)")
            
            # Load player averages
            player_avg_path = 'models/player_averages.csv'
            if os.path.exists(player_avg_path):
                player_df = pd.read_csv(player_avg_path, index_col=0)
                self.player_averages = player_df.to_dict('index')
                print(f"✓ Player averages loaded ({len(player_df)} players)")
            
            # Load team averages
            team_avg_path = 'models/team_averages.csv'
            if os.path.exists(team_avg_path):
                team_df = pd.read_csv(team_avg_path, index_col=0)
                self.team_averages = team_df.to_dict('index')
                print(f"✓ Team averages loaded ({len(team_df)} teams)")
            
            # Load master stats
            master_path = 'models/NBA_Master_Stats.csv'
            if os.path.exists(master_path):
                self.master_stats = pd.read_csv(master_path)
            
            print("✅ All models and data loaded successfully!")
            
        except Exception as e:
            print(f"❌ Error loading models: {e}")
            import traceback
            traceback.print_exc()
    
    def create_feature_vector(self, player_name, team, opponent, position, minutes):
        feature_vec = []
        
        if player_name in self.player_averages:
            for stat in self.stat_columns:
                feature_vec.append(self.player_averages[player_name].get(stat, 0))
        else:
            feature_vec.extend([0] * len(self.stat_columns))
        
        if team in self.team_averages:
            for stat in self.stat_columns:
                feature_vec.append(self.team_averages[team].get(stat, 0))
        else:
            feature_vec.extend([0] * len(self.stat_columns))
        
        # Don't include PRA in opponent adjustments - it's calculated, not allowed
        opponent_stats = [s for s in self.stat_columns if s != 'PRA']
        for stat in opponent_stats:
            if opponent in self.opponent_adjustments[stat]:
                feature_vec.append(self.opponent_adjustments[stat][opponent])
            else:
                feature_vec.append(0)
        
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        for pos in positions:
            feature_vec.append(1 if position == pos else 0)
        
        feature_vec.append(minutes)
        
        return np.array([feature_vec])
    
    def is_valid_number(self, value):
        """Check if a value is a valid number"""
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return not (math.isnan(value) or math.isinf(value))
        return False
    
    def predict(self, player_name, opponent, minutes, team=None, playing_teammates=None):
        """Generate projections for a single player"""
        try:
            # DEBUG: Log first few players
            if not hasattr(self, '_debug_count'):
                self._debug_count = 0
            if self._debug_count < 3:
                print(f"DEBUG predict() called for: {player_name}")
                print(f"  In player_averages: {player_name in self.player_averages}")
                print(f"  In etr_rates: {player_name in self.etr_rates if hasattr(self, 'etr_rates') else 'N/A'}")
                self._debug_count += 1
            
            if player_name not in self.player_averages:
                # Try to use ETR rates directly if player not in averages
                if hasattr(self, 'etr_rates') and player_name in self.etr_rates:
                    etr = self.etr_rates[player_name]
                    team = team or etr.get('team', 'UNK')
                    projections = {}
                    projections['Points'] = 0
                    projections['Assists'] = 0
                    projections['Rebounds'] = 0
                    projections['Three Pointers Made'] = 0
                    projections['Steals'] = 0
                    projections['Blocks'] = 0
                    projections['Turnovers'] = 0
                    projections['PRA'] = 0
                    
                    projections = self.blend_with_etr_rates(player_name, minutes, projections, opponent, team, playing_teammates)
                    
                    return {
                        'success': True,
                        'projections': projections,
                        'team': team,
                        'position': 'SG'
                    }
                return {'success': False, 'error': f'Player {player_name} not found in database'}
            
            player_info = self.player_averages[player_name]
            player_team = team or player_info.get('Team', 'UNK')
            position = player_info.get('Position', 'SG')
            
            X = self.create_feature_vector(player_name, player_team, opponent, position, minutes)
            
            projections = {}
            
            for stat in self.stat_columns:
                try:
                    if stat in self.models:
                        pred = self.models[stat].predict(X)[0]
                        
                        if self.is_valid_number(pred):
                            projections[stat] = max(0, pred)
                        else:
                            return {'success': False, 'error': f'Invalid prediction for {stat}'}
                    else:
                        return {'success': False, 'error': f'No model for {stat}'}
                        
                except Exception as e:
                    print(f"❌ Error predicting {stat} for {player_name}: {e}")
                    return {'success': False, 'error': f'Prediction error for {stat}: {str(e)}'}
            
            # BLEND with ETR learned rates if available (with opponent and lineup adjustments)
            projections = self.blend_with_etr_rates(player_name, minutes, projections, opponent, player_team, playing_teammates, position)
            
            return {
                'success': True,
                'projections': projections,
                'team': player_team,
                'position': position
            }
            
        except Exception as e:
            print(f"❌ Error in predict for {player_name}: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def blend_with_etr_rates(self, player_name, minutes, ml_projections, opponent=None, team=None, playing_teammates=None, position=None):
        """
        Use ETR learned per-minute rates with lineup-based adjustments.
        
        Key improvements:
        1. Sample size confidence weighting (blend with position avg for low-sample players)
        2. Opponent defense adjustments
        3. Lineup-based rate changes when key players are out
        """
        projections = ml_projections.copy()
        
        # Load tuning parameters if available
        tuning = getattr(self, 'tuning_params', {})
        pos_fallback = tuning.get('position_fallback_rates', {})
        sample_conf = tuning.get('sample_size_confidence', {})
        
        # Check if player has ETR rates
        if not hasattr(self, 'etr_rates') or player_name not in self.etr_rates:
            # Use position-based fallback rates for unknown players
            if position and position in pos_fallback:
                pos_rates = pos_fallback[position]
                projections['Points'] = pos_rates.get('pts_per_min', 0.45) * minutes
                projections['Assists'] = pos_rates.get('ast_per_min', 0.10) * minutes
                projections['Rebounds'] = pos_rates.get('reb_per_min', 0.15) * minutes
                projections['Three Pointers Made'] = pos_rates.get('3pm_per_min', 0.05) * minutes
                projections['Steals'] = 0.02 * minutes
                projections['Blocks'] = 0.02 * minutes
                projections['Turnovers'] = 0.05 * minutes
                projections['PRA'] = projections['Points'] + projections['Rebounds'] + projections['Assists']
            return projections
        
        etr = self.etr_rates[player_name]
        sample_size = etr.get('sample_size', 0)
        
        if sample_size < 1:
            return ml_projections
        
        # Determine confidence weight based on sample size
        if sample_size == 1:
            confidence = sample_conf.get('1_game', 0.5)
        elif sample_size <= 3:
            confidence = sample_conf.get('2-3_games', 0.75)
        elif sample_size <= 6:
            confidence = sample_conf.get('4-6_games', 0.9)
        else:
            confidence = sample_conf.get('7+_games', 1.0)
        
        # Get base rates (may be modified if key player is out)
        pts_rate = self._get_effective_rate(player_name, team, playing_teammates, 'pts')
        ast_rate = self._get_effective_rate(player_name, team, playing_teammates, 'ast')
        reb_rate = self._get_effective_rate(player_name, team, playing_teammates, 'reb')
        
        # Calculate ETR-based projections
        etr_pts = pts_rate * minutes
        etr_ast = ast_rate * minutes
        etr_reb = reb_rate * minutes
        
        # Blend with position averages based on confidence (only if low confidence)
        if position and position in pos_fallback and confidence < 1.0:
            pos_rates = pos_fallback[position]
            pos_pts = pos_rates.get('pts_per_min', 0.45) * minutes
            pos_ast = pos_rates.get('ast_per_min', 0.10) * minutes
            pos_reb = pos_rates.get('reb_per_min', 0.15) * minutes
            
            projections['Points'] = confidence * etr_pts + (1 - confidence) * pos_pts
            projections['Assists'] = confidence * etr_ast + (1 - confidence) * pos_ast
            projections['Rebounds'] = confidence * etr_reb + (1 - confidence) * pos_reb
        else:
            projections['Points'] = etr_pts
            projections['Assists'] = etr_ast
            projections['Rebounds'] = etr_reb
        
        # Use standard rates for other stats
        projections['Three Pointers Made'] = etr.get('3pm_per_min', 0) * minutes
        projections['Steals'] = etr.get('stl_per_min', 0) * minutes
        projections['Blocks'] = etr.get('blk_per_min', 0) * minutes
        projections['Turnovers'] = etr.get('tov_per_min', 0) * minutes
        
        # Apply opponent adjustments
        if opponent and hasattr(self, 'opponent_defense') and opponent in self.opponent_defense:
            opp_adj = self.opponent_defense[opponent]
            projections['Points'] *= opp_adj.get('pts_mult', 1.0)
            projections['Assists'] *= opp_adj.get('ast_mult', 1.0)
            projections['Rebounds'] *= opp_adj.get('reb_mult', 1.0)
        
        # Recalculate PRA
        projections['PRA'] = projections['Points'] + projections['Rebounds'] + projections['Assists']
        
        return projections
    
    def _get_effective_rate(self, player, team, playing_teammates, stat):
        """
        Get the effective per-minute rate for a player based on who's playing.
        Uses observed rates when key players are out.
        """
        if player not in self.etr_rates:
            return 0
        
        base_rate = self.etr_rates[player].get(f'{stat}_per_min', 0)
        
        # If no redistribution data or no teammate info, use base rate
        if not hasattr(self, 'redistribution_rates') or team is None or playing_teammates is None:
            return base_rate
        
        if team not in self.redistribution_rates:
            return base_rate
        
        team_redist = self.redistribution_rates[team]
        
        # Check if any players with redistribution data are missing
        for missing_player, teammate_data in team_redist.items():
            if missing_player not in playing_teammates and player in teammate_data:
                data = teammate_data[player]
                rate_key = f'without_{stat}_rate'
                if rate_key in data:
                    return data[rate_key]
        
        return base_rate
    
    def load_redistribution_rates(self):
        """Load learned redistribution rates"""
        try:
            redist_file = 'models/redistribution_rates.json'
            if os.path.exists(redist_file):
                with open(redist_file, 'r') as f:
                    rates = json.load(f)
                    print(f"✅ Loaded redistribution rates for {len(rates)} teams")
                    return rates
            else:
                print("⚠️  No redistribution rates file found")
                return {}
        except Exception as e:
            print(f"⚠️  Could not load redistribution rates: {e}")
            return {}
    
    def load_tuning_params(self):
        """Load fine-tuning parameters for minute efficiency and sample size confidence"""
        try:
            tuning_file = 'models/tuning_params.json'
            if os.path.exists(tuning_file):
                with open(tuning_file, 'r') as f:
                    params = json.load(f)
                    print(f"✅ Loaded tuning params (minute efficiency, sample confidence)")
                    return params
            else:
                print("⚠️  No tuning params file found, using defaults")
                return self._default_tuning_params()
        except Exception as e:
            print(f"⚠️  Could not load tuning params: {e}")
            return self._default_tuning_params()
    
    def _default_tuning_params(self):
        """Return default tuning parameters"""
        return {
            'minute_efficiency_multipliers': {
                '0-15': 0.71,
                '15-25': 0.75,
                '25-35': 1.0,
                '35+': 1.28
            },
            'position_fallback_rates': {
                'PG': {'pts_per_min': 0.48, 'ast_per_min': 0.175, 'reb_per_min': 0.126, '3pm_per_min': 0.061},
                'SG': {'pts_per_min': 0.45, 'ast_per_min': 0.107, 'reb_per_min': 0.133, '3pm_per_min': 0.069},
                'SF': {'pts_per_min': 0.44, 'ast_per_min': 0.083, 'reb_per_min': 0.163, '3pm_per_min': 0.057},
                'PF': {'pts_per_min': 0.44, 'ast_per_min': 0.080, 'reb_per_min': 0.205, '3pm_per_min': 0.050},
                'C': {'pts_per_min': 0.43, 'ast_per_min': 0.079, 'reb_per_min': 0.292, '3pm_per_min': 0.026}
            },
            'sample_size_confidence': {
                '1_game': 0.3,
                '2-3_games': 0.6,
                '4-6_games': 0.85,
                '7+_games': 1.0
            }
        }
    
    
    def get_typical_team_minutes(self, team):
        """Get typical minutes for team's roster from master stats"""
        if self.master_stats is None:
            return {}
        
        team_players = self.master_stats[self.master_stats['Team'] == team]
        
        typical_roster = {}
        for player in team_players['Player'].unique():
            player_games = team_players[team_players['Player'] == player]
            
            typical_roster[player] = {
                'typical_minutes': player_games['Minutes'].mean(),
                'master_stats': {
                    'Points': player_games['Points'].mean(),
                    'Rebounds': player_games['Rebounds'].mean(),
                    'Assists': player_games['Assists'].mean(),
                    'Steals': player_games['Steals'].mean(),
                    'Blocks': player_games['Blocks'].mean(),
                    'Three Pointers Made': player_games['Three Pointers Made'].mean()
                }
            }
        
        return typical_roster
    
    def calculate_assist_redistribution(self, team, projected_players_dict):
        """
        USE LEARNED ABSENCE IMPACTS from ETR historical data.
        
        ETR's actual adjustment range: 95% are between 0.89x and 1.13x
        We cap our adjustments to match this conservative range.
        """
        
        adjustments = {}
        
        try:
            # Check if we have learned impacts for this team
            if not hasattr(self, 'learned_absence_impacts') or team not in self.learned_absence_impacts:
                return {}  # No fallback - if no data, no adjustment
            
            team_impacts = self.learned_absence_impacts[team]
            
            # Find which stars are OUT tonight
            missing_stars = []
            for star_name in team_impacts.keys():
                if star_name not in projected_players_dict:
                    missing_stars.append(star_name)
            
            if not missing_stars:
                return {}
            
            print(f"\n🎯 ABSENCE IMPACTS for {team} (ETR-calibrated):")
            for star in missing_stars:
                print(f"   ⚠️  {star} is OUT")
            
            # Apply learned multipliers for each missing star
            for star_name in missing_stars:
                star_impacts = team_impacts[star_name]
                
                for teammate, impact_data in star_impacts.items():
                    if teammate in projected_players_dict:
                        # Get multipliers (already capped to ETR range in the JSON)
                        ast_mult = impact_data.get('ast_multiplier', 1.0)
                        pts_mult = impact_data.get('pts_multiplier', 1.0)
                        reb_mult = impact_data.get('reb_multiplier', 1.0)
                        
                        # Only apply if meaningful (>2% change)
                        if abs(ast_mult - 1.0) > 0.02 or abs(pts_mult - 1.0) > 0.02:
                            if teammate in adjustments:
                                # Combine multipliers but stay in ETR range
                                existing = adjustments[teammate]['multipliers']
                                existing['Assists'] = max(0.85, min(1.20, existing['Assists'] * ast_mult))
                                existing['Points'] = max(0.89, min(1.13, existing['Points'] * pts_mult))
                                existing['Rebounds'] = max(0.90, min(1.15, existing['Rebounds'] * reb_mult))
                            else:
                                adjustments[teammate] = {
                                    'multipliers': {
                                        'Points': max(0.89, min(1.13, pts_mult)),
                                        'Rebounds': max(0.90, min(1.15, reb_mult)),
                                        'Assists': max(0.85, min(1.20, ast_mult)),
                                        'Steals': 1.0,
                                        'Blocks': 1.0,
                                        'Three Pointers Made': max(0.90, min(1.10, pts_mult))
                                    },
                                    'source': 'etr_calibrated_absence'
                                }
                            
                            print(f"   ✅ {teammate}: PTS {pts_mult:.2f}x, AST {ast_mult:.2f}x")
            
            return adjustments
            
        except Exception as e:
            print(f"Error in absence impacts: {e}")
            return {}
    
    def _fallback_assist_redistribution(self, team, projected_players_dict):
        """
        NEW METHOD: Specifically handle assist redistribution when star playmakers are OUT
        
        This is the KEY FIX for matching ETR projections more closely.
        When a high-assist player (8+ AST avg) is out, their assists need to be
        redistributed to teammates, especially the primary ball handler.
        """
        
        # Define high-assist thresholds
        HIGH_ASSIST_THRESHOLD = 6.0  # Player averages 6+ AST
        
        adjustments = {}
        
        try:
            if self.master_stats is None:
                return {}
            
            # Get team's typical roster from master_stats
            team_data = self.master_stats[self.master_stats['Team'] == team]
            if team_data.empty:
                return {}
            
            # Calculate player averages from master_stats
            player_stats = team_data.groupby('Player').agg({
                'Assists': 'mean',
                'Points': 'mean',
                'Rebounds': 'mean',
                'Position': 'first',
                'Minutes': 'mean'
            }).to_dict('index')
            
            # Find missing high-assist players
            missing_playmakers = []
            
            for player_name, stats in player_stats.items():
                player_assists = stats.get('Assists', 0)
                player_minutes = stats.get('Minutes', 0)
                
                # Check if this high-assist player is NOT in projected players tonight
                if player_assists >= HIGH_ASSIST_THRESHOLD and player_minutes >= 20:
                    if player_name not in projected_players_dict:
                        missing_playmakers.append({
                            'name': player_name,
                            'assists': player_assists,
                            'points': stats.get('Points', 0),
                            'rebounds': stats.get('Rebounds', 0)
                        })
            
            if not missing_playmakers:
                return {}
            
            # Calculate total assists to redistribute
            total_missing_assists = sum(p['assists'] for p in missing_playmakers)
            total_missing_points = sum(p['points'] for p in missing_playmakers)
            total_missing_rebounds = sum(p['rebounds'] for p in missing_playmakers)
            
            # Apply efficiency factors (calibrated to match ETR projections)
            assist_pool = total_missing_assists * 0.50  # 50% of assists get redistributed
            points_pool = total_missing_points * 0.45   # 45% of points (efficiency drops)
            rebounds_pool = total_missing_rebounds * 0.60  # 60% of rebounds
            
            print(f"\n🎯 ASSIST REDISTRIBUTION for {team}:")
            for pm in missing_playmakers:
                print(f"   ⚠️  {pm['name']} OUT: {pm['assists']:.1f} AST, {pm['points']:.1f} PTS")
            print(f"   📊 Pool to redistribute: {assist_pool:.1f} AST, {points_pool:.1f} PTS, {rebounds_pool:.1f} REB")
            
            # Sort active players by minutes (primary ball handler gets most)
            active_players = [(name, mins) for name, mins in projected_players_dict.items() if mins >= 15]
            active_players.sort(key=lambda x: x[1], reverse=True)
            
            if not active_players:
                return {}
            
            total_active_minutes = sum(mins for _, mins in active_players)
            
            for i, (player_name, projected_mins) in enumerate(active_players):
                minute_share = projected_mins / total_active_minutes if total_active_minutes > 0 else 0
                
                # Get player's position and base stats from master_stats
                position = player_stats.get(player_name, {}).get('Position', 'SF')
                base_assists = player_stats.get(player_name, {}).get('Assists', 0)
                base_points = player_stats.get(player_name, {}).get('Points', 0)
                base_rebounds = player_stats.get(player_name, {}).get('Rebounds', 0)
                
                # If not in team's master stats, try player_averages
                if base_assists == 0 and player_name in self.player_averages:
                    base_assists = self.player_averages[player_name].get('Assists', 0)
                    base_points = self.player_averages[player_name].get('Points', 0)
                    base_rebounds = self.player_averages[player_name].get('Rebounds', 0)
                
                is_guard = position in ['PG', 'SG']
                is_primary = (i == 0)  # Most minutes = primary
                is_secondary = (i == 1)
                
                # Calculate assist share based on role
                if is_primary and is_guard:
                    assist_share = 0.40  # Primary ball handler gets 40%
                elif is_primary:
                    assist_share = 0.30  # Primary non-guard gets 30%
                elif is_secondary and is_guard:
                    assist_share = 0.25  # Secondary guard gets 25%
                elif is_secondary:
                    assist_share = 0.15  # Secondary non-guard gets 15%
                else:
                    assist_share = minute_share * 0.5  # Others by minutes
                
                # Points and rebounds distributed more evenly by minutes
                points_share = minute_share
                rebounds_share = minute_share
                
                # Calculate boosts
                assist_boost = (assist_pool * assist_share) / base_assists if base_assists > 0.5 else 0
                points_boost = (points_pool * points_share) / base_points if base_points > 1 else 0
                rebounds_boost = (rebounds_pool * rebounds_share) / base_rebounds if base_rebounds > 1 else 0
                
                # Cap the boosts
                assist_multiplier = min(1.0 + assist_boost, 1.50)  # Max 50% boost
                points_multiplier = min(1.0 + points_boost, 1.35)  # Max 35% boost
                rebounds_multiplier = min(1.0 + rebounds_boost, 1.30)  # Max 30% boost
                
                # Only add if meaningful boost
                if assist_multiplier > 1.05 or points_multiplier > 1.05:
                    adjustments[player_name] = {
                        'multipliers': {
                            'Points': points_multiplier,
                            'Rebounds': rebounds_multiplier,
                            'Assists': assist_multiplier,
                            'Steals': min(1.0 + (assist_boost * 0.3), 1.20),
                            'Blocks': min(1.0 + (rebounds_boost * 0.3), 1.20),
                            'Three Pointers Made': min(points_multiplier * 0.95, 1.30)
                        },
                        'source': 'assist_redistribution'
                    }
                    
                    role = "PRIMARY" if is_primary else ("SECONDARY" if is_secondary else "ROLE")
                    print(f"   ✅ {player_name} [{role}]: AST {(assist_multiplier-1)*100:+.0f}%, PTS {(points_multiplier-1)*100:+.0f}%")
            
            return adjustments
            
        except Exception as e:
            print(f"Error in assist redistribution: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def calculate_usage_adjustments(self, team, projected_players_dict):
        """
        Calculate usage adjustments using HISTORICAL PATTERNS when available
        Falls back to generic if no pattern exists
        
        KEY ENHANCEMENT: Special handling for high-assist playmakers being OUT
        """
        
        # Get team-specific cap
        max_boost = self.team_caps.get(team, 1.40)
        
        # FIRST: Check for missing star playmakers and apply assist redistribution
        assist_adjustments = self.calculate_assist_redistribution(team, projected_players_dict)
        if assist_adjustments:
            print(f"📊 Applied assist redistribution for {team}")
        
        try:
            typical_roster = self.get_typical_team_minutes(team)
            
            if not typical_roster:
                return {}
            
            # Find significant missing players (20+ mins typically)
            missing_players = {}
            for player_name, player_data in typical_roster.items():
                if player_name not in projected_players_dict and player_data['typical_minutes'] >= 20:
                    missing_players[player_name] = player_data
            
            if not missing_players:
                return {}
            
            print(f"\n🚨 {team} USAGE ADJUSTMENT:")
            print(f"Missing key players: {', '.join(missing_players.keys())}")
            print(f"Team boost cap: {max_boost:.2f} ({int((max_boost-1)*100)}%)")
            
            # TRY HISTORICAL PATTERNS FIRST
            missing_player_names = list(missing_players.keys())
            active_player_names = list(projected_players_dict.keys())
            
            historical_adjustments = self.pattern_matcher.find_similar_situation(
                team,
                missing_player_names,
                active_player_names
            )
            
            # If we have historical patterns, use them!
            if historical_adjustments:
                print(f"✅ Using {len(historical_adjustments)} HISTORICAL PATTERNS")
                
                adjustments = {}
                for player_name, multiplier in historical_adjustments.items():
                    # Cap the historical multiplier too
                    multiplier = min(multiplier, max_boost)
                    
                    multipliers = {}
                    for stat in ['Points', 'Rebounds', 'Assists', 'Steals', 'Blocks', 'Three Pointers Made']:
                        multipliers[stat] = multiplier
                    
                    adjustments[player_name] = {
                        'multipliers': multipliers,
                        'source': 'historical_pattern'
                    }
                
                # DON'T return early - merge with assist_adjustments first!
                # MERGE: Combine assist redistribution adjustments with historical
                for player_name, assist_adj in assist_adjustments.items():
                    if player_name in adjustments:
                        existing = adjustments[player_name]['multipliers']
                        new_assists = assist_adj['multipliers']
                        # Take the HIGHER assist multiplier
                        if new_assists.get('Assists', 1.0) > existing.get('Assists', 1.0):
                            existing['Assists'] = new_assists['Assists']
                            adjustments[player_name]['source'] = 'assist_redistribution+historical'
                            print(f"   🔄 {player_name}: Applying assist redistribution boost (AST: {new_assists['Assists']:.2f}x)")
                    else:
                        adjustments[player_name] = assist_adj
                        print(f"   ➕ {player_name}: Adding assist redistribution adjustment")
                
                return adjustments
            
            # FALLBACK TO GENERIC if no historical pattern
            print("⚠️  No historical pattern found, using generic boost")
            
            # Calculate total missing production
            total_missing_minutes = sum(p['typical_minutes'] for p in missing_players.values())
            missing_production = {
                'Points': sum(p['master_stats'].get('Points', 0) for p in missing_players.values()),
                'Rebounds': sum(p['master_stats'].get('Rebounds', 0) for p in missing_players.values()),
                'Assists': sum(p['master_stats'].get('Assists', 0) for p in missing_players.values()),
                'Steals': sum(p['master_stats'].get('Steals', 0) for p in missing_players.values()),
                'Blocks': sum(p['master_stats'].get('Blocks', 0) for p in missing_players.values()),
                'Three Pointers Made': sum(p['master_stats'].get('Three Pointers Made', 0) for p in missing_players.values())
            }
            
            print(f"Missing production: {missing_production['Points']:.1f} pts, {missing_production['Rebounds']:.1f} reb, {missing_production['Assists']:.1f} ast")
            print(f"Missing minutes: {total_missing_minutes:.1f}")
            
            # Calculate adjustments for active players
            adjustments = {}
            total_active_minutes = sum(projected_players_dict.values())
            
            for player_name, projected_mins in projected_players_dict.items():
                # Skip bench players with <15 projected minutes
                if projected_mins < 15:
                    continue
                
                minute_share = projected_mins / total_active_minutes if total_active_minutes > 0 else 0
                
                # Extra boost for players getting more minutes than usual
                if player_name in typical_roster:
                    typical_mins = typical_roster[player_name]['typical_minutes']
                    extra_minute_boost = max(0, (projected_mins - typical_mins) / typical_mins) if typical_mins > 0 else 0
                    is_replacement = projected_mins > typical_mins + 5
                else:
                    typical_mins = 0
                    extra_minute_boost = 0
                    is_replacement = True
                
                # Combined share
                total_share = (minute_share * 0.80) + (extra_minute_boost * 0.20)
                
                # Updated efficiency factors (from analysis)
                efficiency = 0.67 if is_replacement else 0.57
                
                # Star player boost
                if projected_mins >= 35:
                    efficiency *= 1.05
                    print(f"   ⭐ Star boost: {player_name} ({projected_mins:.0f} mins)")
                
                # Calculate multipliers
                multipliers = {}
                for stat in missing_production.keys():
                    if player_name in typical_roster:
                        base = typical_roster[player_name]['master_stats'].get(stat, 0)
                    else:
                        base = 0
                    
                    if base > 0:
                        boost = (missing_production[stat] * total_share * efficiency) / base
                        multiplier = 1 + boost
                        # Apply team-specific cap
                        multiplier = min(multiplier, max_boost)
                        multipliers[stat] = multiplier
                
                # Only add if meaningful boost (>5%)
                if multipliers and any(m > 1.05 for m in multipliers.values()):
                    adjustments[player_name] = {
                        'multipliers': multipliers,
                        'share': total_share,
                        'source': 'generic'
                    }
                    
                    boost_pct = int((max(multipliers.values()) - 1) * 100)
                    role = "REPLACEMENT" if is_replacement else f"+{projected_mins-typical_mins:.1f} mins"
                    print(f"✅ {player_name} ({role}): {boost_pct}% boost [GENERIC]")
            
            # MERGE: Combine assist redistribution adjustments with generic/historical
            # Assist redistribution takes priority for the Assists stat
            for player_name, assist_adj in assist_adjustments.items():
                if player_name in adjustments:
                    # Merge: keep higher assist multiplier, average others
                    existing = adjustments[player_name]['multipliers']
                    new_assists = assist_adj['multipliers']
                    
                    # Take the HIGHER assist multiplier (assist redistribution is usually better)
                    if new_assists.get('Assists', 1.0) > existing.get('Assists', 1.0):
                        existing['Assists'] = new_assists['Assists']
                        adjustments[player_name]['source'] = 'assist_redistribution+generic'
                        print(f"   🔄 {player_name}: Using assist redistribution AST boost")
                else:
                    # Add new adjustment from assist redistribution
                    adjustments[player_name] = assist_adj
            
            return adjustments
            
        except Exception as e:
            print(f"Error calculating usage adjustments: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def parse_dfs_projections_csv(self, file_content):
        """Parse NBA DFS Projections CSV to extract player, team, opponent, and minutes"""
        try:
            df = pd.read_csv(StringIO(file_content), encoding='utf-8-sig')
            print(f"DFS Projections CSV columns: {df.columns.tolist()}")
            print(f"DFS Projections CSV shape: {df.shape}")
            
            players_data = []
            for _, row in df.iterrows():
                try:
                    # Get minutes value
                    minutes = float(row.get('Minutes', 0))
                    
                    # Only include players with minutes > 0
                    if pd.notna(minutes) and minutes > 0:
                        players_data.append({
                            'player': str(row['Player']).strip(),
                            'team': str(row['Team']).strip(),
                            'opponent': str(row['Opp']).strip(),
                            'position': str(row.get('Pos', 'SG')).strip(),
                            'minutes': minutes
                        })
                except Exception as e:
                    continue
            
            print(f"Parsed {len(players_data)} players from DFS Projections")
            return players_data
            
        except Exception as e:
            print(f"Error parsing DFS Projections CSV: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def generate_daily_projections(self, dfs_data):
        projections = []
        skipped = []
        
        print(f"Generating projections for {len(dfs_data)} players...")
        print(f"ETR rates available: {len(self.etr_rates) if hasattr(self, 'etr_rates') else 0}")
        print(f"Player averages available: {len(self.player_averages) if hasattr(self, 'player_averages') else 0}")
        
        # Group players by team to know who's playing
        teams_dict = {}
        for player_data in dfs_data:
            team = player_data['team']
            if team not in teams_dict:
                teams_dict[team] = set()
            teams_dict[team].add(player_data['player'])
        
        # Generate projections using lineup-aware rates
        for player_data in dfs_data:
            player_name = player_data['player']
            opponent = player_data['opponent']
            minutes = player_data['minutes']
            team = player_data['team']
            playing_teammates = teams_dict.get(team, set())
            
            result = self.predict(player_name, opponent, minutes, team, playing_teammates)
            
            if result['success']:
                try:
                    proj = result['projections']
                    
                    # Validate all projection values
                    valid = True
                    for key, value in proj.items():
                        if not self.is_valid_number(value):
                            valid = False
                            break
                    
                    if valid:
                        projections.append({
                            'player': str(player_name),
                            'team': str(player_data['team']),  # Use team from input CSV
                            'opponent': str(opponent),
                            'position': str(player_data.get('position', result['position'])),
                            'minutes': float(minutes),
                            'points': float(proj['Points']),
                            'rebounds': float(proj['Rebounds']),
                            'assists': float(proj['Assists']),
                            'three_pointers_made': float(proj['Three Pointers Made']),
                            'steals': float(proj['Steals']),
                            'blocks': float(proj['Blocks']),
                            'turnovers': float(proj['Turnovers']),
                            'pra': float(proj['PRA']),
                            'usage_boosted': False
                        })
                    else:
                        skipped.append(f"{player_name} (invalid values)")
                except Exception as e:
                    skipped.append(f"{player_name} (conversion error: {e})")
            else:
                skipped.append(f"{player_name} ({result.get('error', 'unknown')})")
        
        print(f"\nSuccessfully generated {len(projections)} projections")
        print(f"Boosted {sum(1 for p in projections if p.get('usage_boosted', False))} players due to missing teammates")
        
        if skipped:
            print(f"\nSkipped {len(skipped)} players")
        
        return projections

# Initialize the projection system
projection_system = NBAProjectionSystem()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_daily', methods=['POST'])
def generate_daily():
    try:
        print("Received daily generation request")
        
        dfs_file = request.files.get('dfs_projections')
        
        if not dfs_file:
            return jsonify({'success': False, 'error': 'NBA DFS Projections CSV file is required'})
        
        print(f"Processing file: {dfs_file.filename}")
        
        dfs_content = dfs_file.read().decode('utf-8')
        dfs_data = projection_system.parse_dfs_projections_csv(dfs_content)
        
        if not dfs_data:
            return jsonify({'success': False, 'error': 'No valid data found in DFS Projections file'})
        
        projections = projection_system.generate_daily_projections(dfs_data)
        
        return jsonify({
            'success': True,
            'projections': projections,
            'count': len(projections)
        })
        
    except Exception as e:
        print(f"Error in generate_daily: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download_projections', methods=['POST'])
def download_projections():
    try:
        data = request.get_json()
        projections = data.get('projections', [])
        
        if not projections:
            return jsonify({'success': False, 'error': 'No projections to download'})
        
        df = pd.DataFrame(projections)
        
        # Reorder columns
        column_order = ['player', 'team', 'opponent', 'position', 'minutes',
                       'points', 'rebounds', 'assists', 'three_pointers_made',
                       'steals', 'blocks', 'turnovers', 'pra']
        
        for col in column_order:
            if col not in df.columns:
                df[col] = 0
        
        df = df[column_order]
        
        # Create CSV
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name='nba_daily_projections.csv'
        )
        
    except Exception as e:
        print(f"Error in download_projections: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/calculate_scenario', methods=['POST'])
def calculate_scenario():
    """Calculate projection changes when a player is marked OUT"""
    try:
        data = request.get_json()
        out_player = data.get('out_player')
        team = data.get('team')
        current_projections = data.get('projections', [])
        
        if not out_player or not team:
            return jsonify({'success': False, 'error': 'Missing out_player or team'})
        
        # Get teammates from current projections
        teammates = [p for p in current_projections if p.get('team') == team and p.get('player') != out_player]
        
        if not teammates:
            return jsonify({'success': False, 'error': f'No teammates found for {team}'})
        
        # Check if we have redistribution data for this player being out
        redist = projection_system.redistribution_rates
        
        adjusted_projections = []
        
        for teammate in teammates:
            player_name = teammate['player']
            minutes = teammate['minutes']
            original_pra = teammate['pra']
            
            # Default: no change
            new_pts = teammate['points']
            new_ast = teammate['assists']
            new_reb = teammate['rebounds']
            
            # Check if we have data for when out_player is out
            if team in redist and out_player in redist[team]:
                if player_name in redist[team][out_player]:
                    boost_data = redist[team][out_player][player_name]
                    
                    # Use "without" rates instead of base rates
                    new_pts = boost_data.get('without_pts_rate', teammate['points']/minutes) * minutes
                    new_ast = boost_data.get('without_ast_rate', teammate['assists']/minutes) * minutes
                    new_reb = boost_data.get('without_reb_rate', teammate['rebounds']/minutes) * minutes
            
            new_pra = new_pts + new_ast + new_reb
            pra_change = new_pra - original_pra
            
            adjusted_projections.append({
                'player': player_name,
                'team': team,
                'position': teammate.get('position', ''),
                'minutes': minutes,
                'original_pra': round(original_pra, 2),
                'new_pra': round(new_pra, 2),
                'pra_change': round(pra_change, 2),
                'original_pts': round(teammate['points'], 2),
                'new_pts': round(new_pts, 2),
                'original_reb': round(teammate['rebounds'], 2),
                'new_reb': round(new_reb, 2),
                'original_ast': round(teammate['assists'], 2),
                'new_ast': round(new_ast, 2)
            })
        
        # Sort by PRA change descending
        adjusted_projections.sort(key=lambda x: x['pra_change'], reverse=True)
        
        return jsonify({
            'success': True,
            'out_player': out_player,
            'team': team,
            'adjusted_projections': adjusted_projections
        })
        
    except Exception as e:
        print(f"Error in calculate_scenario: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get_injuries', methods=['GET'])
def get_injuries():
    """Scrape Rotowire for questionable/probable players"""
    try:
        url = "https://www.rotowire.com/basketball/nba-lineups.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        injuries_by_team = {}
        
        # Find all lineup boxes (each game has 2 teams)
        lineup_boxes = soup.find_all('div', class_='lineup__box')
        print(f"Found {len(lineup_boxes)} lineup boxes")
        
        for box in lineup_boxes:
            # Get team abbreviation
            team_elem = box.find('div', class_='lineup__abbr')
            if not team_elem:
                continue
            team = team_elem.text.strip()
            
            if team not in injuries_by_team:
                injuries_by_team[team] = []
            
            seen_players = set()
            
            # Method 1: Look for lineup__injured section
            injured_section = box.find('ul', class_='lineup__injured')
            if injured_section:
                players = injured_section.find_all('li', class_='lineup__player')
                for player in players:
                    player_link = player.find('a')
                    if not player_link:
                        continue
                    
                    short_name = player_link.text.strip()
                    if short_name in seen_players:
                        continue
                    
                    status_elem = player.find('span', class_='lineup__inj')
                    if status_elem:
                        status = status_elem.text.strip().lower()
                        seen_players.add(short_name)
                        injuries_by_team[team].append({
                            'player': short_name,
                            'status': status,
                            'full_status': get_full_status(status)
                        })
            
            # Method 2: If no injured section found, look for players with injury tags
            # that are NOT in the starting lineup (first 5 players in lineup__main)
            if not injuries_by_team[team]:
                # Get starting 5 names to exclude
                main_lineup = box.find('ul', class_='lineup__main')
                starters = set()
                if main_lineup:
                    for li in main_lineup.find_all('li', class_='lineup__player')[:5]:
                        a = li.find('a')
                        if a:
                            starters.add(a.text.strip())
                
                # Find ALL players with injury status
                all_players = box.find_all('li', class_='lineup__player')
                for player in all_players:
                    player_link = player.find('a')
                    if not player_link:
                        continue
                    
                    short_name = player_link.text.strip()
                    
                    # Skip if already seen or if it's a starter (to avoid duplicates)
                    if short_name in seen_players:
                        continue
                    
                    status_elem = player.find('span', class_='lineup__inj')
                    if status_elem:
                        status = status_elem.text.strip().lower()
                        if status in ['ques', 'prob', 'doubt', 'gtd', 'out']:
                            seen_players.add(short_name)
                            # Only add if NOT a starter (starters with tags are duplicates)
                            # OR if there are no starters found (fallback)
                            if short_name not in starters or not starters:
                                injuries_by_team[team].append({
                                    'player': short_name,
                                    'status': status,
                                    'full_status': get_full_status(status)
                                })
        
        # Filter to only teams with injuries
        injuries_by_team = {k: v for k, v in injuries_by_team.items() if v}
        
        print(f"Found injuries for {len(injuries_by_team)} teams")
        for team, players in injuries_by_team.items():
            print(f"  {team}: {[p['player'] + ' (' + p['status'] + ')' for p in players]}")
        
        return jsonify({
            'success': True,
            'injuries': injuries_by_team
        })
        
    except Exception as e:
        print(f"Error scraping injuries: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

def get_full_status(status):
    """Convert short status to full status name"""
    status_map = {
        'ques': 'Questionable',
        'prob': 'Probable', 
        'doubt': 'Doubtful',
        'gtd': 'Game-Time Decision',
        'out': 'Out'
    }
    return status_map.get(status, status)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
