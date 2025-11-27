# Prompt: Make config paths installation‑safe and remove hard‑coded 'verwalter' defaults

You are an AI coding assistant working on the **sensepi** project.
Your task is to improve configuration and path handling so the application
is less tied to a specific user (`/home/verwalter`) and works better when
installed as a package or used on other machines.

Focus on **integration** in the existing config layer and Pi defaults.

---

## Context: AppPaths and host defaults

Relevant modules/files:

- `sensepi/config/app_config.py` (or similar; adjust to repo)
- `hosts.yaml` sample(s)
- `raspberrypi_scripts/pi_config.yaml` (or equivalent Pi‑side config)

### AppPaths uses a fixed repo_root

```python
@dataclass
class AppPaths:
    repo_root: Path = Path(__file__).resolve().parents[3]
    data_root: Path = field(init=False)
    logs_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data_root = self.repo_root / "data"
        self.logs_dir = self.repo_root / "logs"
```

This works for a **src‑layout** run from the repo but is brittle when
the package is installed elsewhere (e.g. `site-packages`).

### HostInventory / defaults contain `/home/verwalter/...`

Example patterns you need to hunt down and generalise:

```python
DEFAULT_BASE_PATH = "/home/verwalter/sensor"
DEFAULT_DATA_DIR = "/home/verwalter/logs"
```

And Pi config examples like:

```yaml
data_dir: /home/verwalter/logs/mpu
```

These are fine on the original machine but should be made generic.

---

## What you must implement

### 1. Make AppPaths more installation‑friendly

1. Keep `AppPaths` working for **repo‑local development**.
2. Add support for **overriding data/log roots** using environment variables.

   Implement logic roughly like:

   ```python
   class AppPaths:
       def __post_init__(self) -> None:
           env_data_root = os.environ.get("SENSEPI_DATA_ROOT")
           env_logs_dir = os.environ.get("SENSEPI_LOG_DIR")

           if env_data_root:
               self.data_root = Path(env_data_root).expanduser()
           else:
               self.data_root = self.repo_root / "data"

           if env_logs_dir:
               self.logs_dir = Path(env_logs_dir).expanduser()
           else:
               self.logs_dir = self.repo_root / "logs"
   ```

   - Import `os` as needed.
   - Use `.expanduser()` so `~` works on all platforms.

3. Add a short docstring or comment explaining this behaviour and the env vars.

> You do **not** need to introduce `platformdirs` or similar right now;
> environment variables are enough for this task.

### 2. Remove hard‑coded `/home/verwalter` defaults

1. Replace any constants like:

   ```python
   DEFAULT_BASE_PATH = "/home/verwalter/sensor"
   DEFAULT_DATA_DIR = "/home/verwalter/logs"
   ```

   with more generic values that still make sense on a Pi or Linux machine, e.g.:

   ```python
   DEFAULT_BASE_PATH = "~/sensor"
   DEFAULT_DATA_DIR = "~/logs"
   ```

   - Always run these through `.expanduser()` before using them in code.
   - Keep these as *defaults* only; allow users to override via `hosts.yaml` / Settings tab.

2. Update sample `hosts.yaml` files to use generic paths:

   - Replace `/home/verwalter/...` with values appropriate for a typical Pi,
     e.g. `/home/pi/sensor` and `/home/pi/logs` **or** `~/sensor`, `~/logs`.
   - Make it very clear in comments that users should adjust paths to their own environment.

3. Update Pi‑side config defaults (e.g. `raspberrypi_scripts/pi_config.yaml`):

   - Replace `/home/verwalter/logs/...` with something like `/home/pi/logs/...`
     or `~/logs/...`.
   - Ensure that the desktop GUI and Pi defaults are consistent (e.g. if `data_dir`
     is `~/logs/mpu` on the Pi, reflect that in any docs or host defaults).

### 3. Small documentation update

1. In `README.md` or the relevant docs page, add a short note explaining:

   - The new environment variables: `SENSEPI_DATA_ROOT`, `SENSEPI_LOG_DIR`.
   - That host and Pi paths in `hosts.yaml` / `pi_config.yaml` are examples and should be adapted.

   Keep this to one small subsection titled something like **Configuration paths**.

---

## Behaviour expectations

After your changes:

- Running from the repo still uses `repo_root/data` and `repo_root/logs` **by default**.
- Users can override data/log locations by setting environment variables without touching code.
- No paths in code or default configs are tied to `verwalter`; new installations should not need
  to edit Python files just to run the app.

---

## Constraints & style

- No new third‑party dependencies.
- Use `Path` / `expanduser` consistently.
- Be careful to **not break** existing relative path logic (e.g. joining base paths with subdirs).
