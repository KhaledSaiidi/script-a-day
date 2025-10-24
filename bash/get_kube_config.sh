#!/usr/bin/env bash
set -euo pipefail

# --- helpers ---------------------------------------------------------------

extract_gitlab_host() { echo "$1" | sed -E 's#https?://([^/]+)/.*#\1#'; }
extract_project_full_path() { echo "$1" | sed -E 's#https?://[^/]+/([^?]+?)/-/.+#\1#'; }
extract_env_name() { basename "$1"; }
extract_job_id() { echo "$1" | sed -E 's#.*/jobs/([0-9]+).*#\1#'; }
urlencode_slashes() { echo "$1" | sed 's#/#%2F#g'; }
json_get() { jq -r "$1"; }

# --- GitLab ---------------------------------------------------------------

get_project_id() {
  local host="$1" path="$2"
  local enc; enc="$(urlencode_slashes "$path")"
  glab api --hostname "$host" "/projects/${enc}" | json_get '.id'
}

download_artifacts_zip() {
  local host="$1" project_id="$2" job_id="$3" out_zip="$4"
  glab api --hostname "$host" "/projects/${project_id}/jobs/${job_id}/artifacts" > "$out_zip" || {
    echo "❌ Failed to download artifacts for job ${job_id}"; return 1; }
  unzip -tq "$out_zip" >/dev/null 2>&1 || {
    echo "❌ Artifacts are not a valid ZIP (job may lack artifacts)"; return 1; }
}

extract_kubeconfig_from_zip() {
  local zip="$1" env="$2" out="$3"
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  unzip -q "$zip" -d "$tmp"

  # prefer <env>-oidc-kubeconfig; fallback to oidc-kubeconfig; then any *oidc-kubeconfig
  local cand=""
  if [[ -f "$tmp/ansible/k8s-deploy/${env}-oidc-kubeconfig" ]]; then
    cand="$tmp/ansible/k8s-deploy/${env}-oidc-kubeconfig"
  elif [[ -f "$tmp/ansible/k8s-deploy/oidc-kubeconfig" ]]; then
    cand="$tmp/ansible/k8s-deploy/oidc-kubeconfig"
  else
    cand="$(find "$tmp" -type f -name '*oidc-kubeconfig' | head -n1 || true)"
  fi

  [[ -n "$cand" && -s "$cand" ]] || { echo "❌ kubeconfig not found in artifacts"; return 1; }
  cp -f "$cand" "$out"
}

validate_kubeconfig() {
  local f="$1"
  kubectl --kubeconfig "$f" config view >/dev/null 2>&1 || {
    echo "❌ Invalid kubeconfig (parse failed)"; return 1; }
}

# --- build a clean single-context kubeconfig ------------------------------

rebuild_single_kubeconfig_with_env_names() {
  local in="$1" env="$2"
  local j; j="$(kubectl --kubeconfig "$in" config view --raw -o json)"

  # choose cluster: use the cluster referenced by the current (or first) context
  local ctx_name; ctx_name="$(echo "$j" | json_get '.["current-context"]')"
  if [[ -z "$ctx_name" || "$ctx_name" == "null" ]]; then
    ctx_name="$(echo "$j" | json_get '.contexts[0].name')"
  fi
  [[ -n "$ctx_name" && "$ctx_name" != "null" ]] || { echo "❌ No contexts found in kubeconfig"; return 1; }

  # pull the context object
  local ctx_json; ctx_json="$(echo "$j" | jq --arg n "$ctx_name" '.contexts[] | select(.name==$n)')"
  [[ -n "$ctx_json" ]] || { echo "❌ Referenced context not found"; return 1; }

  # original cluster name referenced by the context
  local cluster_name; cluster_name="$(echo "$ctx_json" | json_get '.context.cluster')"
  # find the matching cluster spec
  local cluster_obj; cluster_obj="$(echo "$j" | jq --arg n "$cluster_name" '.clusters[] | select(.name==$n)')"
  [[ -n "$cluster_obj" ]] || { echo "❌ Referenced cluster not found"; return 1; }

  # choose user: prefer OIDC (exec.command=kubectl and args contain "oidc-login"); else first user in contexts[].context.user
  local user_name; user_name="$(echo "$ctx_json" | json_get '.context.user')"
  # if multiple users exist, try to find an OIDC-capable one
  local oidc_user_name=""
  # scan users for oidc-login
  while IFS= read -r name; do
    local u; u="$(echo "$j" | jq --arg n "$name" '.users[] | select(.name==$n)')"
    local cmd; cmd="$(echo "$u" | json_get '.user.exec.command // ""')"
    local args; args="$(echo "$u" | jq -r '.user.exec.args // [] | join(" ")')"
    if [[ "$cmd" == "kubectl" && "$args" == *"oidc-login"* ]]; then
      oidc_user_name="$name"; break
    fi
  done < <(echo "$j" | jq -r '.users[].name')

  if [[ -n "$oidc_user_name" ]]; then
    user_name="$oidc_user_name"
  fi

  # fetch the chosen user object
  local user_obj; user_obj="$(echo "$j" | jq --arg n "$user_name" '.users[] | select(.name==$n)')"
  [[ -n "$user_obj" ]] || { echo "❌ Referenced user not found"; return 1; }

  # Build a fresh, minimal kubeconfig with env names for everything
  jq -n --arg env "$env" \
        --argjson cluster "$(echo "$cluster_obj" | jq '.cluster')" \
        --argjson user    "$(echo "$user_obj" | jq '.user')" '
{
  apiVersion: "v1",
  kind: "Config",
  clusters: [ { name: $env, cluster: $cluster } ],
  users:    [ { name: $env, user: $user } ],
  contexts: [ { name: $env, context: { cluster: $env, user: $env } } ],
  "current-context": $env,
  preferences: {}
}' > "${in}.single"

  mv "${in}.single" "$in"

  # Validate result
  kubectl --kubeconfig "$in" config view >/dev/null
}

