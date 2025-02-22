#!/bin/bash
ENV=$1

# Set namespace to kube-system by default, or use the second argument if provided
NAMESPACE=${2:-"kube-system"}
echo "🔍 Searching for Terraform state files from Kubernetes in namespace: $NAMESPACE for environment: $ENV..."
SECRETS=$(kubectl get secrets -n $NAMESPACE | grep "tfstate-default.*-$ENV-state" | awk '{print $1}')
if [ -z "$SECRETS" ]; then
    echo "❌ No Terraform state secrets found in $NAMESPACE for environment $ENV!"
    exit 1
fi
echo "✅ Found the following Terraform state files for $ENV:"
echo "$SECRETS"
echo "-----------------------------------------"

for SECRET in $SECRETS; do
    echo "🔹 Extracting Terraform state from: $SECRET"

    # Decode and pretty-print the Terraform state
    STATE_JSON=$(kubectl get secret $SECRET -n $NAMESPACE -o jsonpath="{.data.tfstate}" | base64 --decode  | gunzip | jq)

    if [ -z "$STATE_JSON" ]; then
        echo "⚠️ Warning: State file for $SECRET is empty or could not be decoded."
        continue
    fi

    # Display key information from the state file
    echo "📜 Summary of $SECRET:"
    echo "$STATE_JSON" | jq '.resources[] | {name: .name, type: .type, instances: (.instances | length)}'
    echo "-----------------------------------------"

    # Save the state file locally (optional)
    mkdir -p ./terraform_states
    echo "$STATE_JSON" > "./terraform_states/$SECRET.json"
    echo "📁 State file saved: ./terraform_states/$SECRET.json"
done

echo "✅ All Terraform state files have been processed!"

echo "✅ Opening State files in VS..."
cd terraform_states && code .


