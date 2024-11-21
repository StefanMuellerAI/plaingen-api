#!/bin/bash

# Farben für bessere Lesbarkeit
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Funktion zum Anzeigen von Fortschritt
progress() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Root-Rechte prüfen
if [ "$EUID" -ne 0 ]; then 
    echo "Bitte als root ausführen oder sudo verwenden"
    exit 1
fi

# Service User erstellen
progress "Erstelle Service User..."
useradd -m -s /bin/bash plaingen
usermod -aG sudo plaingen

# System Updates
progress "System wird aktualisiert..."
apt update && apt upgrade -y

# Notwendige Pakete installieren
progress "Installiere benötigte Pakete..."
apt install -y python3.10 python3.10-venv python3-pip nginx certbot python3-certbot-nginx git supervisor

# Firewall Setup
progress "Konfiguriere Firewall..."
ufw allow 'Nginx Full'
ufw allow OpenSSH
ufw --force enable

# Projektverzeichnis erstellen
progress "Erstelle Projektverzeichnis..."
mkdir -p /opt/plaingen-api
chown plaingen:plaingen /opt/plaingen-api

# Als plaingen-user ausführen
su - plaingen << 'EOF'
cd /opt/plaingen-api
git clone https://github.com/StefanMuellerAI/plaingen-api.git .
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn[standard] python-dotenv pyyaml slowapi crewai openai httpx async-timeout pydantic
pip install -r requirements.txt
EOF

# ENV Setup
progress "Erstelle .env Datei..."
cat > /opt/plaingen-api/.env << EOF
# OpenAI
OPENAI_API_KEY=
OPENAI_ORGANIZATION=

# Serper (Google Search API)
SERPER_API_KEY=

# Security
API_KEY=
EOF

# Berechtigungen für .env setzen
chown plaingen:plaingen /opt/plaingen-api/.env
chmod 600 /opt/plaingen-api/.env

# Interaktive Eingabe der API Keys
echo -e "${BLUE}Bitte geben Sie die notwendigen API Keys ein:${NC}"
read -p "OpenAI API Key: " openai_key
read -p "OpenAI Organization ID: " openai_org
read -p "Serper API Key: " serper_key
read -p "API Security Key: " api_key

# API Keys in .env einfügen
sed -i "s/OPENAI_API_KEY=/OPENAI_API_KEY=${openai_key}/" /opt/plaingen-api/.env
sed -i "s/OPENAI_ORGANIZATION=/OPENAI_ORGANIZATION=${openai_org}/" /opt/plaingen-api/.env
sed -i "s/SERPER_API_KEY=/SERPER_API_KEY=${serper_key}/" /opt/plaingen-api/.env
sed -i "s/API_KEY=/API_KEY=${api_key}/" /opt/plaingen-api/.env

# Systemd Service erstellen
progress "Erstelle Systemd Service..."
cat > /etc/systemd/system/plaingen-api.service << 'EOF'
[Unit]
Description=PlainGen API Service
After=network.target

[Service]
User=plaingen
Group=plaingen
WorkingDirectory=/opt/plaingen-api
Environment="PATH=/opt/plaingen-api/venv/bin"
ExecStart=/opt/plaingen-api/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Nginx Konfiguration
progress "Konfiguriere Nginx..."
cat > /etc/nginx/sites-available/api.easiergen.com << 'EOF'
server {
    server_name api.easiergen.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        
        # Security headers
        add_header X-Frame-Options "SAMEORIGIN";
        add_header X-XSS-Protection "1; mode=block";
        add_header X-Content-Type-Options "nosniff";
        add_header Referrer-Policy "no-referrer-when-downgrade";
        add_header Content-Security-Policy "default-src 'self';";
        
        # Rate limiting
        limit_req zone=one burst=10 nodelay;
        limit_req_zone $binary_remote_addr zone=one:10m rate=10r/s;
    }

    # Logging
    access_log /var/log/nginx/api.easiergen.com-access.log;
    error_log /var/log/nginx/api.easiergen.com-error.log;
}
EOF

# Nginx Site aktivieren
ln -s /etc/nginx/sites-available/api.easiergen.com /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# SSL Zertifikat einrichten
progress "Richte SSL-Zertifikat ein..."
read -p "Bitte geben Sie eine E-Mail-Adresse für das SSL-Zertifikat ein: " ssl_email
certbot --nginx -d api.easiergen.com --non-interactive --agree-tos --email $ssl_email

# Log Rotation einrichten
cat > /etc/logrotate.d/plaingen-api << 'EOF'
/var/log/nginx/api.easiergen.com-*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 `cat /var/run/nginx.pid`
    endscript
}
EOF

# Services starten
progress "Starte Services..."
systemctl daemon-reload
systemctl enable plaingen-api
systemctl start plaingen-api
systemctl restart nginx

# Backup-Verzeichnis erstellen
mkdir -p /var/backups/plaingen-api
chown plaingen:plaingen /var/backups/plaingen-api

# Backup-Script erstellen
cat > /opt/plaingen-api/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/plaingen-api"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
tar -czf $BACKUP_DIR/plaingen_api_$TIMESTAMP.tar.gz /opt/plaingen-api
find $BACKUP_DIR -type f -mtime +7 -delete
EOF

chmod +x /opt/plaingen-api/backup.sh
chown plaingen:plaingen /opt/plaingen-api/backup.sh

# Backup Cron Job einrichten
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/plaingen-api/backup.sh") | crontab -

# Abschluss
progress "Installation abgeschlossen!"
echo -e "${GREEN}Die API sollte nun unter https://api.easiergen.com erreichbar sein${NC}"
echo -e "${GREEN}Tägliche Backups werden um 3 Uhr morgens erstellt${NC}"
echo -e "${GREEN}Logs finden Sie unter /var/log/nginx/${NC}"
echo -e "${BLUE}Bitte stellen Sie sicher, dass der DNS-Eintrag für api.easiergen.com korrekt gesetzt ist${NC}" 