"""
╔══════════════════════════════════════════════════════════╗
║       llama-server + ngrok Diagnostic Checker            ║
║  Jalankan cell ini di Kaggle untuk cek status server     ║
╚══════════════════════════════════════════════════════════╝

Cara pakai:
  - Copy semua kode ini ke 1 cell baru di Kaggle notebook
  - Jalankan cell tersebut
  - Hasil cek akan muncul dengan status ✅ / ⚠️ / ❌
"""

import subprocess
import os
import time
import requests

# ─────────────────────────────────────────────
# CONFIG — sesuaikan dengan setting notebook kamu
# ─────────────────────────────────────────────
NGROK_PORT    = "8080"          # port yang dipakai llama-server
NGROK_URL     = "https://tipoff-errant-chatroom.ngrok-free.dev/v1/chat/completions"              # isi URL ngrok kamu, contoh: "https://xxxx.ngrok-free.app"
                                # kosongkan jika ingin skip cek eksternal
HEALTH_TIMEOUT = 10             # detik timeout per request
# ─────────────────────────────────────────────


def sep(title=""):
    width = 58
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("─" * width)


def ok(msg):   print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def err(msg):  print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")


# ══════════════════════════════════════════════
# CEK 1 — Proses llama-server masih berjalan?
# ══════════════════════════════════════════════
sep("1. Proses llama-server")

result = subprocess.run(
    ["pgrep", "-a", "-f", "llama-server"],
    capture_output=True, text=True
)

if result.returncode == 0:
    lines = result.stdout.strip().splitlines()
    ok(f"llama-server berjalan ({len(lines)} proses)")
    for line in lines:
        info(f"  PID & CMD: {line[:120]}")
else:
    err("llama-server TIDAK berjalan / sudah mati")
    warn("Solusi: jalankan ulang cell start_llama_server()")


# ══════════════════════════════════════════════
# CEK 2 — Port sedang LISTEN?
# ══════════════════════════════════════════════
sep("2. Port listening")

try:
    lsof = subprocess.run(
        ["sudo", "lsof", "-i", f":{NGROK_PORT}", "-P", "-n"],
        capture_output=True, text=True
    )
    if f":{NGROK_PORT} (LISTEN)" in lsof.stdout:
        ok(f"Port {NGROK_PORT} sedang LISTEN")
    else:
        # fallback ss
        ss = subprocess.run(
            ["ss", "-tlnp", f"sport = :{NGROK_PORT}"],
            capture_output=True, text=True
        )
        if NGROK_PORT in ss.stdout:
            ok(f"Port {NGROK_PORT} sedang LISTEN (via ss)")
        else:
            err(f"Port {NGROK_PORT} TIDAK LISTEN")
            warn("Server mungkin masih loading atau sudah crash")
except Exception as e:
    warn(f"Tidak bisa cek port: {e}")


# ══════════════════════════════════════════════
# CEK 3 — Health endpoint local
# ══════════════════════════════════════════════
sep("3. Health endpoint (localhost)")

local_health = f"http://localhost:{NGROK_PORT}/health"
try:
    r = requests.get(local_health, timeout=HEALTH_TIMEOUT)
    if r.status_code == 200:
        ok(f"Health OK — {r.json()}")
    elif r.status_code == 503:
        warn(f"Server ada tapi model masih loading (503)")
        info("Tunggu beberapa menit lagi lalu cek ulang")
    else:
        warn(f"Health reply: HTTP {r.status_code} — {r.text[:200]}")
except requests.exceptions.ConnectionError:
    err("Tidak bisa konek ke localhost — server tidak jalan")
except requests.exceptions.Timeout:
    warn(f"Timeout setelah {HEALTH_TIMEOUT}s — server sangat lambat")
except Exception as e:
    err(f"Error: {e}")


# ══════════════════════════════════════════════
# CEK 4 — GPU / VRAM
# ══════════════════════════════════════════════
sep("4. GPU & VRAM")

