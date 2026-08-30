"""
Task Dependency DAG Engine.

Provides:
- Topological sort for execution ordering with dependency resolution
- Cycle detection (prevents invalid dependency chains)
- Parallel branch identification (independent tasks that can run concurrently)
- Critical path analysis
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from agent.models import PlanStep, StepStatus

logger = logging.getLogger("taskmaster.task_graph")


class CyclicDependencyError(Exception):
    """Raised when a cycle is detected in the task dependency graph."""
    pass


class MissingDependencyError(Exception):
    """Raised when a step depends on a non-existent step."""
    pass


class TaskDAG:
    """
    Directed Acyclic Graph for task dependency management.

    Each node is a PlanStep identified by step_number.
    Edges represent "depends_on" relationships (B depends on A means edge A → B).
    """

    def __init__(self, steps: List[PlanStep]):
        self.steps = {step.step_number: step for step in steps}
        self.adjacency: Dict[int, List[int]] = defaultdict(list)  # parent → children
        self.in_degree: Dict[int, int] = defaultdict(int)
        self._build_graph()

    def _build_graph(self):
        """Build adjacency list and in-degree counts from step dependencies."""
        all_step_nums = set(self.steps.keys())

        for step_num, step in self.steps.items():
            self.in_degree.setdefault(step_num, 0)
            for dep in step.depends_on:
                if dep not in all_step_nums:
                    raise MissingDependencyError(
                        f"Step {step_num} depends on step {dep}, which does not exist. "
                        f"Valid step numbers: {sorted(all_step_nums)}"
                    )
                self.adjacency[dep].append(step_num)
                self.in_degree[step_num] += 1

    def detect_cycles(self) -> Optional[List[int]]:
        """
        Detect cycles using Kahn's algorithm.
        Returns the cycle path if found, None if DAG is valid.
        """
        in_deg = dict(self.in_degree)
        queue = deque([n for n in self.steps if in_deg.get(n, 0) == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in self.adjacency.get(node, []):
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self.steps):
            # Cycle exists — find the nodes involved
            cycle_nodes = [n for n in self.steps if in_deg.get(n, 0) > 0]
            return cycle_nodes
        return None

    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the DAG: check for cycles and missing dependencies.
        Returns (is_valid, error_message).
        """
        cycle = self.detect_cycles()
        if cycle:
            return False, f"Cyclic dependency detected involving steps: {cycle}"
        return True, None

    def topological_sort(self) -> List[int]:
        """
        Return step numbers in topological order (respecting dependencies).
        Raises CyclicDependencyError if cycles exist.
        """
        cycle = self.detect_cycles()
        if cycle:
            raise CyclicDependencyError(
                f"Cannot sort: cyclic dependency among steps {cycle}"
            )

        in_deg = dict(self.in_degree)
        queue = deque(sorted([n for n in self.steps if in_deg.get(n, 0) == 0]))
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in sorted(self.adjacency.get(node, [])):
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def get_parallel_groups(self) -> List[List[int]]:
        """
        Return groups of steps that can execute in parallel.
        Each group contains steps whose dependencies are all satisfied
        by the time the group runs (i.e., same "level" in the DAG).
        """
        cycle = self.detect_cycles()
        if cycle:
            raise CyclicDependencyError(f"Cannot compute parallel groups: cycle in {cycle}")

        in_deg = dict(self.in_degree)
        current_level = sorted([n for n in self.steps if in_deg.get(n, 0) == 0])
        groups = []

        while current_level:
            groups.append(current_level)
            next_level = []
            for node in current_level:
                for neighbor in self.adjacency.get(node, []):
                    in_deg[neighbor] -= 1
                    if in_deg[neighbor] == 0:
                        next_level.append(neighbor)
            current_level = sorted(next_level)

        return groups

    def get_critical_path(self) -> List[int]:
        """
        Return the longest path through the DAG (critical path).
        Uses dynamic programming on topological order.
        """
        topo_order = self.topological_sort()
        dist: Dict[int, int] = {n: 1 for n in self.steps}
        parent: Dict[int, Optional[int]] = {n: None for n in self.steps}

        for node in topo_order:
            for neighbor in self.adjacency.get(node, []):
                if dist[node] + 1 > dist[neighbor]:
                    dist[neighbor] = dist[node] + 1
                    parent[neighbor] = node

        # Find the node with max distance
        if not dist:
            return []
        end_node = max(dist, key=dist.get)
        path = []
        current = end_node
        while current is not None:
            path.append(current)
            current = parent[current]
        path.reverse()
        return path

    def get_ready_steps(self, completed: Set[int]) -> List[int]:
        """
        Given a set of completed step numbers, return steps that are now
        ready to execute (all dependencies satisfied).
        """
        ready = []
        for step_num, step in self.steps.items():
            if step_num in completed:
                continue
            if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                continue
            if step.status in (StepStatus.IN_PROGRESS, StepStatus.WAITING_APPROVAL):
                continue
            if all(dep in completed for dep in step.depends_on):
                ready.append(step_num)
        return sorted(ready)

    def get_dependents(self, step_number: int) -> List[int]:
        """Return all steps that directly depend on the given step."""
        return self.adjacency.get(step_number, [])

    def get_all_descendants(self, step_number: int) -> Set[int]:
        """Return all transitive dependents of the given step (BFS)."""
        visited = set()
        queue = deque(self.adjacency.get(step_number, []))
        while queue:
            node = queue.popleft()
            if node not in visited:
                visited.add(node)
                queue.extend(self.adjacency.get(node, []))
        return visited

    def summary(self) -> Dict:
        """Return a summary of the DAG structure."""
        groups = self.get_parallel_groups()
        critical = self.get_critical_path()
        return {
            "total_steps": len(self.steps),
            "parallel_groups": len(groups),
            "critical_path_length": len(critical),
            "critical_path": critical,
            "execution_levels": [[s for s in g] for g in groups],
            "max_parallelism": max(len(g) for g in groups) if groups else 0,
        }
