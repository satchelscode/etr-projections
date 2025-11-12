document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('projectionForm');
    const resultsSection = document.getElementById('resultsSection');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const errorMessage = document.getElementById('errorMessage');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Get form values
        const formData = {
            player: document.getElementById('player').value,
            team: document.getElementById('team').value,
            opponent: document.getElementById('opponent').value,
            position: document.getElementById('position').value,
            minutes: document.getElementById('minutes').value
        };

        // Validate
        if (!formData.player || !formData.team || !formData.opponent) {
            showError('Please fill in all required fields');
            return;
        }

        // Hide results and errors, show loading
        resultsSection.style.display = 'none';
        errorMessage.style.display = 'none';
        loadingSpinner.style.display = 'block';

        try {
            // Make API request
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            // Hide loading
            loadingSpinner.style.display = 'none';

            if (data.success) {
                displayResults(data);
            } else {
                showError(data.error || 'An error occurred while generating projections');
            }

        } catch (error) {
            loadingSpinner.style.display = 'none';
            showError('Network error: ' + error.message);
        }
    });

    function displayResults(data) {
        // Update player info
        document.getElementById('playerName').textContent = data.player;
        document.getElementById('matchupInfo').textContent = 
            `${data.team} vs ${data.opponent} | ${data.position} | ${data.minutes} minutes`;

        // Update stats
        const projections = data.projections;
        document.getElementById('stat-pra').textContent = projections.PRA;
        document.getElementById('stat-points').textContent = projections.Points;
        document.getElementById('stat-rebounds').textContent = projections.Rebounds;
        document.getElementById('stat-assists').textContent = projections.Assists;
        document.getElementById('stat-threes').textContent = projections['Three Pointers Made'];
        document.getElementById('stat-steals').textContent = projections.Steals;
        document.getElementById('stat-blocks').textContent = projections.Blocks;
        document.getElementById('stat-turnovers').textContent = projections.Turnovers;

        // Show results with animation
        resultsSection.style.display = 'block';
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Auto-fill team when player is selected (if we know the player's team)
    document.getElementById('player').addEventListener('change', function() {
        // This could be enhanced to auto-select the player's team if needed
    });
});
