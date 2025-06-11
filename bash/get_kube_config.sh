#!/bin/bash
set -euo pipefail

extract_project_name() {
    local job_url="$1"
    echo "$job_url" | sed -E 's|.*/iac/([^/]+)/-.*|\1|'
}

extract_gitlab_host() {
    local job_url="$1"
    echo "$job_url" | sed -E 's|https?://([^/]+)/.*|\1|'
}

extract_job_id() {
    local job_url="$1"
    echo "$job_url" | sed -E 's|.*/jobs/([0-9]+).*|\1|'
}

download_kubeconfig() {
    local base_job_url="$1"

    if [[ -z "${GITLAB_TOKEN:-}" ]]; then
        echo "❌ GITLAB_TOKEN environment variable is not set."
        exit 1
    fi

    export GITLAB_HOST
    GITLAB_HOST=$(extract_gitlab_host "$base_job_url")
    local project
    project=$(extract_project_name "$base_job_url")
    local job_id
    job_id=$(extract_job_id "$base_job_url")

    local project_id
    project_id=$(glab api --hostname "$GITLAB_HOST" /projects?search="$project" | jq ".[0].id")

    if [[ -z "$project_id" ]]; then
        echo "❌ Could not find project ID for project: $project"
        exit 1
    fi

    local output_path="/tmp/${project}"
    echo "🔄 Downloading kubeconfig from project: $project (ID: $project_id), job: $job_id"

    if ! glab api --hostname "$GITLAB_HOST" \
        "/projects/${project_id}/jobs/${job_id}/artifacts/ansible/k8s-deploy/oidc-kubeconfig" \
        > "$output_path"; then
        echo "❌ glab failed to fetch artifact."
        exit 1
    fi

    if [[ ! -s "$output_path" ]]; then
        echo "❌ Download failed or file is empty."
        exit 1
    fi

    echo "✅ Kubeconfig downloaded. Updating names to: ${project}"

    # Use sed to replace names regardless of format
    sed -i \
        -e "s/name: microk8s-cluster/name: ${project}/" \
        -e "s/name: microk8s/name: ${project}/" \
        -e "s/cluster: microk8s-cluster/cluster: ${project}/" \
        -e "s/user: oidc/user: ${project}/" \
        -e "s/name: oidc/name: ${project}/" \
        -e "s/current-context: microk8s/current-context: ${project}/" \
        "$output_path"

    echo "🎯 Final kubeconfig ready at: $output_path"
}


merge_kubeconfig() {
    local new_config="$1"
    local cluster_name="$2"

    if [[ ! -f "$new_config" ]]; then
        echo "❌ Kubeconfig file $new_config not found."
        return 1
    fi

    local kubeconfig_file="$HOME/.kube/config"

    echo "🔍 Checking if cluster '$cluster_name' already exists in $kubeconfig_file..."

    if KUBECONFIG="$kubeconfig_file" kubectl config get-clusters | grep -q "^$cluster_name$"; then
        echo "⚠️ Cluster '$cluster_name' already exists. Removing old entry to avoid conflicts..."

        KUBECONFIG="$kubeconfig_file" kubectl config delete-cluster "$cluster_name" || true
        KUBECONFIG="$kubeconfig_file" kubectl config delete-context "$cluster_name" || true
        KUBECONFIG="$kubeconfig_file" kubectl config delete-user "$cluster_name" || true
    else
        echo "✅ Cluster '$cluster_name' is new. Will be added."
    fi

    echo "🔀 Merging $new_config into $kubeconfig_file..."

    KUBECONFIG="$kubeconfig_file:$new_config" \
    kubectl config view --flatten --merge > /tmp/merged-kubeconfig

    mv /tmp/merged-kubeconfig "$kubeconfig_file"
    chmod 600 "$kubeconfig_file"

    echo "✅ Successfully merged '$cluster_name' into $kubeconfig_file"
}


# Validate input
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <GitLab Job URL (without artifact path)>"
    echo "Example: $0 https://gitlab.ccdev.drpp-onprem.global/iac/mw-dev/-/jobs/21603"
    echo "Note: GITLAB_TOKEN must be set as an environment variable."
    exit 1
fi

BASE_JOB_URL="$1"
project=$(extract_project_name "$BASE_JOB_URL")
download_kubeconfig "$BASE_JOB_URL"
merge_kubeconfig "/tmp/${project}" "${project}"

