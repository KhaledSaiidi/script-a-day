##  retrieve SSL certificate for a given domain, extracts expiration date of the certificate, Compares the expiration date to today
##  If the certificate expires within 30 days, logs a warning message and triggers an alert

#!/bin/bash
trigger_alert() {
    local domain=$1
    local days_left=$2
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ALERT: SSL certificate for $domain is expiring in $days_left days." >> "$LOG_FILE"
    # mail -s "SSL Certificate Expiry Warning for $domain" admin@example.com <<< "The SSL certificate for $domain is expiring in $days_left days."
}

# Check if domain is passed, -z -> check if string is empty
if [ -z "$1" ]; then
    # $0 represents the name of the script itself
    echo "Usage: $0 <domain>"
    exit 1
fi

DOMAIN=$1
LOG_FILE="/var/log/ssl_certificate_check.log"
EXPIRY_THRESHOLD=30  # Days before expiry to trigger an alert

# Get the expiration date of the SSL certificate (in seconds since 1970-01-01):
        # 1) openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null --> creates a connection to the domain's SSL server, 
        #    retrieves the certificate, and ignores any connection errors.
        # 2) openssl x509 -noout -enddate --> Extracts the expiration date, -noout: Prevents openssl from printing the entire certificate
        # 3) sed 's/notAfter=//' Replaces "notAfter=" with nothing to get the expiration date only (exp: May 10 12:34:56 2025 GMT)
        # 0) Without "echo |" the openssl s_client command would just sit there waiting for user input after establishing the connection 
        #    for that we give it a empty echo so the openssl not have to manually exit or close the connection
expiration_date=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate | sed 's/notAfter=//')



# Convert expiration date to seconds since 1970-01-01
expiration_date_seconds=$(date -d "$expiration_date" +%s)

# Get the current date in seconds since 1970-01-01
current_date_seconds=$(date +%s)

# Calculate days left until expiration
days_left=$(( (expiration_date_seconds - current_date_seconds) / 86400 ))

if [ "$days_left" -le "$EXPIRY_THRESHOLD" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: SSL certificate for $DOMAIN expires in $days_left days." >> "$LOG_FILE"
    trigger_alert "$DOMAIN" "$days_left"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - OK: SSL certificate for $DOMAIN is valid for $days_left more days." >> "$LOG_FILE"
fi

exit 0

