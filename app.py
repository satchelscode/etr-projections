from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import pickle
import os
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
                predictions[stat] = round((rf_pred + gb_pred) / 2, 2)
            
            return {
                'success': True,
                'player': player_name,
                'team': team,
                'opponent': opponent,
                'position': position,
                'minutes': minutes,
                'projections': predictions
            }
        except Exception as e:
            print(f"Error in predict: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def parse_rotowire_csv(self, file_content):
        try:
            df = pd.read_csv(StringIO(file_content), encoding='utf-8-sig')
            print(f"RotoWire CSV columns: {df.columns.tolist()}")
            print(f"RotoWire CSV shape: {df.shape}")
            
            players_data = []
            for _, row in df.iterrows():
                try:
                    minutes = float(row.get('MIN', 0))
                    if pd.notna(minutes) and minutes > 0:
                        players_data.append({
                            'player': str(row['NAME']).strip(),
                            'team': str(row['Team']).strip(),
                            'opponent': str(row['OPP']).strip(),
                            'rotowire_min': minutes
                        })
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue
            
            print(f"Parsed {len(players_data)} players from RotoWire")
            return players_data
            
        except Exception as e:
            print(f"Error parsing RotoWire CSV: {e}")
            return []
    
    def generate_daily_projections(self, rotowire_data):
        projections = []
        
        print(f"Generating projections for {len(rotowire_data)} players...")
        
        for rw_player in rotowire_data:
            player_name = rw_player['player']
            opponent = rw_player['opponent']
            minutes = rw_player['rotowire_min']
            
            result = self.predict(player_name, opponent, minutes)
            
            if result['success']:
                proj = result['projections']
                projections.append({
                    'player': player_name,
                    'team': result['team'],
                    'opponent': opponent,
                    'position': result['position'],
                    'minutes': minutes,
                    'points': proj['Points'],
                    'rebounds': proj['Rebounds'],
                    'assists': proj['Assists'],
                    'three_pointers_made': proj['Three Pointers Made'],
                    'steals': proj['Steals'],
                    'blocks': proj['Blocks'],
                    'turnovers': proj['Turnovers'],
                    'pra': proj['PRA']
                })
            else:
                print(f"Failed to project {player_name}: {result.get('error')}")
        
        print(f"Successfully generated {len(projections)} projections")
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
        
        rotowire_file = request.files.get('rotowire')
        
        if not rotowire_file:
            return jsonify({'success': False, 'error': 'RotoWire CSV file is required'})
        
        print(f"Processing file: {rotowire_file.filename}")
        
        rotowire_content = rotowire_file.read().decode('utf-8')
        rotowire_data = projection_system.parse_rotowire_csv(rotowire_content)
        
        if not rotowire_data:
            return jsonify({'success': False, 'error': 'No valid data found in RotoWire file'})
        
        projections = projection_system.generate_daily_projections(rotowire_data)
        
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
