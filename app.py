from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import pickle
import os
from io import StringIO, BytesIO
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
        """Load all trained models and data"""
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
            print(f"✓ {len(self.players_list)} players in database")
            print(f"✓ {len(self.teams_list)} teams in database")
            
        except Exception as e:
            print(f"Error loading models: {e}")
            raise
    
    def create_feature_vector(self, player_name, team, opponent, position, minutes):
        """Create feature vector for prediction"""
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
        """Get player's team and position from the master data"""
        try:
            master_df = pd.read_csv('models/NBA_Master_Stats.csv')
            player_data = master_df[master_df['Player'] == player_name].iloc[0]
            return player_data['Team'], player_data['Position']
        except Exception as e:
            return None, None
    
    def predict(self, player_name, opponent, minutes):
        """Make prediction for a player"""
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
            return {
                'success': False,
                'error': str(e)
            }
    
    def parse_rotowire_csv(self, file_content):
        """Parse RotoWire CSV to extract player, team, opponent, and minutes"""
        df = pd.read_csv(StringIO(file_content), encoding='utf-8-sig')
        
        # RotoWire columns: NAME, Team, OPP, Pos, MIN, ...
        players_data = []
        for _, row in df.iterrows():
            if pd.notna(row.get('MIN')) and float(row.get('MIN', 0)) > 0:
                players_data.append({
                    'player': row['NAME'],
                    'team': row['Team'],
                    'opponent': row['OPP'],
                    'rotowire_min': float(row['MIN'])
                })
        
        return players_data
    
    def parse_basketball_monster_html(self, html_content):
        """Parse Basketball Monster HTML to extract player and minutes"""
        soup = BeautifulSoup(html_content, 'html.parser')
        players_data = {}
        
        # Find the table with lineup data
        table = soup.find('table', {'id': 'lineups'}) or soup.find('table')
        
        if table:
            for row in table.find_all('tr')[1:]:  # Skip header
                cells = row.find_all('td')
                if len(cells) >= 2:
                    player_cell = cells[0]
                    minutes_cell = cells[1] if len(cells) > 1 else None
                    
                    player_name = player_cell.get_text(strip=True)
                    if minutes_cell:
                        try:
                            minutes = float(minutes_cell.get_text(strip=True))
                            players_data[player_name] = minutes
                        except:
                            pass
        
        return players_data
    
    def generate_daily_projections(self, rotowire_data, basketball_monster_data):
        """Generate projections for all players"""
        projections = []
        
        for rw_player in rotowire_data:
            player_name = rw_player['player']
            opponent = rw_player['opponent']
            rw_min = rw_player['rotowire_min']
            
            # Get Basketball Monster minutes
            bm_min = basketball_monster_data.get(player_name, rw_min)
            
            # Average the two sources
            avg_minutes = round((rw_min + bm_min) / 2, 1)
            
            # Generate projection
            result = self.predict(player_name, opponent, avg_minutes)
            
            if result['success']:
                proj = result['projections']
                projections.append({
                    'player': player_name,
                    'team': result['team'],
                    'opponent': opponent,
                    'position': result['position'],
                    'minutes': avg_minutes,
                    'points': proj['Points'],
                    'rebounds': proj['Rebounds'],
                    'assists': proj['Assists'],
                    'three_pointers_made': proj['Three Pointers Made'],
                    'steals': proj['Steals'],
                    'blocks': proj['Blocks'],
                    'turnovers': proj['Turnovers'],
                    'pra': proj['PRA']
                })
        
        return projections

# Initialize the projection system
projection_system = NBAProjectionSystem()

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html', 
                         players=projection_system.players_list,
                         teams=projection_system.teams_list)

@app.route('/predict', methods=['POST'])
def predict():
    """API endpoint for single player predictions"""
    try:
        data = request.json
        
        player = data.get('player')
        opponent = data.get('opponent')
        minutes = float(data.get('minutes', 30))
        
        if not player or not opponent:
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            })
        
        result = projection_system.predict(player, opponent, minutes)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/generate_daily', methods=['POST'])
def generate_daily():
    """Generate projections for entire day"""
    try:
        rotowire_file = request.files.get('rotowire')
        basketball_monster_file = request.files.get('basketball_monster')
        
        if not rotowire_file:
            return jsonify({
                'success': False,
                'error': 'RotoWire CSV file is required'
            })
        
        # Parse RotoWire CSV
        rotowire_content = rotowire_file.read().decode('utf-8')
        rotowire_data = projection_system.parse_rotowire_csv(rotowire_content)
        
        # Parse Basketball Monster HTML (optional)
        basketball_monster_data = {}
        if basketball_monster_file:
            bm_content = basketball_monster_file.read().decode('utf-8')
            basketball_monster_data = projection_system.parse_basketball_monster_html(bm_content)
        
        # Generate projections
        projections = projection_system.generate_daily_projections(
            rotowire_data, 
            basketball_monster_data
        )
        
        return jsonify({
            'success': True,
            'projections': projections,
            'count': len(projections)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/download_projections', methods=['POST'])
def download_projections():
    """Download projections in specified format"""
    try:
        data = request.json
        projections = data.get('projections', [])
        
        # Create DataFrame in desired format
        df_data = []
        for i, proj in enumerate(projections):
            df_data.append({
                'id': i + 1,
                'name': proj['player'],
                'first_name': proj['player'].split()[0] if ' ' in proj['player'] else proj['player'],
                'last_name': proj['player'].split()[-1] if ' ' in proj['player'] else '',
                'position': proj['position'],
                'team': proj['team'],
                'three_pointers_made': proj['three_pointers_made'],
                'assists': proj['assists'],
                'blocks': proj['blocks'],
                'double_double': '',  # Can calculate if needed
                'points': proj['points'],
                'rebounds': proj['rebounds'],
                'steals': proj['steals'],
                'triple_double': '',  # Can calculate if needed
                'turnovers': proj['turnovers'],
                'fd_points': '',  # Calculate FanDuel points if needed
                'dk_points': ''   # Calculate DraftKings points if needed
            })
        
        df = pd.DataFrame(df_data)
        
        # Convert to CSV
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
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/players')
def get_players():
    """Get list of all players"""
    return jsonify(projection_system.players_list)

@app.route('/api/teams')
def get_teams():
    """Get list of all teams"""
    return jsonify(projection_system.teams_list)

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
