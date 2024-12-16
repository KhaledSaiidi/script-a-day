## SSL Certificate Expiration Monitoring
## Fetch the SSL certificate & Extract the expiration date of the certificate
## Calculate how many days remain until the certificate expires.
## Send an email alert and log a warning if the certificate is about to expire.

#!/bin/bash

DOMAIN="$1"
THRESHOLD=15
LOG_FILE="/var/log/ssl_check.log"
ALERT_EMAIL="devops_team@example.com"

if [[ -z "$DOMAIN" ]]; then
    echo "Usage: $0 <domain>"
    exit 1
fi

# Fetch the certificate expiration date using openssl
expiration_date=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null \
    | openssl x509 -noout -enddate | sed 's/notAfter=//')

if [[ -z "$expiration_date" ]]; then
    echo "$(date): ERROR - Could not retrieve SSL certificate expiration for $DOMAIN" >> "$LOG_FILE"
    exit 1
fi

# Convert expiration date to seconds since epoch
expiration_date_seconds=$(date -d "$expiration_date" +%s)
current_date_seconds=$(date +%s)

# Calculate days until expiration
days_until_expiration=$(( (expiration_date_seconds - current_date_seconds) / 86400 ))

if [[ $days_until_expiration -le $THRESHOLD ]]; then
    # Log a warning
    echo "$(date): WARNING - $DOMAIN SSL cert expires in $days_until_expiration days ($expiration_date)" >> "$LOG_FILE"
    
    # Send an alert email
    mail -s "SSL Certificate Expiring Soon for $DOMAIN" "$ALERT_EMAIL" <<EOF
The SSL certificate for $DOMAIN will expire in $days_until_expiration days (on $expiration_date).
Please renew the certificate to avoid service interruption.
EOF
else
    # Log that everything is normal
    echo "$(date): $DOMAIN SSL cert is fine, expires in $days_until_expiration days" >> "$LOG_FILE"
fi