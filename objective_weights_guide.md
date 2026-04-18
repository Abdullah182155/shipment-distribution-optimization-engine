# Courier Optimizer: Objective Weights Guide

This document explains the three primary objective weights (**Alpha, Beta, Delta**) used in the optimizer. It breaks down what each weight does mathematically, how it affects the routing algorithm, and provides examples of when to tweak them.

*(Note: Gamma/Elongation is fully disabled as compactness natively penalizes elongated shapes via perimeter, making gamma redundant and safely removable for maximum performance).*

---

## 1. Alpha (Area)

**What it is:** The primary driving force of the entire algorithm. It penalizes the total geographic area covered by all couriers combined.
**Mathematical Definition:** The sum of the Convex Hull Areas (in square kilometers) of every courier's zone.
**How it affects the code:** 
- In `moves.py`, every single time a delivery is moved from Courier A to Courier B (`move_delta` function), the algorithm calculates if the combined area of Courier A and Courier B goes down.
- By minimizing Area, the algorithm naturally clusters deliveries that are close to each other tightly together.

**Computation & Time Complexity:**
- **Computation:** Generates a 2D bounding polygon encompassing all delivery points for a courier, then calculates its internal vector area. Protected heavily by a ThreadLocalState LRU cache to skip redundant calculations.
- **Time Complexity:** **$O(N \log N)$** per courier zone (where *N* is the number of deliveries), determined by the `scipy.spatial.ConvexHull` Quickhull algorithm. With caching, amortization drives this down to **$O(1)$** in tight inner loops.

**Examples:**
- **High Alpha (e.g., 0.99):** Standard behavior. Produces the tightest possible zones, ensuring a courier drives the minimum geographic distance.
- **Low Alpha (e.g., 0.10):** Would allow zones to expand dramatically, leading to inefficient, overlapping paths unless other weights forcefully restrict the shapes.

---

## 2. Beta (Overlap)

**What it is:** A strict penalty applied when the convex hull of Courier A geographically overlaps with the convex hull of Courier B.
**Mathematical Definition:** Evaluated using the Sutherland-Hodgman Polygon Clipping algorithm (`exact_overlap_area` in `geometry.py`). It calculates the exact shared $km^2$ region between two boundaries.
**How it affects the code:**
- In `moves.py` (`full_cost`), Beta applies a heavy cost penalty if a newly proposed zone arrangement creates overlapping territories.
- Due to the heavy processing power required for polygon clipping, it is evaluated globally during the evaluation phase of the LNS/SA pipeline rather than dynamically on every single micro-move.

**Computation & Time Complexity:**
- **Computation:** Uses the **Sutherland-Hodgman Polygon Clipping** algorithm. It traces the intersecting boundary coordinates between two courier polygons to yield an entirely new "shared" polygon, then calculates the area of that shape.
- **Time Complexity:** **$O(V_1 \times V_2)$** per overlapping pair (where $V_1, V_2$ are the number of boundary vertices belonging to the couriers). Overall overhead across the fleet is **$O(K^2)$** (where $K$ = number of couriers). To mitigate this cost, the engine pre-filters checks by completely bypassing the calculus if the centroids of two couriers are geographically too far apart ($>3.0$ km).

**Examples:**
- **High Beta (e.g., 0.50+):** Forces the algorithm to draw "hard lines" between couriers. Useful for franchised delivery systems where Courier A is legally not allowed to cross into Courier B's zip code. 
- **Low Beta (e.g., 0.01):** Allows slight overlaps. Useful in dense city centers where allowing two couriers to slightly overlap on a main avenue is vastly more efficient than forcing a strict border.

---

## 3. Delta (Compactness)

**What it is:** Measures how "jagged", "scattered", or "bumpy" a given delivery zone is. 
**Mathematical Definition:** The Isoperimetric Quotient ($4\pi \times Area / Perimeter^2$). A perfect circle has a compactness of 1.0. A messy starfish shape has a compactness close to 0.0.
**How it affects the code:**
- Dynamically evaluated in `moves.py` (`move_delta`). The algorithm subtracts the compactness score from the cost (using `delta_w`), effectively rewarding shapes that have smaller, smoother perimeters.
- It prevents the algorithm from trying to forcefully shrink total area by drawing crazy, convoluted jagged edges.

**Computation & Time Complexity:**
- **Computation:** Leverages the existing Convex Hull calculation. It measures the Euclidean distance between all ordered hull vertices to find the total **Perimeter**, then performs the constant-time operation ($4\pi \times Area / Perimeter^2$).
- **Time Complexity:** **$O(N \log N)$** for the underlying hull, plus **$O(V)$** to traverse the boundary vertices and compute perimeter length. Because `hull_perimeter` and `hull_area` rely heavily on the shared LRU geometry cache, checking compactness is lightning fast and viable inside micro-move iterations.

**Examples:**
- **High Delta (e.g., 0.5):** Produces smooth, visually pleasing, near-circular or hexagonal zones. Helpful in residential areas where you want a courier circulating around a specific neighborhood block.
- **Low Delta (e.g., 0.0):** Standard behavior for maximum speed. The algorithm doesn't care if the boundaries look jagged on a map, as long as the pure area covered is mathematically tiny.

---

# Algorithm & Metaheuristic Hyperparameters

Beyond purely calculating geometric costs, the multi-phase optimizer relies on several control knobs to balance **speed** versus **quality**. 

