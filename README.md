# K8s Pod-Size Scheduler

### Kernel density / similarity balancing

For incoming pod size $x$, define how much node $j$ already has pods of similar size:

$$
D_j(x) = \sum_{q \in node_j} K(x, x_q)
$$

where:

- $x_q$ is CPU request of existing pod $q$
- $K$ is a smooth similarity kernel, e.g. Gaussian:

$$
K(x, y) = \exp\left(-\frac{(x-y)^2}{2\sigma^2}\right)
$$

Interpretation:

- if node already has many pods near size $x$, $D_j(x)$ is large
- prefer nodes where $D_j(x)$ is smaller

Score:

$$
S_j = -D_j(x)
$$

### Density V2: asymmetric larger-pod penalty

A refinement of the basic density scorer that adds a penalty when an existing pod on the node is _larger_ than the incoming pod.
The intuition: placing a small pod next to a large pod wastes co-location opportunities for other large pods, so we should nudge small pods away from large-pod nodes.

$$
D^{v2}_j(x) = \sum_{q \in node_j} K(x, x_q) \cdot \left(1 + \lambda \cdot \frac{\max(0,\, x_q - x)}{x}\right)
$$

where $\lambda$ (`larger_penalty`) controls how aggressively larger neighbours are penalised.

Score:

$$
S_j = -D^{v2}_j(x)
$$

When $\lambda = 0$ this reduces to the plain density scorer.
Larger $\lambda$ increasingly steers small pods toward nodes already occupied by similarly-sized (small) pods, at the cost of a less uniform CPU spread.

This is the closest continuous version of "balance count of same-size pods across nodes".

### Soft buckets: a middle ground between discrete classes and continuous similarity

Instead of rigid bins, every pod contributes partially to nearby sizes.

It behaves like soft buckets.

Instead of discrete class count:

$$
n_{j,k}
$$

use smooth "mass near x":

$$
D_j(x) = \sum_{q \in node_j} K(x, x_q)
$$

So there is a tradeoff:

- **Fixed buckets**: exact control, interpretable, but discontinuous
- **Continuous similarity**: smooth and elegant, but less explicit

A compromise is **soft buckets**.

Example anchor sizes:

- small center = 1 CPU
- mid center = 4 CPU
- large center = 10 CPU
- xl center = 18 CPU

Then every pod contributes to all classes with smooth weights:

$$
w_k(x) = \exp\left(-\frac{(x-\mu_k)^2}{2\sigma_k^2}\right)
$$

For each node:

$$
n^{soft}_{j,k} = \sum_{q \in node_j} w_k(x_q)
$$

Then for incoming pod of size $x$, score node by how much it worsens imbalance of these soft class counts.

This gives:

- class-like behavior
- smooth transitions
- still understandable to humans

May be better than either pure hard buckets or pure unrestricted continuous scoring.

A practical soft-bucket score would be:

$$
S_j = - \sum_k \alpha_k \cdot w_k(x) \cdot n^{soft}_{j,k}
$$

where:

- $n^{soft}_{j,k}$ is current soft mass of class $k$ on node $j$
- $w_k(x)$ is contribution of incoming pod to class $k$

### Demo: see [scheduler.ipynb](scripts/scheduler.ipynb) for a simulation of how this scoring methods distribute pods across nodes

#### Results

<div>
<table border="1">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>strategy</th>
      <th>cpu_std</th>
      <th>pod_count_std</th>
      <th>small_std</th>
      <th>mid_std</th>
      <th>large_std</th>
      <th>xl_std</th>
      <th>total_bucket_std</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>Soft-Bucket</td>
      <td>5.47</td>
      <td>0.80</td>
      <td>0.38</td>
      <td>0.31</td>
      <td>0.16</td>
      <td>0.30</td>
      <td>1.14</td>
    </tr>
    <tr>
      <th>1</th>
      <td>Density</td>
      <td>8.15</td>
      <td>0.80</td>
      <td>0.38</td>
      <td>0.24</td>
      <td>0.46</td>
      <td>0.32</td>
      <td>1.39</td>
    </tr>
    <tr>
      <th>2</th>
      <td>DensityV2</td>
      <td>8.15</td>
      <td>0.80</td>
      <td>0.38</td>
      <td>0.24</td>
      <td>0.46</td>
      <td>0.32</td>
      <td>1.39</td>
    </tr>
    <tr>
      <th>3</th>
      <td>Random</td>
      <td>17.30</td>
      <td>2.76</td>
      <td>2.52</td>
      <td>1.01</td>
      <td>1.49</td>
      <td>0.59</td>
      <td>5.60</td>
    </tr>
    <tr>
      <th>4</th>
      <td>Least-Allocated</td>
      <td>1.41</td>
      <td>5.12</td>
      <td>4.63</td>
      <td>1.65</td>
      <td>0.44</td>
      <td>0.59</td>
      <td>7.31</td>
    </tr>
    <tr>
      <th>5</th>
      <td>Soft-Bucket + AntiAffinity</td>
      <td>4.61</td>
      <td>0.66</td>
      <td>0.37</td>
      <td>0.26</td>
      <td>0.18</td>
      <td>0.30</td>
      <td>1.11</td>
    </tr>
    <tr>
      <th>6</th>
      <td>Density + AntiAffinity</td>
      <td>5.62</td>
      <td>0.66</td>
      <td>0.38</td>
      <td>0.24</td>
      <td>0.43</td>
      <td>0.29</td>
      <td>1.33</td>
    </tr>
    <tr>
      <th>7</th>
      <td>DensityV2 + AntiAffinity</td>
      <td>5.62</td>
      <td>0.66</td>
      <td>0.38</td>
      <td>0.24</td>
      <td>0.43</td>
      <td>0.29</td>
      <td>1.33</td>
    </tr>
    <tr>
      <th>8</th>
      <td>Least-Allocated + AntiAffinity</td>
      <td>3.23</td>
      <td>1.36</td>
      <td>0.84</td>
      <td>0.80</td>
      <td>0.52</td>
      <td>0.33</td>
      <td>2.48</td>
    </tr>
  </tbody>
</table>
</div>

#### Visualizations

**Density scheduler**: pure continuous similarity-based scoring
![density-sim](assets/density-sim.png)

**Soft-buckets scheduler**: soft bucket scoring with 4 anchors
![soft-buckets-sim](assets/soft-buckets-sim.png)

**Random scheduler**: random scoring for comparison
![random-sim](assets/random-sim.png)
