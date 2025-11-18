from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import pickle
import os
import math
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
    
    def load_models(self):
        try:
            with open('models/nba_models.pkl', 'rb') as f:
                self.models = pickle.load(f)
            
            self.opponent_adjustments = pd.read_csv('models/opponent_adjustments.csv', index_col=0).to_dict()
            
            player_avg_df = pd.read_csv('models/player_averages.csv', index_col=0)
            self.player_averages = player_avg_df.to_dict('index')
            self.players_list = sorted(list(self.player_averages.keys()))
            
            team_avg_df = pd.read_csv('models/team_averages.csv', index_col=0)
            self.team_averages = team_avg_df.to_dict('index')
            self.teams_list = sorted(list(self.team_averages.keys()))
            
            print("✓ Models loaded successfully")
            
        except Exception as e:
            print(f"Error loading models: {e}")
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
        
        for stat in self.stat_columns:
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
                return {
                    'success': False,
                    'error': f'Could not find team/position data for {player_name}'
                }
            
            X = self.create_feature_vector(player_name, team, opponent, position, minutes)
            
            predictions = {}
            for stat in self.stat_columns:
                rf_pred = self.models[stat]['rf'].predict(X)[0]
                gb_pred = self.models[stat]['gb'].predict(X)[0]
                avg_pred = (rf_pred + gb_pred) / 2
                
                # Validate the prediction
                if not self.is_valid_number(avg_pred):
                    return {
                        'success': False,
                        'error': f'Invalid prediction for {stat}'
                    }
                
                predictions[stat] = round(float(avg_pred), 2)
            
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
            print(f"Error in predict for {player_name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_typical_team_minutes(self, team):
        """Get typical minute distribution for a team from player averages"""
        try:
            master_df = pd.read_csv('models/NBA_Master_Stats.csv')
            team_players = master_df[master_df['Team'] == team].copy()
            
            # Calculate typical minutes per game based on player averages
            team_roster = {}
            for _, player in team_players.iterrows():
                player_name = player['Player']
                if player_name in self.player_averages:
                    # Estimate minutes from their per-game stats (assuming 82 game season)
                    avg_stats = self.player_averages[player_name]
                    # Players with higher stats typically play more minutes
                    # Use PRA as a proxy for minutes (rough estimate)
                    estimated_mins = min(avg_stats.get('PRA', 0) * 1.5, 38)  # Cap at 38 mins
                    if estimated_mins >= 15:  # Only significant rotation players
                        team_roster[player_name] = {
                            'typical_minutes': estimated_mins,
                            'stats': avg_stats
                        }
            
            return team_roster
        except Exception as e:
            print(f"Error getting typical team minutes: {e}")
            return {}
    
    def calculate_usage_adjustments(self, team, projected_players_dict):
        """
        Calculate usage adjustments based on missing players
        
        Args:
            team: Team abbreviation
            projected_players_dict: Dict of {player_name: projected_minutes}
        
        Returns:
            Dict of {player_name: adjustment_multipliers}
        """
        try:
            # Get typical roster
            typical_roster = self.get_typical_team_minutes(team)
            
            if not typical_roster:
                return {}
            
            # Find significant missing players
            missing_players = {}
            for player_name, player_data in typical_roster.items():
                if player_name not in projected_players_dict and player_data['typical_minutes'] >= 20:
                    missing_players[player_name] = player_data
            
            if not missing_players:
                return {}
            
            # Calculate total missing production
            total_missing_minutes = sum(p['typical_minutes'] for p in missing_players.values())
            missing_production = {
                'Points': sum(p['stats'].get('Points', 0) for p in missing_players.values()),
                'Rebounds': sum(p['stats'].get('Rebounds', 0) for p in missing_players.values()),
                'Assists': sum(p['stats'].get('Assists', 0) for p in missing_players.values()),
                'Steals': sum(p['stats'].get('Steals', 0) for p in missing_players.values()),
                'Blocks': sum(p['stats'].get('Blocks', 0) for p in missing_players.values()),
                'Three Pointers Made': sum(p['stats'].get('Three Pointers Made', 0) for p in missing_players.values())
            }
            
            print(f"\n🚨 {team} USAGE ADJUSTMENT:")
            print(f"Missing: {', '.join(missing_players.keys())}")
            print(f"Missing production: {missing_production['Points']:.1f} pts, {missing_production['Rebounds']:.1f} reb, {missing_production['Assists']:.1f} ast")
            
            # Calculate adjustments for active players
            adjustments = {}
            total_extra_minutes = 0
            
            # Identify who's getting extra minutes (including new players)
            for player_name, proj_mins in projected_players_dict.items():
                if player_name in typical_roster:
                    # Existing player
                    typical_mins = typical_roster[player_name]['typical_minutes']
                    minute_increase = max(0, proj_mins - typical_mins)
                    
                    if minute_increase >= 3:  # Significant increase
                        total_extra_minutes += minute_increase
                        adjustments[player_name] = {
                            'minute_increase': minute_increase,
                            'proj_mins': proj_mins,
                            'is_replacement': False,
                            'typical_stats': typical_roster[player_name]['stats']
                        }
                else:
                    # New/replacement player getting significant minutes
                    if proj_mins >= 20:  # They're filling a significant role
                        total_extra_minutes += proj_mins * 0.7  # Count 70% as "extra" for replacement players
                        adjustments[player_name] = {
                            'minute_increase': proj_mins * 0.7,
                            'proj_mins': proj_mins,
                            'is_replacement': True,
                            'typical_stats': None
                        }
            
            # Redistribute production proportionally
            if total_extra_minutes > 0:
                for player_name, adj in adjustments.items():
                    share = adj['minute_increase'] / total_extra_minutes
                    
                    # Get baseline stats for this player
                    if adj['is_replacement']:
                        # For replacement players, use league average or small baseline
                        baseline_stats = {
                            'Points': 8.0,
                            'Rebounds': 3.0,
                            'Assists': 2.0,
                            'Steals': 0.5,
                            'Blocks': 0.3,
                            'Three Pointers Made': 1.0
                        }
                    else:
                        baseline_stats = adj['typical_stats']
                    
                    # Calculate boost multipliers (percentage boosts)
                    # Replacement players get higher boosts since they're literally replacing the missing player
                    boost_efficiency = 0.7 if adj['is_replacement'] else 0.6
                    
                    adj['multipliers'] = {}
                    for stat in ['Points', 'Rebounds', 'Assists', 'Steals', 'Blocks', 'Three Pointers Made']:
                        baseline = baseline_stats.get(stat, 1)
                        if baseline > 0:
                            boost = (share * missing_production[stat] * boost_efficiency) / baseline
                            adj['multipliers'][stat] = min(1.0 + boost, 1.5)  # Cap at 50% boost
                        else:
                            adj['multipliers'][stat] = 1.0
                    
                    if adj['is_replacement']:
                        print(f"✅ {player_name} (REPLACEMENT): {adj['proj_mins']:.1f} mins (covering {share*100:.1f}% of void)")
                    else:
                        print(f"✅ {player_name}: +{adj['minute_increase']:.1f} mins (covering {share*100:.1f}% of void)")
            
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
