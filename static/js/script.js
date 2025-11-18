document.addEventListener('DOMContentLoaded', function() {
    // Single player projection
    const form = document.getElementById('projectionForm');
    const resultsSection = document.getElementById('resultsSection');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const errorMessage = document.getElementById('errorMessage');

    // Daily projections
    const dfsInput = document.getElementById('dfsFile');
    const generateDailyBtn = document.getElementById('generateDailyBtn');
    const dailyResults = document.getElementById('dailyResults');
    const projectionsTableBody = document.getElementById('projectionsTableBody');
    const downloadBtn = document.getElementById('downloadBtn');
    
    let currentProjections = [];

    // File name display
    dfsInput.addEventListener('change', function(e) {
        const fileName = e.target.files[0]?.name || 'No file selected';
        document.getElementById('dfsFileName').textContent = fileName;
    });

    // Single player prediction
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const formData = {
            player: document.getElementById('player').value,
            opponent: document.getElementById('opponent').value,
            minutes: document.getElementById('minutes').value
        };

        if (!formData.player || !formData.opponent) {
            showError('Please fill in all required fields');
            return;
        }

        resultsSection.style.display = 'none';
        errorMessage.style.display = 'none';
        loadingSpinner.style.display = 'block';

        try {
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const data = await response.json();
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
        document.getElementById('playerName').textContent = data.player;
        document.getElementById('matchupInfo').textContent = 
            `${data.team} vs ${data.opponent} | ${data.position} | ${data.minutes} minutes`;

        const projections = data.projections;
        document.getElementById('stat-pra').textContent = projections.PRA || '0';
        document.getElementById('stat-points').textContent = projections.Points || '0';
        document.getElementById('stat-rebounds').textContent = projections.Rebounds || '0';
        document.getElementById('stat-assists').textContent = projections.Assists || '0';
        document.getElementById('stat-threes').textContent = projections['Three Pointers Made'] || '0';
        document.getElementById('stat-steals').textContent = projections.Steals || '0';
        document.getElementById('stat-blocks').textContent = projections.Blocks || '0';
        document.getElementById('stat-turnovers').textContent = projections.Turnovers || '0';

        resultsSection.style.display = 'block';
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Generate daily projections
    generateDailyBtn.addEventListener('click', async function() {
        const dfsFile = dfsInput.files[0];

        if (!dfsFile) {
            showError('Please upload the NBA DFS Projections CSV file');
            return;
        }

        const formData = new FormData();
        formData.append('dfs_projections', dfsFile);

        errorMessage.style.display = 'none';
        loadingSpinner.style.display = 'block';
        dailyResults.style.display = 'none';

        try {
            const response = await fetch('/generate_daily', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            loadingSpinner.style.display = 'none';

            if (data.success) {
                currentProjections = data.projections;
                displayDailyProjections(data.projections);
                document.getElementById('projectionsCount').textContent = 
                    `${data.count} Projections Generated`;
                dailyResults.style.display = 'block';
                dailyResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else {
                showError(data.error || 'An error occurred while generating daily projections');
            }

        } catch (error) {
            loadingSpinner.style.display = 'none';
            showError('Network error: ' + error.message);
        }
    });

    function displayDailyProjections(projections) {
        projectionsTableBody.innerHTML = '';

        projections.forEach(proj => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${proj.player}</strong></td>
                <td>${proj.team}</td>
                <td>${proj.opponent}</td>
                <td>${proj.position}</td>
                <td>${parseFloat(proj.minutes).toFixed(1)}</td>
                <td>${parseFloat(proj.points).toFixed(2)}</td>
                <td>${parseFloat(proj.rebounds).toFixed(2)}</td>
                <td>${parseFloat(proj.assists).toFixed(2)}</td>
                <td>${parseFloat(proj.three_pointers_made).toFixed(2)}</td>
                <td>${parseFloat(proj.steals).toFixed(2)}</td>
                <td>${parseFloat(proj.blocks).toFixed(2)}</td>
                <td>${parseFloat(proj.turnovers).toFixed(2)}</td>
                <td class="stats-highlight">${parseFloat(proj.pra).toFixed(2)}</td>
            `;
            projectionsTableBody.appendChild(row);
        });
    }

    // Player search functionality
    const playerSearch = document.getElementById('playerSearch');
    if (playerSearch) {
        playerSearch.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const rows = projectionsTableBody.getElementsByTagName('tr');
            
            Array.from(rows).forEach(row => {
                const playerName = row.cells[0].textContent.toLowerCase();
                if (playerName.includes(searchTerm)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }

    // Download projections as CSV
    downloadBtn.addEventListener('click', async function() {
        if (currentProjections.length === 0) {
            showError('No projections to download');
            return;
        }

        try {
            const response = await fetch('/download_projections', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ projections: currentProjections })
            });

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'nba_daily_projections.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (error) {
            showError('Error downloading file: ' + error.message);
        }
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});
