apt update && apt upgrade -y
apt install -y python3
python3 --version
mkdir -p /opt/taskboard /var/log/taskboard

Файлы добавил через FileZilla

cat > /etc/systemd/system/taskboard.service <<'EOF'
[Unit]
Description=TaskBoard mock API + static
After=network.target

[Service]
Type=simple
User=taskboard
Group=taskboard
WorkingDirectory=/opt/taskboard
ExecStart=/opt/taskboard/.venv/bin/python3 mock_server.py 7755
Restart=always
RestartSec=3
StandardOutput=append:/var/log/taskboard/app.log
StandardError=append:/var/log/taskboard/err.log
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now taskboard
systemctl status taskboard


