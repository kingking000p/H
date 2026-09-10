name: Linux Remote Terminal

on:
  workflow_dispatch:
    inputs:
      batch_id:
        description: 'Batch ID for logs'
        required: false
        type: string
        default: '1'

jobs:
  runner:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      actions: write

    steps:
      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y python3 curl

      - name: Install cloudflared
        run: |
          curl -L \
            -o /tmp/cloudflared \
            https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64

          chmod +x /tmp/cloudflared
          sudo mv /tmp/cloudflared /usr/local/bin/cloudflared

          cloudflared --version

      - name: Generate API token
        run: |
          TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
          echo "API_TOKEN=$TOKEN" >> "$GITHUB_ENV"
          echo
          echo "=========================================="
          echo "                 API TOKEN"
          echo "=========================================="
          echo "$TOKEN"
          echo "=========================================="
          echo

      - name: Create PTY API
        run: |
          cat > /tmp/server.py <<'PY'
          # ... (محتوای سرور بدون تغییر)
          PY

      - name: Start PTY API
        run: |
          nohup python3 /tmp/server.py > /tmp/api.log 2>&1 &
          sleep 3
          echo "PTY API started:"
          cat /tmp/api.log

      - name: Start Cloudflare Tunnel
        run: |
          nohup cloudflared tunnel --url http://127.0.0.1:8080 > /tmp/cloudflared.log 2>&1 &
          echo "Waiting for Cloudflare..."
          sleep 10
          URL=$(grep -oE 'https://[-a-z0-9]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1)
          if [ -z "$URL" ]; then
            echo "ERROR: Could not extract URL from cloudflared log"
            cat /tmp/cloudflared.log
            exit 1
          fi
          echo "URL=$URL" >> "$GITHUB_ENV"
          echo "REMOTE_URL=$URL" >> "$GITHUB_ENV"

      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.PAT_TOKEN }}
          fetch-depth: 0

      - name: Send logs to repo
        id: send_logs
        continue-on-error: true   # 🔥 اگه خطا داد، Workflow متوقف نشه
        env:
          GH_TOKEN: ${{ secrets.PAT_TOKEN }}
          RUN_ID: ${{ github.run_id }}
          RUN_NUMBER: ${{ github.run_number }}
          RUN_ATTEMPT: ${{ github.run_attempt }}
          BATCH_ID: ${{ github.event.inputs.batch_id }}
        run: |
          LOG_FILE="logs/run-${RUN_ID}-batch-${BATCH_ID}.txt"
          mkdir -p logs

          echo "Collecting logs into ${LOG_FILE} ..."
          cat > "${LOG_FILE}" <<EOF
          ==========================================
          Run ID        : ${RUN_ID}
          Batch ID      : ${BATCH_ID}
          Run Number    : ${RUN_NUMBER}
          Run Attempt   : ${RUN_ATTEMPT}
          Repository    : ${{ github.repository }}
          Actor         : ${{ github.actor }}
          Branch        : ${{ github.ref_name }}
          Commit        : ${{ github.sha }}
          Collected at  : $(date -u +"%Y-%m-%d %H:%M:%S UTC")
          ==========================================

          --- API log (/tmp/api.log) ---
          $(cat /tmp/api.log 2>/dev/null || echo "File not found")

          --- Cloudflared log (/tmp/cloudflared.log) ---
          $(cat /tmp/cloudflared.log 2>/dev/null || echo "File not found")

          --- Environment Variables ---
          API_TOKEN=${API_TOKEN}
          REMOTE_URL=${URL}

          ==========================================
          End of logs
          ==========================================
          EOF

          echo "${LOG_FILE} created:"
          cat "${LOG_FILE}"

          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git remote set-url origin https://x-access-token:${{ secrets.PAT_TOKEN }}@github.com/${{ github.repository }}.git

          git add "${LOG_FILE}"

          if git diff --staged --quiet; then
            echo "No changes to commit (file unchanged)"
            exit 0
          fi

          git commit -m "Add logs for run ${RUN_ID} batch ${BATCH_ID} [skip ci]"

          # 🔥 تلاش چند باره برای push با rebase
          MAX_RETRIES=5
          for i in $(seq 1 $MAX_RETRIES); do
            echo "Push attempt ${i}/${MAX_RETRIES}..."
            
            # اول fetch و rebase کن
            git fetch origin ${GITHUB_REF_NAME}
            git rebase origin/${GITHUB_REF_NAME} || git rebase --abort
            
            if git push origin HEAD:${GITHUB_REF_NAME}; then
              echo "✅ Push successful on attempt ${i}"
              exit 0
            fi
            
            echo "⚠️ Push failed, waiting 5s before retry..."
            sleep 5
          done
          
          echo "❌ All push attempts failed"
          exit 1

      - name: Update repository variables
        continue-on-error: true
        env:
          GH_TOKEN: ${{ secrets.PAT_TOKEN }}
        run: |
          echo "Setting repository variables..."
          gh variable set REMOTE_URL --body "$URL" --repo "${{ github.repository }}"
          gh variable set API_TOKEN --body "$API_TOKEN" --repo "${{ github.repository }}"
          echo "Repository variables updated."

      - name: Keep runner alive
        run: |
          echo
          echo "=========================================="
          echo "REAL PTY RUNNER READY"
          echo "Waiting for commands..."
          echo "=========================================="
          while true; do sleep 60; done
