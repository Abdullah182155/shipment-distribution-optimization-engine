# Courier Optimizer

A full-stack geographic optimization engine designed to allocate deliveries to couriers. It intelligently partitions a fleet's delivery footprint to minimize travel area, drastically reduce courier territory overlap, and firmly enforce workload capacity constraints (minimum and maximum deliveries per courier).

By utilizing a cutting-edge hybrid optimization pipeline consisting of **Large Neighborhood Search (LNS)**, **Simulated Annealing (SA)**, **PCA-based Anti-Elongation**, **Voronoi Reassignment**, and adaptive geographical heuristics, this application produces mathematically optimized, production-ready courier sectors.

### 📊 Optimization Result Example

The following map shows an optimized courier territory allocation. Each color represents a different courier's delivery zone — territories are compact, spatially coherent, and have minimal overlap:

<p align="center">
  <img src="docs/images/Screenshot 2026-04-19 011507.png" alt="Optimized Courier Territories" width="800"/>
</p>

> **Each polygon** = one courier's territory (convex hull) &nbsp;|&nbsp; **Each dot** = a delivery point &nbsp;|&nbsp; **Color** = courier assignment

---

## 🏗️ Project Structure

```
courier-optimizer_V4/
├── backend/                          # Python FastAPI optimization engine
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py             # All configurable parameters & weights
│   │   ├── services/
│   │   │   ├── optimizer.py          # Main pipeline orchestrator (multi-start + hybrid)
│   │   │   ├── initializers.py       # 4 clustering strategies (KMeans, Compact, HexGrid, Perturb)
│   │   │   ├── moves.py             # Basic move operators (greedy, swap, relocate)
│   │   │   ├── advanced_moves.py    # Advanced repairs (anti-elongation, Voronoi, deoverlap, etc.)
│   │   │   ├── sa.py                # Simulated Annealing polish
│   │   │   └── lns.py               # Large Neighborhood Search (destroy + repair)
│   │   └── utils/
│   │       ├── geometry.py           # Convex hull, overlap detection
│   │       ├── spatial.py            # Centroids, validation, clustering
│   │       └── cache.py             # Thread-local hull computation cache
│   ├── requirements.txt
│   └── run.py
├── frontend/                         # React + Vite + Leaflet.js dashboard
├── data/                             # Input CSV files
├── runs/                             # Historical optimization results (JSON)
├── logs/                             # Debug & performance logs
├── Courier_Optimizer_Documentation.docx  # Comprehensive project documentation
├── run_all.bat                       # One-click launcher
└── README.md
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js (v16+)
- Check `backend/requirements.txt` and `frontend/package.json` for specific dependencies.

### One-Click Launch
```bash
./run_all.bat
```
This opens two console windows:
- **Backend API:** `http://localhost:8000`
- **Frontend UI:** `http://localhost:5173`

### Manual Launch

**1. Backend:**
```bash
cd backend
pip install -r requirements.txt
python run.py
```

**2. Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 🧠 Optimization Pipeline

The optimizer runs a **5-phase hybrid pipeline** for each of 4 competing initial strategies:

```
Phase 1: Multi-Start Initialization
  ├── Compact v17    (nearest-neighbor greedy, tightest clusters)
  ├── KMeans v17     (balanced spatial partitioning)
  ├── HexGrid v17    (hexagonal grid overlay)
  └── Perturb30 v17  (best-of-3 + 30% random shuffle)
          │
Phase 2: Large Neighborhood Search (LNS)
  ├── Adaptive destroy (15-65% of points)
  ├── Regret-based repair
  ├── Periodic: or_opt, cross_exchange, vertex_steal
  ├── Periodic: merge_split (restructure courier pairs)
  ├── Periodic: anti_elongation (fix stretched couriers)
  └── Solution archive with crossover
          │
Phase 3: Simulated Annealing (SA)
  ├── Relocate & swap moves
  ├── Temperature: 0.05 → 0.0025 (15K iterations)
  └── Metropolis acceptance criterion
          │
Phase 4: Post-Processing & Repair
  ├── deoverlap_pass (fix hull intersections)
  ├── shrink_wrap_pass (tighten boundaries)
  ├── squeeze_pass (compress clusters)
  ├── area_greedy_vertex_steal (steal profitable points)
  ├── anti_elongation_pass (PCA aspect ratio check)
  └── merge_split_pass (large-scale restructuring)
          │
Phase 5: Final Voronoi Reassignment (Nuclear Cleanup)
  ├── Compute centroids from optimized solution
  ├── Reassign EVERY point to nearest centroid
  ├── Handle capacity constraints (min/max)
  ├── deoverlap_pass + targeted_overlap_swap (boundary fix)
  └── Final area tightening (vertex_steal + squeeze + greedy)
          │
     Best variant wins → JSON output
```

