# Architecture notes

- Graph: networkx DiGraph, nodes = suppliers, edges = supply relationships
- Risk scoring: per-node score from external signals (sanctions, news, geo)
- Simulation: remove node → BFS downstream impact → rank affected products
- Frontend: force-directed graph (e.g. react-force-graph) + map view
