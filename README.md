# Pizza Index Discord Alerter

🍕 A Python bot that monitors the [Pizza Index](https://www.pizzint.watch/) (DOUGHCON) and sends Discord alerts when conditions change.

## Features

- 📊 **DOUGHCON Monitoring**: Tracks threat level changes (1-5)
- 🏪 **Store Status Tracking**: Monitors pizza store OPEN/CLOSED/BUSY status
- 📈 **Spike Detection**: Alerts on unusual order activity
- 🔔 **Discord Notifications**: Rich embeds with color-coded alerts
- 🐳 **Docker Ready**: Containerized for easy deployment

## Quick Start

### Prerequisites
- Python 3.10+
- Discord Webhook URL

### Installation

```bash
# Clone repository
git clone https://github.com/your-repo/pizza-index-discord-alerter.git
cd pizza-index-discord-alerter

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Discord webhook URL
```

### Configuration

Edit `config.yaml` to customize:

```yaml
polling_interval_seconds: 300    # Check every 5 minutes
order_spike_threshold_percent: 30  # Alert on 30%+ activity increase
```

### Running

```bash
# Direct execution
python main.py

# With Docker
docker compose up -d
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DISCORD_WEBHOOK_URL` | Discord webhook endpoint | ✅ |
| `POLLING_INTERVAL` | Override config interval (seconds) | ❌ |
| `LOG_LEVEL` | Logging verbosity (DEBUG/INFO/WARNING) | ❌ |

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready releases |
| `develop` | Development and testing |

**Workflow:**
1. Feature branches → `develop`
2. `develop` → `main` (triggers production deployment)

## CI/CD

- **`ci.yml`**: Runs on `develop` - linting and tests
- **`deploy.yml`**: Runs on `main` - builds and deploys Docker image

## Alert Types

| Emoji | Alert Type | Description |
|-------|------------|-------------|
| 🚨 | DOUGHCON Change | Threat level increased |
| 📈 | Activity Spike | Order rate surge detected |
| 🔄 | Status Change | Store opened/closed |

## Project Structure

```
pizza-index-discord-alerter/
├── main.py              # Entry point
├── src/
│   ├── scraper.py       # Web scraping logic
│   ├── detector.py      # Change detection
│   ├── notifier.py      # Discord notifications
│   └── state.py         # State persistence
├── config.yaml          # Configuration
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/
    ├── ci.yml
    └── deploy.yml
```

## License

MIT