### Winning Strategy Tracking

Each run records which initialization strategy produced the best result:

```json
{
  "winning_strategy": "Compact  v17",
  "variant_scores": {
    "Compact  v17": 12.34,
    "KMeans   v17": 13.67,
    "HexGrid  v17": 14.01,
    "Perturb30 v17": 12.89
  }
}
```

---

## ⚙️ Configuration Parameters

All parameters are defined in `backend/app/core/config.py` and can be adjusted via the web UI.

### Objective Weights

| Weight | Default | Description |
|--------|---------|-------------|
| `alpha` | 1.0 | Area minimization weight |
| `beta` | 0.0 | Overlap penalty weight (recommended: 0.0, handled by post-processing) |
| `delta` | 0.0 | Compactness penalty weight (0.05-0.10 for light compactness enforcement) |

### Pipeline Tuning

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lns_iters` | 64 | LNS iterations per variant |
| `sa_iters` | 15,000 | Simulated Annealing iterations |
| `sa_t_start` | 0.05 | SA initial temperature |
| `sa_cool` | 0.9998 | SA cooling rate |
| `steal_n_neighbours` | 10 | Vertex steal search radius |
| `merge_split_pairs` | 2 | Courier pairs to merge-split per pass |
| `boredom_kick_every` | 5 | Rounds before large perturbation when stuck |

### Recommended Presets

| Scenario | LNS | SA | Time |
|----------|-----|-----|------|
| Quick Test | 4 | 1,000 | ~2-5 min |
| Standard | 32 | 6,000 | ~10-20 min |
| High Quality | 64 | 15,000 | ~30-60 min |

---

## 🔧 Key Advanced Features

### Anti-Elongation Pass
Detects couriers with elongated territories using **PCA (Principal Component Analysis)** aspect ratio. If a courier's length/width ratio exceeds 2.0, outlier points are moved or swapped to nearby couriers. Uses two strategies:
- **Move**: Transfer outlier to nearest courier with capacity
- **Swap**: If all couriers are full, swap outlier with a closer point (capacity-neutral)

### Final Voronoi Reassignment
The "nuclear cleanup" step. After all optimization, it takes the optimized centroid positions and **completely reassigns every point from scratch** to its nearest centroid. Guarantees:
- ✅ Spatial coherence (each point belongs to nearest courier)
- ✅ Compact shapes (Voronoi cells are naturally convex)
- ✅ Minimal overlap (Voronoi-like partition)
- ✅ Capacity constraints respected

### Targeted Overlap Swap
For remaining boundary overlaps after Voronoi reassignment: pools all points from two overlapping couriers, re-clusters them using KMeans with 5 random seeds, and picks the best partition.

---

## 🔥 Key Features

- **Real-Time Solver WebSockets:** Live streaming of optimization progress to the React dashboard — watch the solver work in real-time.
- **Thread-Local Execution State:** Extensive native geographical memory caching pushes performance closer to O(1) during intensive computations.
- **Strict Capacity Verification:** Guarantees no output violates dispatch constraints (min/max deliveries per courier).
- **History Analytics:** Browse and compare past optimization runs within the dashboard.
- **Multi-Start Competition:** 4 different clustering strategies compete — the best wins.
- **Winning Strategy Tracking:** JSON output includes which strategy won and all variant scores.

---

## 📄 Documentation

- [**Full Pipeline Strategy**](./full_pipeline_strategy.md): Breakdown of multi-start, LNS, merge-split, and SA passes.
- [**Objective Weights Guide**](./objective_weights_guide.md): How to tune alpha, beta, delta hyperparameters.
- [**Comprehensive Documentation**](./Courier_Optimizer_Documentation.docx): Detailed Word document covering every function, parameter, challenge, and solution — suitable for management review.

---

## 📊 Output Format

Each optimization run saves a JSON file in `runs/` with:

| Field | Description |
|-------|-------------|
| `area` | Total optimized area (km²) |
| `baseline_area` | Raw baseline for comparison |
| `overlap` | Total pairwise territory overlap |
| `time` | Computation time (seconds) |
| `valid` | Capacity constraint satisfaction |
| `winning_strategy` | Name of the best-performing variant |
| `variant_scores` | Area scores for all 4 variants |
| `avg_compact` | Average compactness across couriers |
| `couriers[]` | Per-courier: area, compactness, deliveries, hull vertices, centroid |
| `workload` | Min/max/mean/std of delivery counts |