## 1. Large Neighborhood Search (LNS) Iterations
**What it does:** Controls how many times the hybrid "destroy and repair" algorithm loops for each initialized variant.
**How it affects execution:** 
- The LNS phase rips apart $15\%$ to $50\%$ of the current solution and intelligently reconstructs it.
- **Tuning:** Setting this high (e.g., `32`) extensively explores the solution space to find major structural breakthroughs but takes significantly longer. Setting it low (e.g., `4`) forces the algorithm to rapidly exit LNS and move onto SA polishing.

## 2. SA Iterations
**What it does:** The number of loops Simulated Annealing (SA) executes during the final polish phase.
**How it affects execution:** 
- SA evaluates rapid, granular micro-moves (moving 1 point or swapping 2 points). It requires thousands of iterations to effectively cool down and settle.
- **Tuning:** A value of `1000` is extremely fast but might not perfectly smooth boundary rough spots. `6000` gives the algorithm enough time to test millions of micro-moves.

## 3. SA Start Temp & Cooling Rate
**What it does:** Dictates the initial "chaos" parameter of the SA algorithm and how fast that chaos freezes.
**How it affects execution:**
- In SA, the algorithm will occasionally accept *worse* moves mathematically to escape local minimums. Start Temp (`0.05`) defines how willing it is to accept terrible moves initially.
- The Cooling Rate (`0.9998`) determines how much the temperature drops per iteration. 
- **Tuning:** If the cooling rate is too low (e.g., `0.95`), the algorithm "freezes" almost instantly and acts purely greedy. If it's too close to `1.0` (e.g., `0.99999`), it never settles on a good localized minimum.

## 4. Vertex Steal Neighbours
**What it does:** Controls the reach of the `area_greedy_vertex_steal` operator, which attempts to greedily "steal" overlapping boundary nodes from adjacent couriers.
**How it affects execution:**
- Limits how many neighboring couriers it checks when attempting to steal an isolated, non-compact delivery point.
- **Tuning:** Lower values (e.g., `5`) limit search to immediate geographic neighbors, keeping it extremely fast. Higher values (e.g., `15`) ensure edge cases where a distant courier is weirdly assigned to a point get repaired.

## 5. Merge-Split Pairs
**What it does:** Decides the aggression of the macro `merge_split_pass` operator (which takes two overlapping couriers, perfectly groups all their deliveries into one mega-pool, and then splits it back in half).
**How it affects execution:**
- Helps automatically repair massive structural boundary overlaps that micro-moves cannot fix.
- **Tuning:** Setting to `10` forces the algorithm to attempt this computationally heavy repair on the 10 most-overlapping courier pairs. Reducing this increases LNS loop speed but risks leaving permanent structural cross-overs in the solution.

## 6. Archive Size
**What it does:** The capacity of the `SolutionArchive` memory bank.
**How it affects execution:**
- The engine saves the best overarching solutions it discovers during LNS loops so it can genetically cross-over ("breed") elements from different successful runs.
- **Tuning:** Too small (`2`) limits genetic diversity. Too large (`20`) wastes precious time during the crossover calculations comparing incompatible architectures. `6` is mathematically balanced.

## 7. Adaptive Destroy Bounds (`adapt_frac_min`, `adapt_frac_max`, `boredom_kick_every`)
**What it does:** Limits the mathematical fraction of the entire map that the LNS phase is allowed to violently destroy and reconstruct. 
**How it affects execution:**
- `adapt_frac_max` defines the ceiling (e.g. default `0.50` means it can destroy up to half the routes when struggling). `boredom_kick_every` defines how many consecutive failed optimization iterations must occur before triggering a massive map-wide destruction.
- **Speed vs Quality:** Higher `adapt_frac_max` (e.g., `0.65`) heavily favors absolute territory quality by allowing the algorithm to rip itself out of deep local minimums, but significantly lowers overall processing speed due to massive point regret-reconstructions. 

## 8. LNS Locality Factor (`locality_r_fac`)
**What it does:** Multiplies the vector search radius limit when evaluating replacement couriers for an unassigned delivery.
**How it affects execution:**
- **Speed vs Quality:** Setting this to a narrow radius (e.g., `1.0`) maximizes algorithm speed by drastically reducing the total candidate couriers mathematically evaluated per delivery point. A larger radius (e.g., `1.5`) restricts speed but often finds mathematically superior geographic placements for distant outliers.

## 9. Hull Cache Maximum (`hull_cache_max`)
**What it does:** Sets the maximum capacity of the Python `ThreadLocalState` LRU hardware cache.
**How it affects execution:**
- **Speed vs Quality:** Has **zero functional impact on the final map quality**, but causes a **massive impact on execution speed**. If navigating large datasets (e.g. >500-1000 deliveries) and the memory cache limit is exceeded, the optimization core experiences cache misses — plunging its loop performance from lightning-fast $O(1)$ constant-time lookup back to punishing $O(N \log N)$ math. Default is `8000`. Set to `15000+` for huge datasets.

## 10. Operation Cadence (`merge_split_every`, `archive_crossover_every`)
**What it does:** Dictates exactly how frequently (number of LNS iterations) the heavier geographic algorithms trigger.
**How it affects execution:**
- **Speed vs Quality:** Lowering these values (e.g., triggering every `3` iterations) favors strict quality by constantly restructuring overlapping boundary hubs. However, merging and breeding are the most expensive computational functions. Raising them to `10` or higher aggressively boosts raw LNS cycle throughput speed.
