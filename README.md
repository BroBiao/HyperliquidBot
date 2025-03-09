# HyperliquidBot
---

## Installation
`pip3 install -r requirements.txt`

## Configuration
- Set the public key (main wallet address) as the `account_address` in config.json.
- Set your private key (API private key) as the `secret_key` in config.json.
- Set `BOT_TOKEN` and `CHAT_ID` in .env.
- [Optional] Modify the trading parameters in grid.py.
- Modify `dryRun` from `True` to `False` in grid.py.

## Usage
#### Run in Terminal
`Python3 grid.py`

#### Run as systemd service
```
[Unit]
Description=Hyperliquid Grid Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/HyperliquidBot
ExecStart=/usr/bin/python3 -u /home/ubuntu/HyperliquidBot/grid.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```