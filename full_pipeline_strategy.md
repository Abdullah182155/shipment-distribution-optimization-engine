# Courier Optimizer V4: Full Pipeline Strategy

This document outlines the end-to-end optimization pipeline used to solve the courier routing and delivery territory allocation problem. The system relies on a **multi-start hybrid algorithm** that pairs diverse initializations with Large Neighborhood Search (LNS) and Simulated Annealing (SA).

> 💡 **Complexity Variables Context:**
> - **N** = Total deliveries
> - **K** = Number of couriers
> - **n** = Average deliveries per courier (approx. **N/K**)
> - A fundamental operation executed repeatedly is the calculation of Convex Hulls via QuickHull or similar algorithms, which computes in **O(n log n)**. A full map state evaluation (updating all couriers) naturally runs in **O(K * n log n)** which simplifies to **O(N log(N/K))**.

## 1. Multi-Start Initialization
The optimization orchestrator evaluates multiple distinct starting configurations to avoid early local minima. 
- **KMeans Initialization:** Groups deliveries based on geographic clustering. 
  * **Time Complexity: O(I * N * K)** where `I` is the number of LLyod's algorithm iterations.
- **Compact Initialization:** A heuristic focusing strictly on creating dense initial shapes using spatial proximity. 
  * **Time Complexity: O(N log N)** driven by KDTree queries and spatial sorting.
- **HexGrid Initialization:** Formats clusters uniformly around a hexagonal grid template. 
  * **Time Complexity: O(N)** for direct geographic coordinate binning.
- **Random Perturbation (Perturb30):** Takes the best baseline layout and applies a 30% random perturbation to force structural variety. 
  * **Time Complexity: O(N)** 

## 2. Early Convergence & Repair
Before deep exploration begins, each layout sequence is pre-polished:
- **Convergence:** An initial greedy adjustment to stabilize the raw initialization states based on distance to centroids. 
  * **Time Complexity: O(N log(N/K))** (due to sequential cluster updates)
- **Area Greedy Vertex Steal:** Boundary points (vertices of the convex hulls) are swapped between couriers if it minimizes the combined area. 
  * **Time Complexity: O(V * c * n log n)** where `V` is the number of boundary vertices and `c` is nearby couriers. Generally much faster than `O(N)`.
- **De-overlap Passes:** Identifies overlapping territories via polygon intersection heuristics. 
  * **Time Complexity: O(K² + K * N)** for broad-phase bounding box checks and narrow point-in-polygon checks.
- **Merge / Split Pass:** Merges adjacent suboptimal zones and mathematically splits them optimally across axes. 
  * **Time Complexity: O(n log n)** per targeted pair, since it applies PCA or constrained sorting to sub-clusters.

## 3. Large Neighborhood Search (LNS) Loop
The core exploration phase iterates (e.g., $I_{LNS} = 32$) over the solution map. It destroys a portion of the map and rebuilds it creatively:
- **Adaptive Destroy:** Targets deliveries with the worst marginal area contributions and removes them. 
  * **Time Complexity: O(N * n log n)**. It evaluates the "hull cost without point `p`" for every point, although caching aggressively optimizes this empirical run-time.
- **Regret-based Repair:** The removed deliveries (fraction `D`) are re-inserted using a "regret" heuristical lookup matrix. 
  * **Time Complexity: O(D * c * n log n)** where `D` is the number of destroyed points and `c` is the evaluated local candidate couriers.
- **Solution Archive & Crossover & Simulated Annealing Check:** Constant-time `O(1)` metric checks, but doing the actual crossover reconstruction costs **O(N log(N/K))**.
- **Stage Complexity:** Heavily dominated by repairs, scaling theoretically at **O($I_{LNS}$ * N * n log n)**.

## 4. Middle Refinement
To clean up geometric imperfections left over by LNS destruction/creation phases:
- **Shrink Wrap Pass:** Explores points on convex hull boundaries and iteratively attempts to collapse the area inwards. 
  * **Time Complexity: O(V * c * n log n)** where `V` is checking specific boundary points.
- **Squeeze Pass:** Ejects deliveries from geometries that have become highly elongated or oddly shaped. 
  * **Time Complexity: O(N)** for fast geometric ratio calculations.

## 5. Simulated Annealing (SA) Polish
A micro-optimization sequence acting entirely on granular 1-to-1 boundary swaps, utilizing thousands of fast iterations (e.g., $I_{SA}$ = 6,000).
- **Time Complexity: O($I_{SA}$ * n log n)** theoretically.
- *Performance note:* Because $I_{SA}$ is very large, the system leverages massive ThreadLocalState hull caching. Empirical performance for rejected/bad moves approaches **O(1)** constants, shifting the real-world bottleneck back to the memory bus.

## 6. Final Re-Balancing & Validation
Verifies constraints ensuring the solution is viable for real-world dispatch:
- **Capacity Regulators:** Validates that every courier is within `min_del` and `max_del` limits. `rebalance.py` uses heuristic solver trees to move overflow. 
  * **Time Complexity: O(N log N)** using KD-tree shortest-path cascades.
- Generates final precise geometric arrays, outputting polygons boundaries and final overlap matrices. 
  * **Time Complexity: O(N log(N/K))**

## The Global Objective Function
Throughout all geometric swaps, the entire system consults a `ThreadLocalState` containing the user-defined hyperweights. 
**`Cost = (Alpha * Total Area) + (Beta * Total Overlap Matrix Penalty) - (Delta * Average Compactness)`**
*(Cost calculation updates are isolated to dirty un-cached couriers, taking **O(n log n)** per modified courier, avoiding full-map **O(N log(N/K))** recalculations).*
