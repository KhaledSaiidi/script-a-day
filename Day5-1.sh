# Write a Bash script that analyzes a web server log file and provides a summary of the following:
#       Total number of requests.
#       Number of unique IP addresses.
#       The most requested URL.
#       The total number of 404 errors (Page Not Found).
#       A report of the top 5 most active IP addresses.

#       common Apache log format: 127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326

#!/bin/bash

function check_file {
    if [[ ! -f $1 ]]; then
        echo "Error: File not found!"
        exit 1
    fi
}

function analyze_log {
    local file=$1
    local total_requests=$(wc -l < "$file")
    local unique_ips=$(awk '{print $1}' "$file" | sort -u | wc -l)
    local most_requested_url=$(awk '{print $5}' "$file" | sed 's/^"[^ ]* //; s/ HTTP\/.*$//' | sort | uniq -c | sort -nr | head -n 1 | awk '{print $2}')
    local total_404_errors=$(grep -c '404' "$file")
    local top_ips=$(awk '{print $1}' "$file" | sort | uniq -c | sort -nr | head -n 5)


    echo "Total Requests: $total_requests"
    echo "Unique IP Addresses: $unique_ips"
    echo "Most Requested URL: $most_requested_url"
    echo "Total 404 Errors: $total_404_errors"
    echo "Top 5 Active IP Addresses:"
    echo "$top_ips"

}


if [[ $# -ne 1 ]]; then
    echo "Usage: $0 needs a logfile as an arg to analyze"
    exit 1
fi

logfile=$1
check_file "$logfile"
analyze_log "$logfile"
