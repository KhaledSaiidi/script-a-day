#!/bin/bash

# Script Name: json_cleaner.sh
# Description: Cleans, fixes, and formats JSON input using jsonrepair & jq.

if [ -z "$1" ]; then
    echo "❌ Error: No JSON input provided."
    echo "Usage: ./json_cleaner.sh 'JSON_BLOCK'"
    exit 1
fi

INPUT_JSON="$1"

CLEANED_JSON=$(echo "$INPUT_JSON" | sed 's/^[^{]*//')

if [[ "$CLEANED_JSON" == *"}"* ]]; then
    CLEANED_JSON=$(echo "$CLEANED_JSON" | sed 's/}[^}]*$/}/')
fi

QUOTE_COUNT=$(echo "$CLEANED_JSON" | grep -o '"' | wc -l)

if (( QUOTE_COUNT % 2 != 0 )); then
    echo "⚠ Warning: JSON has an unclosed double quote! Attempting to fix..."

    CLEANED_JSON=$(echo "$CLEANED_JSON" | sed -E 's/([^"])(,)/\1"\2/' | sed -E 's/([^"])}$/\1"}/')
fi


if ! echo "$CLEANED_JSON" | jq empty 2>/dev/null; then
    echo "⚠ JSON is invalid! Attempting to fix..."

    FIXED_JSON=$(echo "$CLEANED_JSON" | jsonrepair 2>/dev/null)

    if [ -z "$FIXED_JSON" ]; then
        echo "❌ Error: Could not fix JSON. Please check manually."
        exit 1
    fi

    CLEANED_JSON=$FIXED_JSON
fi

FORMATTED_JSON=$(echo "$CLEANED_JSON" | jq --indent 2 '.')

echo "✅ Cleaned and formatted JSON:"
echo "$FORMATTED_JSON"