# --- merge into main ------------------------------------------------------

merge_into_main() {
  local new="$1" name="$2"
  local main="${HOME}/.kube/config"

  mkdir -p "$(dirname "$main")"
  touch "$main"; chmod 600 "$main"

  echo "🔍 Ensuring no old entries named '$name' remain in main config…"
  KUBECONFIG="$main" kubectl config delete-context "$name" 2>/dev/null || true
  KUBECONFIG="$main" kubectl config delete-cluster "$name" 2>/dev/null || true
  KUBECONFIG="$main" kubectl config delete-user "$name" 2>/dev/null || true

  echo "🔀 Merging $new into $main…"
  KUBECONFIG="$main:$new" kubectl config view --merge --flatten > /tmp/merged-kubeconfig
  mv /tmp/merged-kubeconfig "$main"
  chmod 600 "$main"
  echo "✅ Successfully merged '$name' into $main"
}

# --- main ----------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <GitLab Job URL>"
  echo "Example: $0 https://gitlab.controlcenter.cbc.drpp.global/iac/mw/-/jobs/107"
  exit 1
fi
[[ -n "${GITLAB_TOKEN:-}" ]] || { echo "❌ GITLAB_TOKEN is not set"; exit 1; }

BASE_JOB_URL="$1"
HOST="$(extract_gitlab_host "$BASE_JOB_URL")"
PROJECT_PATH="$(extract_project_full_path "$BASE_JOB_URL")"   # e.g. iac/mw
ENV_NAME="$(extract_env_name "$PROJECT_PATH")"                 # e.g. mw
JOB_ID="$(extract_job_id "$BASE_JOB_URL")"

ARTIFACT_ZIP="/tmp/${ENV_NAME}-job-${JOB_ID}.zip"
KCFG="/tmp/${ENV_NAME}"

cleanup(){ rm -f "$ARTIFACT_ZIP" /tmp/merged-kubeconfig 2>/dev/null || true; }
trap cleanup EXIT

echo "🔎 Host: $HOST"
echo "🔎 Project: $PROJECT_PATH (env name: $ENV_NAME)"
echo "🔎 Job ID: $JOB_ID"

PROJ_ID="$(get_project_id "$HOST" "$PROJECT_PATH")"
[[ -n "$PROJ_ID" && "$PROJ_ID" != "null" ]] || { echo "❌ Could not resolve project ID"; exit 1; }
echo "🔎 Project ID: $PROJ_ID"

echo "📦 Downloading artifacts…"
download_artifacts_zip "$HOST" "$PROJ_ID" "$JOB_ID" "$ARTIFACT_ZIP"

echo "📂 Extracting kubeconfig (preferring ${ENV_NAME}-oidc-kubeconfig)…"
extract_kubeconfig_from_zip "$ARTIFACT_ZIP" "$ENV_NAME" "$KCFG"

echo "🔐 Validating kubeconfig…"
validate_kubeconfig "$KCFG"

echo "🧰 Rebuilding kubeconfig with names forced to '${ENV_NAME}' and preferring OIDC user…"
rebuild_single_kubeconfig_with_env_names "$KCFG" "$ENV_NAME"

echo "🔗 Merging into ~/.kube/config…"
merge_into_main "$KCFG" "$ENV_NAME"

echo "🎯 Final kubeconfig ready at: $KCFG"
echo "✅ Done. Try: kubectx ${ENV_NAME} && kubens"

