document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('projectionForm');
    const resultsSection = document.getElementById('resultsSection');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const errorMessage = document.getElementById('errorMessage');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Get form values (no team or position needed!)
        const formData = {
            player: document.getElementById('player').value,
            opponent: document.getElementById('opponent').value,
            minutes: document.getElementById('minutes').value
        };

        console.log('Sending request:', formData); // Debug log

        // Validate
        if (!formData.player || !formData.opponent) {
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
            console.log('Received response:', data); // Debug log

            // Hide loading
            loadingSpinner.style.display = 'none';

            if (data.success) {
                displayResults(data);
            } else {
                showError(data.error || 'An error occurred while generating projections');
            }

        } catch (error) {
            console.error('Error:', error); // Debug log
            loadingSpinner.style.display = 'none';
            showError('Network error: ' + error.message);
        }
    });

    function displayResults(data) {
        console.log('Displaying results:', data); // Debug log
        
        // Update player info
        document.getElementById('playerName').textContent = data.player;
        document.getElementById('matchupInfo').textContent = 
            `${data.team} vs ${data.opponent} | ${data.position} | ${data.minutes} minutes`;

        // Update stats
        const projections = data.projections;
        document.getElementById('stat-pra').textContent = projections.PRA || '0';
        document.getElementById('stat-points').textContent = projections.Points || '0';
        document.getElementById('stat-rebounds').textContent = projections.Rebounds || '0';
        document.getElementById('stat-assists').textContent = projections.Assists || '0';
        document.getElementById('stat-threes').textContent = projections['Three Pointers Made'] || '0';
        document.getElementById('stat-steals').textContent = projections.Steals || '0';
        document.getElementById('stat-blocks').textContent = projections.Blocks || '0';
        document.getElementById('stat-turnovers').textContent = projections.Turnovers || '0';

        // Show results with animation
        resultsSection.style.display = 'block';
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        console.log('Results displayed successfully'); // Debug log
    }

    function showError(message) {
        console.error('Showing error:', message); // Debug log
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});
