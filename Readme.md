# Roy ProcWatch 👑

Superviseur **vanilla** (Flask + Python / HTML-CSS-JS sans framework) pour **processus** et **ports** sur Ubuntu :
- Liste tous les **processus** (CPU, mémoire, nice, utilisateur, cmdline, fichiers ouverts*)
- Montre les **ports** locaux et distants par **PID**
- Actions : **Stop (SIGTERM)**, **Tuer (SIGKILL)**, **Relancer**, **Renice**, **Envoyer un signal**
- **Recherche**, **tri**, **auto-rafraîchissement**
- **Auth par token** (en-tête `X-Auth-Token`)
- Interface moderne **sans frameworks front**.

> \* Les fichiers ouverts peuvent nécessiter des privilèges élevés.

---

## Sommaire
- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation rapide (dev)](#installation-rapide-dev)
- [Configuration (.env)](#configuration-env)
- [Lancement](#lancement)
- [Sécurité](#sécurité)
- [Utilisation UI](#utilisation-ui)
- [API HTTP](#api-http)
- [Exemples `curl`](#exemples-curl)
- [Service systemd (au démarrage)](#service-systemd-au-démarrage)
- [Déploiement production (Gunicorn + Nginx)](#déploiement-production-gunicorn--nginx)
- [Dépannage](#dépannage)
- [Roadmap / Idées](#roadmap--idées)
- [Licence](#licence)

---

## Architecture

```

roy-procwatch/
├─ app.py                 # Flask API + vues statiques
├─ requirements.txt       # Dépendances Python
├─ .env                   # Variables d'environnement (token, host, port)
├─ static/
│  ├─ index.html          # UI (HTML)
│  ├─ app.js              # UI (JS vanilla)
│  └─ styles.css          # UI (CSS)
└─ systemd/
└─ roy-procwatch.service  # Unit systemd (mode user)

````

**Stack :**
- Backend : Python 3.10+ / Flask 3 / psutil 6
- Frontend : HTML + CSS + JS (aucune lib externe)
- OS cible : Ubuntu (dev/testé sur Debian/Ubuntu)

---

## Prérequis

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
````

---

## Installation rapide (dev)

```bash
git clone <votre-repo> roy-procwatch
cd roy-procwatch

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

---

## Configuration (.env)

Créez `.env` à la racine :

```env
# Clé d'authentification envoyée par l'UI et par l'API via X-Auth-Token
ROY_PROCWATCH_TOKEN=mettez-une-longue-cle-aleatoire-ici

# Bind réseau
ROY_PROCWATCH_HOST=127.0.0.1
ROY_PROCWATCH_PORT=8088
```

> **Conseil sécurité :** utilisez un token long/unique et **ne poussez jamais** `.env` dans Git (voir `.gitignore`).

---

## Lancement

### Mode développement

```bash
source .venv/bin/activate
python app.py
```

La console affiche :

```
[Roy ProcWatch] Running on http://127.0.0.1:8088  (token: VOTRE_TOKEN)
```

Ouvrez l’UI : `http://127.0.0.1:8088`
Dans le champ **X-Auth-Token** (en haut), collez **exactement** le token affiché et cliquez **Rafraîchir**.

### Permissions (processus root)

* Pour agir sur des processus d’autres utilisateurs/root, lancez le serveur avec **sudo** :

  ```bash
  sudo -E env PATH="$PATH" .venv/bin/python app.py
  ```

  ou exécutez sous un service systemd root (voir section dédiée).

---

## Sécurité

* **Ne pas exposer** l’app sur Internet sans proxy/authentification.
* **Token obligatoire** via l’en-tête `X-Auth-Token`.
* Gardez `ROY_PROCWATCH_HOST=127.0.0.1` si vous n’avez pas de reverse-proxy.
* En prod : placez l’app derrière **Nginx**, ajoutez **TLS**, rate-limiting, et un **basic auth** si besoin.

---

## Utilisation UI

**Barre de contrôle** (entête) :

* `X-Auth-Token` : votre token d’accès (obligatoire)
* **Recherche** : texte libre (PID, nom, cmdline, user)
* **Tri** : `CPU` | `Mémoire` | `Nom` | `PID`
* **Ordre** : asc/desc
* **Auto** : rafraîchissement automatique toutes les 3 s
* **Rafraîchir** : mise à jour immédiate

**Actions par processus** :

* **Stop** → `SIGTERM`
* **Tuer** → `SIGKILL`
* **HUP** → `SIGHUP`
* **Relancer** → tente d’arrêter puis relancer via `cmdline`/`exe`
* **Nice** → change la priorité (renice)

> La relance fonctionne si le binaire/cmdline est lisible et permis pour l’utilisateur du serveur.

---

## API HTTP

Toutes les routes **protégées** exigent l’en-tête :

```
X-Auth-Token: <votre_token>
```

### `GET /api/health`

Ping de santé.

**Réponse**

```json
{ "status": "ok", "time": "2025-10-14T23:00:00.000000" }
```

### `GET /api/processes`

Liste les processus + ports.

**Query params**

* `q` *(string, optionnel)* : filtre texte
* `sort` *(cpu|mem|pid|name, défaut: cpu)*
* `order` *(asc|desc, défaut: desc)*

**Réponse**

```json
{
  "count": 123,
  "items": [
    {
      "pid": 1234,
      "ppid": 1,
      "name": "python3",
      "exe": "/usr/bin/python3",
      "username": "jegue",
      "status": "running",
      "create_time": 1697300000.0,
      "create_time_iso": "2025-10-14T22:59:59",
      "cpu_percent": 3.2,
      "memory_rss": 12345678,
      "nice": 0,
      "cmdline": ["python3","app.py"],
      "ports": [
        {"local":"127.0.0.1:8088","remote":null,"status":"LISTEN","family":"AddressFamily.AF_INET"}
      ],
      "open_files_count": 2
    }
  ]
}
```

### `POST /api/process/<pid>/signal`

Envoie un signal.

**Body**

```json
{ "signal": "TERM" }   // TERM | KILL | INT | HUP | STOP | CONT
```

**Réponses**

* `200`: `{ "ok": true, "pid": 1234, "signal": "TERM" }`
* `404`: `{ "error": "Process not found" }`
* `403`: `{ "error": "Access denied..." }`

### `POST /api/process/<pid>/renice`

Change la priorité (nice).

**Body**

```json
{ "nice": 10 }   // int
```

**Réponse**

```json
{ "ok": true, "pid": 1234, "nice": 10 }
```

### `POST /api/process/<pid>/restart`

Arrête (TERM) puis relance (best effort).

**Réponse**

```json
{ "ok": true, "old_pid": 1234, "new_pid": 5678 }
```

---

## Exemples `curl`

Assurez-vous d’avoir exporté votre token :

```bash
TOKEN="mettez-une-longue-cle-aleatoire-ici"
```

* **Lister** :

  ```bash
  curl -H "X-Auth-Token: $TOKEN" "http://127.0.0.1:8088/api/processes?sort=cpu&order=desc"
  ```

* **TERM** :

  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -H "X-Auth-Token: $TOKEN" \
       -d '{"signal":"TERM"}' \
       http://127.0.0.1:8088/api/process/1234/signal
  ```

* **KILL** :

  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -H "X-Auth-Token: $TOKEN" \
       -d '{"signal":"KILL"}' \
       http://127.0.0.1:8088/api/process/1234/signal
  ```

* **Renice** :

  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -H "X-Auth-Token: $TOKEN" \
       -d '{"nice":5}' \
       http://127.0.0.1:8088/api/process/1234/renice
  ```

* **Restart** :

  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -H "X-Auth-Token: $TOKEN" \
       http://127.0.0.1:8088/api/process/1234/restart
  ```

---

## Service systemd (au démarrage)

### Unit (mode *user*)

Fichier : `systemd/roy-procwatch.service`

```ini
[Unit]
Description=Roy ProcWatch (process & ports) 👑
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/roy-procwatch
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=%h/roy-procwatch/.env
ExecStart=%h/roy-procwatch/.venv/bin/python %h/roy-procwatch/app.py
Restart=on-failure
User=%i

[Install]
WantedBy=default.target
```

Installation :

```bash
mkdir -p ~/.config/systemd/user
cp systemd/roy-procwatch.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable roy-procwatch.service
systemctl --user start  roy-procwatch.service

# Logs
journalctl --user -u roy-procwatch.service -f
```

### Unit (mode *system*, root)

Utile pour agir sur des PIDs root.

`/etc/systemd/system/roy-procwatch.service` :

```ini
[Unit]
Description=Roy ProcWatch (root)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/roy-procwatch
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/roy-procwatch/.env
ExecStart=/opt/roy-procwatch/.venv/bin/python /opt/roy-procwatch/app.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /opt/roy-procwatch
sudo cp -r * /opt/roy-procwatch/
cd /opt/roy-procwatch
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

sudo systemctl daemon-reload
sudo systemctl enable roy-procwatch
sudo systemctl start  roy-procwatch
sudo journalctl -u roy-procwatch -f
```

---

## Déploiement production (Gunicorn + Nginx)

### Gunicorn

```bash
. .venv/bin/activate
pip install gunicorn

# WSGI : app:app (module:objet)
gunicorn -b 127.0.0.1:8088 app:app --workers 2
```

### Nginx (reverse-proxy)

`/etc/nginx/sites-available/roy-procwatch.conf` :

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # Optionnel : Auth Basic
        # auth_basic "Restricted";
        # auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/roy-procwatch.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

> **Important :** Conservez le **token**. Ajoutez **TLS** (Let’s Encrypt) en prod.

---

## Dépannage

* **401 Unauthorized** : vous n’avez pas mis le **X-Auth-Token** dans l’UI / `curl`.
* **403 Access Denied** : action sur un processus ne vous appartenant pas → lancer le service avec plus de privilèges (root/systemd).
* **Relance ne marche pas** : le process n’a pas de `cmdline` exploitable / binaire introuvable / permissions.
* **404 /favicon.ico** : bénin (cosmétique).
* **Ports vides** : aucune socket ou permissions insuffisantes.
* **UI ne retient pas le token** : activez l’astuce localStorage (voir ci-dessous).

**Astuce (mémoriser le token côté navigateur)** – à ajouter en haut de `static/app.js` :

```js
tokenInput.value = localStorage.getItem("roy_token") || "";
tokenInput.addEventListener("input", () => localStorage.setItem("roy_token", tokenInput.value));
```

---

## Roadmap / Idées

* Pagination / colonnes configurables
* Export CSV/JSON
* Détail avancé d’un PID (threads, maps mémoire, fichiers)
* Signaux configurables/whitelist
* Intégration `systemd` (start/stop/restart de **services**)
* WebSocket/SSE pour métriques en temps réel
* Thème clair/sombre, préférences utilisateur

---

## Licence

MIT – libre d’utilisation, modification et distribution. Ajoutez `LICENSE` si vous publiez le dépôt.

````