try:
    nvsmi = subprocess.run(
        ["nvidia-smi",
         "--query-gpu=index,name,memory.used,memory.free,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True
    )
    for line in nvsmi.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        idx, name, used, free, total, util = parts
        used_pct = round(int(used) / int(total) * 100, 1)
        status_fn = ok if used_pct < 90 else warn
        status_fn(
            f"GPU {idx} [{name}] "
            f"VRAM: {used}/{total} MiB ({used_pct}%) | "
            f"Util: {util}%"
        )
        if used_pct > 95:
            err("VRAM hampir penuh — kemungkinan OOM, server bisa crash")
except FileNotFoundError:
    warn("nvidia-smi tidak tersedia (CPU-only environment?)")
except subprocess.CalledProcessError as e:
    warn(f"nvidia-smi error: {e}")


# ══════════════════════════════════════════════
# CEK 5 — Proses ngrok masih berjalan?
# ══════════════════════════════════════════════
sep("5. Proses ngrok")

ngrok_proc = subprocess.run(
    ["pgrep", "-a", "-f", "ngrok"],
    capture_output=True, text=True
)
if ngrok_proc.returncode == 0:
    ok("ngrok process berjalan")
    info(ngrok_proc.stdout.strip()[:120])
else:
    err("ngrok process TIDAK ditemukan")
    warn("Solusi: jalankan ulang cell setup_ngrok_tunnel()")


# ══════════════════════════════════════════════
# CEK 6 — Ngrok tunnel aktif (via ngrok API lokal)
# ══════════════════════════════════════════════
sep("6. Ngrok tunnels aktif")

try:
    ng = requests.get("http://localhost:4040/api/tunnels", timeout=5)
    tunnels = ng.json().get("tunnels", [])
    if tunnels:
        for t in tunnels:
            ok(f"Tunnel: {t['public_url']}  →  {t['config']['addr']}")
    else:
        warn("Ngrok berjalan tapi tidak ada tunnel aktif")
except requests.exceptions.ConnectionError:
    warn("Ngrok dashboard (port 4040) tidak bisa diakses")
    info("Coba cek manual: tunnel mungkin sudah expired")
except Exception as e:
    warn(f"Error cek ngrok API: {e}")


# ══════════════════════════════════════════════
# CEK 7 — Akses eksternal via URL ngrok
# ══════════════════════════════════════════════
sep("7. Akses dari luar via ngrok URL")

if not NGROK_URL:
    warn("NGROK_URL belum diisi — skip cek eksternal")
    info("Isi variabel NGROK_URL di bagian CONFIG di atas")
else:
    ext_health = f"{NGROK_URL.rstrip('/')}/health"
    try:
        r = requests.get(
            ext_health,
            timeout=HEALTH_TIMEOUT,
            headers={"ngrok-skip-browser-warning": "true"}
        )
        if r.status_code == 200:
            ok(f"Ngrok URL bisa diakses dari luar ✓")
            info(f"Response: {r.json()}")
        elif r.status_code == 503:
            warn(f"503 — server ada tapi model masih loading")
        elif r.status_code == 502:
            err(f"502 — ngrok tunnel jalan tapi llama-server tidak merespons")
            warn("Restart llama-server lalu tunggu model selesai load")
        else:
            warn(f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.exceptions.Timeout:
        err(f"Timeout setelah {HEALTH_TIMEOUT}s dari ngrok URL")
    except Exception as e:
        err(f"Tidak bisa akses ngrok URL: {e}")


# ══════════════════════════════════════════════
# CEK 8 — Disk space (untuk download model)
# ══════════════════════════════════════════════
sep("8. Disk space")

try:
    df = subprocess.run(
        ["df", "-h", "/", "/kaggle/working"],
        capture_output=True, text=True
    )
    for line in df.stdout.strip().splitlines():
        info(line)
except Exception as e:
    warn(f"Tidak bisa cek disk: {e}")


# ══════════════════════════════════════════════
# RINGKASAN
# ══════════════════════════════════════════════
sep("RINGKASAN")
print("""
  Arti status error:
  ─────────────────────────────────────────────────
  503 Service Unavailable  → Server ada, model masih loading
                             Tunggu lalu retry

  502 Bad Gateway          → ngrok tunnel aktif, tapi
                             llama-server tidak merespons
                             (crash / belum jalan / OOM)

  Connection Error         → llama-server tidak jalan sama sekali

  ─────────────────────────────────────────────────
  Urutan restart yang benar:
    1. start_llama_server(...)
    2. check_llama_server_port(NGROK_PORT)   ← tunggu LISTEN
    3. wait_for_model_ready(localhost:PORT)  ← tunggu model ready
    4. setup_ngrok_tunnel(PORT, secrets)     ← baru buka tunnel
    5. Gunakan URL ngrok yang baru
""")
sep()