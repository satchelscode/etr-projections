from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import pickle
import gzip
import os
import math
import json
from pattern_matcher import HistoricalPatternMatcher
from io import StringIO, BytesIO

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

class NBAProjectionSystem:
    def __init__(self):
        self.models = None
        self.opponent_adjustments = None
        self.player_averages = None
        self.team_averages = None
        self.players_list = []
        self.teams_list = []
        self.stat_columns = [
            'Points', 'Assists', 'Rebounds', 'Three Pointers Made',
            'Turnovers', 'Steals', 'Blocks', 'PRA'
        ]
        self.load_models()
        self.team_caps = self.load_learned_caps()
        self.pattern_matcher = HistoricalPatternMatcher()
    
    def load_models(self):
        try:
            # Try loading compressed model first (smaller, faster)
            if os.path.exists('models/nba_models.pkl.gz'):
                print("📦 Loading compressed models...")
                with gzip.open('models/nba_models.pkl.gz', 'rb') as f:
                    self.models = pickle.load(f)
                print(f"✓ Compressed models loaded. Stats: {list(self.models.keys())}")
            # Fall back to regular pickle
            elif os.path.exists('models/nba_models.pkl'):
                print("📦 Loading standard models...")
                with open('models/nba_models.pkl', 'rb') as f:
                    self.models = pickle.load(f)
                print(f"✓ Standard models loaded. Stats: {list(self.models.keys())}")
            else:
                raise FileNotFoundError("No model file found (nba_models.pkl.gz or nba_models.pkl)")
            
            # Check model format
            for stat in list(self.models.keys())[:2]:
                if isinstance(self.models[stat], dict):
                    print(f"   {stat}: Ensemble model (keys: {list(self.models[stat].keys())})")
                else:
                    print(f"   {stat}: Single model ({type(self.models[stat]).__name__})")
            
            self.opponent_adjustments = pd.read_csv('models/opponent_adjustments.csv', index_col=0).to_dict()
            print(f"✓ Opponent adjustments loaded ({len(self.opponent_adjustments['Points'])} teams)")
            
            player_avg_df = pd.read_csv('models/player_averages.csv', index_col=0)
            self.player_averages = player_avg_df.to_dict('index')
            self.players_list = sorted(list(self.player_averages.keys()))
            print(f"✓ Player averages loaded ({len(self.player_averages)} players)")
            
            team_avg_df = pd.read_csv('models/team_averages.csv', index_col=0)
            self.team_averages = team_avg_df.to_dict('index')
            self.teams_list = sorted(list(self.team_averages.keys()))
            print(f"✓ Team averages loaded ({len(self.team_averages)} teams)")
            
            print("✅ All models and data loaded successfully!")
            
        except Exception as e:
            print(f"❌ Error loading models: {e}")
            import traceback
            traceback.print_exc()
            raise
    
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
    
    def get_player_info(self, player_name):
        try:
            master_df = pd.read_csv('models/NBA_Master_Stats.csv')
            player_data = master_df[master_df['Player'] == player_name].iloc[0]
            return player_data['Team'], player_data['Position']
        except:
            return None, None
    
    def is_valid_number(self, value):
        """Check if value is a valid number (not NaN, not None, not inf)"""
        if value is None:
            return False
        if isinstance(value, float):
            return not (math.isnan(value) or math.isinf(value))
        return True
    
    def predict(self, player_name, opponent, minutes):
        try:
            team, position = self.get_player_info(player_name)
            
            if not team or not position:
                print(f"❌ Could not find team/position for {player_name}")
                return {
                    'success': False,
                    'error': f'Could not find team/position data for {player_name}'
                }
            
            X = self.create_feature_vector(player_name, team, opponent, position, minutes)
            
            predictions = {}
            for stat in self.stat_columns:
                try:
                    # Check if model is ensemble or single
                    if isinstance(self.models[stat], dict):
                        # Old ensemble format (RF + GB)
                        if 'random_forest' in self.models[stat]:
                            rf_pred = self.models[stat]['random_forest'].predict(X)[0]
                            gb_pred = self.models[stat]['gradient_boosting'].predict(X)[0]
                            pred = (rf_pred + gb_pred) / 2
                        elif 'rf' in self.models[stat]:
                            rf_pred = self.models[stat]['rf'].predict(X)[0]
                            gb_pred = self.models[stat]['gb'].predict(X)[0]
                            pred = (rf_pred + gb_pred) / 2
                        else:
                            print(f"❌ Unknown dict format for {stat}: {self.models[stat].keys()}")
                            return {
                                'success': False,
                                'error': f'Unknown model format for {stat}'
                            }
                    else:
                        # New single model format (RF only)
                        pred = self.models[stat].predict(X)[0]
                    
                    # Validate the prediction
                    if not self.is_valid_number(pred):
                        print(f"❌ Invalid prediction for {stat}: {pred}")
                        return {
                            'success': False,
                            'error': f'Invalid prediction for {stat}'
                        }
                    
                    predictions[stat] = round(float(pred), 2)
                except Exception as e:
                    print(f"❌ Error predicting {stat} for {player_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    return {
                        'success': False,
                        'error': f'Error predicting {stat}: {str(e)}'
                    }
            
            return {
                'success': True,
                'player': player_name,
                'team': team,
                'opponent': opponent,
                'position': position,
                'minutes': float(minutes),
                'projections': predictions
            }
        except Exception as e:
            print(f"❌ Error in predict for {player_name}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_typical_team_minutes(self, team):
        """Get typical minute distribution for a team from NBA_Master_Stats.csv"""
        try:
            master_df = pd.read_csv('models/NBA_Master_Stats.csv')
            # Filter for this team and get unique players with their minutes
            team_players = master_df[master_df['Team'] == team].copy()
            
            # Group by player and get their typical minutes (use max or mean across scenarios)
            team_roster = {}
            for player_name in team_players['Player'].unique():
                player_rows = team_players[team_players['Player'] == player_name]
                
                # Use the max minutes across scenarios (represents their typical role)
                typical_mins = player_rows['Minutes'].max()
                
                if typical_mins >= 15 and player_name in self.player_averages:
                    # Get the row with max minutes for stats
                    main_row = player_rows.loc[player_rows['Minutes'].idxmax()]
                    
                    team_roster[player_name] = {
                        'typical_minutes': float(typical_mins),
                        'stats': self.player_averages[player_name],
                        'master_stats': {
                            'Points': float(main_row['Points']),
                            'Rebounds': float(main_row['Rebounds']),
                            'Assists': float(main_row['Assists']),
                            'Steals': float(main_row['Steals']),
                            'Blocks': float(main_row['Blocks']),
                            'Three Pointers Made': float(main_row['Three Pointers Made'])
                        }
                    }
            
            return team_roster
        except Exception as e:
            print(f"Error getting typical team minutes: {e}")
            import traceback
            traceback.print_exc()
            return {}
    

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
            'IND': 1.25,  'CLE': 1.25,  # Severe over-projectors
            'ATL': 1.30, 'BKN': 1.30, 'DAL': 1.30, 'LAC': 1.30, 'LAL': 1.30, 'WAS': 1.30,  # Moderate
        }

    def calculate_usage_adjustments(self, team, projected_players_dict):
        """
        IMPROVED: Calculate usage adjustments with team-specific caps and smarter detection
        Based on 39 days of historical validation data
        """
        
        # Get team-specific cap from learned parameters (self-updating!)
        max_boost = self.team_caps.get(team, 1.40)
        
        try:
            typical_roster = self.get_typical_team_minutes(team)
            
            if not typical_roster:
                return {}
            
            # Find significant missing players (20+ mins typically - HIGH/MEDIUM impact only)
            missing_players = {}
            for player_name, player_data in typical_roster.items():
                if player_name not in projected_players_dict and player_data['typical_minutes'] >= 20:
                    missing_players[player_name] = player_data
            
            if not missing_players:
                return {}
            
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
            
            print(f"\n🚨 {team} USAGE ADJUSTMENT:")
            print(f"Missing: {', '.join(missing_players.keys())}")
            print(f"Missing production: {missing_production['Points']:.1f} pts, {missing_production['Rebounds']:.1f} reb, {missing_production['Assists']:.1f} ast")
            print(f"Missing minutes: {total_missing_minutes:.1f}")
            print(f"Team boost cap: {max_boost:.2f} ({int((max_boost-1)*100)}%)")
            
            # First, try to find historical patterns for this exact situation
            missing_player_names = list(missing_players.keys())
            active_player_names = list(projected_players_dict.keys())
            
            historical_adjustments = self.pattern_matcher.find_similar_situation(
                team, 
                missing_player_names, 
                active_player_names
            )
            
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
                
                # Reduced efficiency factors (from validation)
                efficiency = 0.65 if is_replacement else 0.55
                
                # Calculate multipliers
                multipliers = {}
                
                # Check if we have historical pattern for this player
                if player_name in historical_adjustments:
                    # Use historical pattern multiplier
                    pattern_multiplier = historical_adjustments[player_name]
                    for stat in missing_production.keys():
                        multipliers[stat] = pattern_multiplier
                    print(f"   📊 Using historical pattern for {player_name}: {pattern_multiplier:.2f}x")
                else:
                    # Fall back to generic calculation
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
                        'share': total_share
                    }
                    
                    boost_pct = int((max(multipliers.values()) - 1) * 100)
                    role = "REPLACEMENT" if is_replacement else f"+{projected_mins-typical_mins:.1f} mins"
                    print(f"✅ {player_name} ({role}): {total_share*100:.1f}% share of production (max {boost_pct}% boost)")
            
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
        
        # Group players by team to calculate usage adjustments
        teams_dict = {}
        for player_data in dfs_data:
            team = player_data['team']
            if team not in teams_dict:
                teams_dict[team] = {}
            teams_dict[team][player_data['player']] = player_data['minutes']
        
        # Calculate usage adjustments for each team
        all_adjustments = {}
        for team, players in teams_dict.items():
            team_adjustments = self.calculate_usage_adjustments(team, players)
            all_adjustments.update(team_adjustments)
        
        # Generate projections with adjustments
        for player_data in dfs_data:
            player_name = player_data['player']
            opponent = player_data['opponent']
            minutes = player_data['minutes']
            
            result = self.predict(player_name, opponent, minutes)
            
            if result['success']:
                try:
                    proj = result['projections']
                    
                    # Apply usage adjustments if player has them
                    if player_name in all_adjustments:
                        adjustment = all_adjustments[player_name]
                        multipliers = adjustment.get('multipliers', {})
                        
                        print(f"\n📈 Boosting {player_name}:")
                        for stat in ['Points', 'Rebounds', 'Assists', 'Steals', 'Blocks', 'Three Pointers Made']:
                            if stat in multipliers and stat in proj:
                                original = proj[stat]
                                multiplier = multipliers[stat]
                                proj[stat] = original * multiplier
                                print(f"   {stat}: {original:.1f} → {proj[stat]:.1f} ({(multiplier-1)*100:.1f}% boost)")
                        
                        # Recalculate PRA
                        proj['PRA'] = proj['Points'] + proj['Rebounds'] + proj['Assists']
                    
                    # Validate all projection values
                    valid = True
                    for key, value in proj.items():
                        if not self.is_valid_number(value):
                            valid = False
                            break
                    
                    if valid:
                        projections.append({
                            'player': str(player_name),
                            'team': str(result['team']),
                            'opponent': str(opponent),
                            'position': str(result['position']),
                            'minutes': float(minutes),
                            'points': float(proj['Points']),
                            'rebounds': float(proj['Rebounds']),
                            'assists': float(proj['Assists']),
                            'three_pointers_made': float(proj['Three Pointers Made']),
                            'steals': float(proj['Steals']),
                            'blocks': float(proj['Blocks']),
                            'turnovers': float(proj['Turnovers']),
                            'pra': float(proj['PRA']),
                            'usage_boosted': player_name in all_adjustments
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
            print(f"Skipped {len(skipped)} players")
        
        return projections

projection_system = NBAProjectionSystem()

@app.route('/')
def index():
    return render_template('index.html', 
                         players=projection_system.players_list,
                         teams=projection_system.teams_list)

@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.json
        player = data.get('player')
        opponent = data.get('opponent')
        minutes = float(data.get('minutes', 30))
        
        if not player or not opponent:
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        result = projection_system.predict(player, opponent, minutes)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
        data = request.json
        projections = data.get('projections', [])
        
        df_data = []
        for i, proj in enumerate(projections):
            name_parts = proj['player'].split()
            df_data.append({
                'id': i + 1,
                'name': proj['player'],
                'first_name': name_parts[0] if name_parts else proj['player'],
                'last_name': name_parts[-1] if len(name_parts) > 1 else '',
                'position': proj['position'],
                'team': proj['team'],
                'three_pointers_made': proj['three_pointers_made'],
                'assists': proj['assists'],
                'blocks': proj['blocks'],
                'double_double': '',
                'points': proj['points'],
                'rebounds': proj['rebounds'],
                'steals': proj['steals'],
                'triple_double': '',
                'turnovers': proj['turnovers'],
                'fd_points': '',
                'dk_points': ''
            })
        
        df = pd.DataFrame(df_data)
        
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
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/players')
def get_players():
    return jsonify(projection_system.players_list)

@app.route('/api/teams')
def get_teams():
    return jsonify(projection_system.teams_list)

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
