# Cloud_Demo: Flipkart Big Billion Days scalability exercise (IT457, Group 30)

Case: Flipkart's move from own data centres / private cloud towards a hybrid setup, and how it
survives the Big Billion Days (BBD) traffic spike (Week 1 report: Group30_1.pdf; mapping table below).
Exercise (faculty theme "Scalability"): web app behind a load balancer with autoscaling, load test,
plot response time against instance count.

## What is built and which Flipkart practice it mirrors

| Flipkart practice (Week 1 source) | In this repo |
|---|---|
| Software LB, no hardware appliances [2] | `lb/nginx.conf` (Docker) and `lb/lb.py` (dev mode), backends discovered dynamically |
| Spike >5x normal traffic [2], load tests at 5x [1] | `loadtest/locustfile.py` BBD-shaped profile (warm, ramp, hold at 5x, ramp down); `loadtest/k6_spike.js` |
| Autoscaling / elastic capacity [3][4] | `autoscaler/autoscaler.py` target-tracking, fast scale-out, slow scale-in |
| Preparation months ahead, pre-provisioning [1] | `prewarm` mode: scheduled capacity floor before the sale |
| Async queues decouple heavy work [1] | `/api/checkout` returns 202 and enqueues; `app/worker.py` drains the queue |
| Caching layer [4] | Redis cache-aside on `/api/products` |
| Fallbacks / graceful degradation [1] | load shedding with 503 + Retry-After ("waiting room"), queue backpressure |
| 2014 stock-outs / correctness [5] | atomic Redis `DECRBY` stock, no overselling under concurrency |
| Shared platform, minutes-not-days deploys [4] | Docker Compose, replicas change in seconds |
| Cost efficiency of autoscaling [3][4] | instance-seconds x price per run, compared against static provisioning |

Only discussed, not replicated: own data centres, the hybrid migration, Aerospike-scale infrastructure.

## Layout

```
app/            FastAPI storefront (main.py) + order worker (worker.py)
lb/             nginx.conf (Docker) and lb.py (dev-mode software LB)
autoscaler/     control loop, process and docker backends, cost accounting
loadtest/       locustfile.py (primary), k6_spike.js (alternative)
experiments/    run_experiment.py, run_all.sh, analyze.py
results/        per-run CSVs, plots, summary.json, comparison.png / comparison.csv
```

## How capacity is modelled

Each app instance has `CONCURRENCY` slots (default 2) and heavy requests cost `SERVICE_MS` (250 ms),
so one instance serves roughly 30 requests/s of the shopper mix (60% browse, 25% search, 10% cart,
5% checkout). Because capacity is bounded per instance rather than by the host CPU, scaling
behaviour is reproducible on any laptop. Instances also have a simulated boot delay (`START_DELAY_S`)
so that reacting late is visibly costly, which is the argument for Flipkart-style pre-provisioning.

## Run it

Requirements: Python 3.11+, `pip install -r requirements.txt`, `redis-server` on PATH.

```bash
# dev mode (no Docker): one scenario, ~2 minutes
python experiments/run_experiment.py --name reactive --mode reactive

# all four scenarios + comparison plot, ~12 minutes
experiments/run_all.sh
```

Scenarios: `static-low` (4 instances, sized for normal traffic), `static-peak` (12 instances, provisioned for
the peak all day), `reactive` (autoscaler only), `prewarm` (scheduled floor + autoscaler).

### Docker mode

```bash
docker compose up -d --build                       # redis, 2 app replicas, 2 workers, nginx on :8080
python autoscaler/autoscaler.py --backend docker --mode reactive --redis redis://localhost:6379/0 \
       --timeline results/docker/timeline.csv
BASE_RPS=40 locust -f loadtest/locustfile.py --headless --host http://localhost:8080 \
       --csv results/docker/locust --csv-full-history
python experiments/analyze.py --run docker
```

Docker mode has not been exercised yet in the environment where this was written (no Docker daemon),
so expect to adjust it on first run.

## Outputs for the report

* `results/<run>/timeline.png`: offered load, served rate, latency percentiles, instance count over time
* `results/<run>/latency_vs_instances.png`: the required response time vs instance count plot
* `results/comparison.png` and `comparison.csv`: latency, failures, cost and average instances per scenario
* `results/<run>/summary.json`: all headline numbers

## Caveats to state in the report

* The price (`--price-per-hour`, default 0.0208 USD/h) is an assumed small-VM on-demand rate, not a Flipkart figure; Flipkart's real spend is not public (Week 1, gaps).
* Instances are processes (dev mode) or containers, not VMs; boot time is simulated.
* Load generator, LB, Redis and instances share one machine, so absolute numbers are indicative; the comparison between scenarios is the result.

## Results (180 s profile: 40 req/s normal, ramp to 200 req/s = 5x, hold 40 s, ramp down)

| Scenario | Failed % | Peak p95 median / worst (ms) | Avg instances | Cost (USD, assumed price) |
|---|---|---|---|---|
| static-low (4) | 13.2 | 1900 / 3200 | 4.0 | 0.0044 |
| static-peak (12) | 0.12 | 560 / 750 | 12.0 | 0.0133 |
| reactive | 0.28 | 330 / 1200 | 9.3 | 0.0104 |
| prewarm | 0.17 | 485 / 670 | 11.1 | 0.0123 |

Reading: sizing for normal traffic fails under a 5x spike; sizing for the peak works but is the most expensive;
reactive autoscaling is ~22% cheaper than static-peak here but its worst-case latency (1.2 s) occurs during the
ramp while new instances boot; pre-warming trades some cost for the lowest worst-case latency among the scaling
options. Failures are fast 503 responses from load shedding, so percentiles for `static-low` are not comparable to the others.
The cost gap would be far larger on a real day, because a 2-minute run spends a third of its time at peak.
Locust history percentiles are a 10 s sliding window. A mixed workload with only 2 slots per instance shows
head-of-line blocking (cheap requests queue behind 250 ms searches), which is why p50 is high at base load.
Reactive and prewarm both hit the 20-instance cap during the ramp: the step policy overshoots while instances boot.
