# NBA Player Projections

AI-powered NBA player statistical projections based on opponent matchups and historical performance.

## Features

- 🎯 Accurate player stat projections (98%+ R² scores)
- 📊 Predicts: Points, Rebounds, Assists, 3PM, Steals, Blocks, Turnovers, PRA
- 🏀 Trained on 3,300+ historical projections
- 🎨 Clean, responsive web interface
- ⚡ Real-time predictions

## Model Performance

| Stat | R² Score |
|------|----------|
| Points | 98.4% |
| Assists | 97.5% |
| Rebounds | 98.2% |
| PRA | 98.7% |

## How It Works

1. **Input**: Enter player name, team, opponent, position, and projected minutes
2. **Analysis**: Model considers:
   - Player's historical performance
   - Opponent's defensive strength
   - Team tendencies
   - Expected playing time
3. **Output**: Complete projected stat line

## Deployment to Render

### Prerequisites
- GitHub account
- Render account (free tier works)

### Step 1: Prepare Your Repository

1. **Create models directory**:
   ```bash
   mkdir models
   ```

2. **Copy your trained models**:
   - Place these files in the `models/` directory:
     - `nba_models.pkl`
     - `opponent_adjustments.csv`
     - `player_averages.csv`
     - `team_averages.csv`

3. **Project structure should look like**:
   ```
   nba-projections/
   ├── app.py
   ├── requirements.txt
   ├── runtime.txt
   ├── Procfile
   ├── models/
   │   ├── nba_models.pkl
   │   ├── opponent_adjustments.csv
   │   ├── player_averages.csv
   │   └── team_averages.csv
   ├── templates/
   │   └── index.html
   └── static/
       ├── css/
       │   └── style.css
       └── js/
           └── script.js
   ```

### Step 2: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: NBA projection app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/nba-projections.git
git push -u origin main
```

### Step 3: Deploy on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `nba-projections` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free

5. Click **"Create Web Service"**

6. Wait for deployment (5-10 minutes)

7. Your app will be live at: `https://nba-projections.onrender.com`

### Important Notes

⚠️ **File Size Limits**: 
- Free tier has 512MB limit
- Your models directory should be under 100MB
- If models are too large, consider using Git LFS

⚠️ **Cold Starts**: 
- Free tier spins down after inactivity
- First request after inactivity may take 30-60 seconds

## Local Development

Run locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run app
python app.py
```

Visit: `http://localhost:5000`

## Updating Models

To update with new data:

1. Add new projections to `NBA_Master_Stats.csv`
2. Retrain models: `python nba_projection_model.py`
3. Copy new model files to `models/` directory
4. Push to GitHub
5. Render will auto-deploy

## API Endpoints

- `GET /` - Web interface
- `POST /predict` - Get projections (JSON)
- `GET /api/players` - List all players
- `GET /api/teams` - List all teams
- `GET /health` - Health check

## Tech Stack

- **Backend**: Flask (Python)
- **ML Models**: Random Forest + Gradient Boosting (scikit-learn)
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Render
- **Data**: 3,300+ historical player projections

## Support

For issues or questions, open an issue on GitHub.

## License

MIT License
