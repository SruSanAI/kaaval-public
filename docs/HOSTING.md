# Hosting Kaaval

Kaaval runs in one container with open tools only (ngspice + the open sky130 PDK); see the `Dockerfile`.

    docker build -t kaaval .
    docker run -p 7860:7860 kaaval                         # http://localhost:7860

Optional environment (set as host secrets, never in code or the image):

| variable | enables |
|---|---|
| `MUSE_API_KEY` | Muse Spark plans the review (Meta Model API) |
| `KAAVAL_MAX_REVIEWS` | reviews simulating at once (default 2; others wait in a queue) |
| `KAAVAL_ACCESS_CODE` | a code needed to start a review (share it only with judges) |
| `KAAVAL_REVIEWS_PER_HOUR`, `KAAVAL_MAX_WAITING` | per-visitor limit (default 4/hour) and queue cap (default 6) |

## Hugging Face Spaces (free CPU: 2 vCPU, 16 GB)

1. Create a Space with SDK **Docker**, hardware **CPU basic**.
2. Push this repository to the Space (or connect it), with this header at the top of the Space's README:

       ---
       title: Kaaval
       sdk: docker
       app_port: 7860
       ---

3. Add `MUSE_API_KEY` under Settings → Variables and secrets.

Safety on a shared host: repositories are fetched as text files only (no GDS, nothing executed); every simulation
runs a deck Kaaval writes itself; reviews queue beyond `KAAVAL_MAX_REVIEWS`; each simulation session is capped.
