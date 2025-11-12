from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import pickle
import os

app = Flask(__name__)

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
            # Load models
            with open('models/nba_models.pkl', 'rb') as f:
                self.models = pickle.load(f)
            
            # Load opponent adjustments
            self.opponent_adjustments = pd.read_csv('models/opponent_adjustments.csv', index_col=0).to_dict()
            
            # Load player averages
            player_avg_df = pd.read_csv('models/player_averages.csv', index_col=0)
            self.player_averages = player_avg_df.to_dict('index')
            self.players_list = sorted(list(self.player_averages.keys()))
            
            # Load team averages
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
        
        # Player historical averages
        if player_name in self.player_averages:
            for stat in self.stat_columns:
                feature_vec.append(self.player_averages[player_name].get(stat, 0))
        else:
            feature_vec.extend([0] * len(self.stat_columns))
        
        # Team averages
        if team in self.team_averages:
            for stat in self.stat_columns:
                feature_vec.append(self.team_averages[team].get(stat, 0))
        else:
            feature_vec.extend([0] * len(self.stat_columns))
        
        # Opponent adjustments
        for stat in self.stat_columns:
            if opponent in self.opponent_adjustments[stat]:
                feature_vec.append(self.opponent_adjustments[stat][opponent])
            else:
                feature_vec.append(0)
        
        # Position encoding
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        for pos in positions:
            feature_vec.append(1 if position == pos else 0)
        
        # Minutes
        feature_vec.append(minutes)
        
        return np.array([feature_vec])
    
    def predict(self, player_name, team, opponent, position, minutes):
        """Make prediction for a player"""
        try:
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
    """API endpoint for predictions"""
    try:
        data = request.json
        
        player = data.get('player')
        team = data.get('team')
        opponent = data.get('opponent')
        position = data.get('position', 'SG')
        minutes = float(data.get('minutes', 30))
        
        if not all([player, team, opponent]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            })
        
        result = projection_system.predict(player, team, opponent, position, minutes)
        return jsonify(result)
        
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
