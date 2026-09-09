"""
# backend/core/agent/workflow_dag.py

Workflow and DAG orchestration engine for Carole.ai task boards.
Provides:
1. Cycle detection (Kahn's algorithm / DFS 3-coloring) preventing dependency deadlocks.
2. Topological level ordering into parallel execution waves (Wave 0, Wave 1, etc.).
3. Multi-dependency unblocking when prerequisite tasks complete.
4. Cascade failure propagation for downstream tasks.
5. Rich DAG graph summary serialization for frontend Kanban / DAG view.
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict, deque

logger = logging.getLogger("carole.workflow_dag")


class DAGCycleError(ValueError):
    """Raised when a dependency cycle is detected in a task graph."""

    def __init__(self, cycle_path: List[str]):
        self.cycle_path = cycle_path
        path_str = " -> ".join(cycle_path)
        super().__init__(f"Dependency cycle detected: {path_str}")


class WorkflowDAG:
    """Manages directed acyclic task graphs, dependency resolution, and execution waves."""

    @staticmethod
    def _normalize_id(val: Any) -> str:
        if val is None:
            return ""
        return str(val).strip().lower()

    @staticmethod
    def _get_field(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def get_task_dependencies(cls, task: Any) -> List[str]:
        """Extracts all upstream dependency IDs for a given task,
        combining `depends_on` array and legacy `blocked_by_task_id`.
        """
        deps: List[str] = []
        raw_deps = cls._get_field(task, "depends_on", None)
        if isinstance(raw_deps, list):
            for d in raw_deps:
                norm = cls._normalize_id(d)
                if norm and norm not in deps:
                    deps.append(norm)

        blocked_by = cls._get_field(task, "blocked_by_task_id", None)
        if blocked_by:
            norm_b = cls._normalize_id(blocked_by)
            if norm_b and norm_b not in deps:
                deps.append(norm_b)

        return deps

    @classmethod
    def build_adjacency_list(
        cls,
        tasks: Any,
        override_task_id: Optional[str] = None,
        override_deps: Optional[List[str]] = None,
    ) -> Dict[str, List[str]]:
        """
        Builds a map from task_id -> list of prerequisite task_ids.
        Optionally overrides dependencies for a specific task (e.g. before updating in DB).
        """
        adj: Dict[str, List[str]] = {}
        norm_override = cls._normalize_id(override_task_id) if override_task_id else None

        if isinstance(tasks, dict):
            for k, v in tasks.items():
                k_norm = cls._normalize_id(k)
                if isinstance(v, list):
                    adj[k_norm] = [cls._normalize_id(x) for x in v if cls._normalize_id(x)]
                else:
                    adj[k_norm] = [cls._normalize_id(v)] if cls._normalize_id(v) else []
            if norm_override and override_deps is not None:
                adj[norm_override] = [cls._normalize_id(d) for d in override_deps if cls._normalize_id(d)]
            return adj

        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                if not tid:
                    continue

                if norm_override and tid == norm_override and override_deps is not None:
                    adj[tid] = [cls._normalize_id(d) for d in override_deps if cls._normalize_id(d)]
                else:
                    adj[tid] = cls.get_task_dependencies(t)

            if norm_override and norm_override not in adj and override_deps is not None:
                adj[norm_override] = [cls._normalize_id(d) for d in override_deps if cls._normalize_id(d)]

        return adj

    @classmethod
    def validate_acyclic(
        cls,
        tasks: List[Any],
        new_or_updated_task_id: Optional[str] = None,
        new_dependencies: Optional[List[str]] = None,
    ) -> None:
        """
        Validates that the task graph does NOT contain cycles.
        Raises DAGCycleError with the detected cycle path if a cycle is found.
        """
        adj = cls.build_adjacency_list(tasks, new_or_updated_task_id, new_dependencies)
        norm_target = cls._normalize_id(new_or_updated_task_id) if new_or_updated_task_id else None

        # 1. Immediate self-dependency check
        for tid, deps in adj.items():
            if tid in deps:
                # Find task title for human-friendly message if available
                raise DAGCycleError([tid, tid])

        # 2. Cycle detection via DFS 3-coloring (0=WHITE, 1=GRAY, 2=BLACK)
        visited: Dict[str, int] = defaultdict(int)
        parent_map: Dict[str, str] = {}
        cycle_found: List[str] = []

        def dfs(node: str) -> bool:
            visited[node] = 1  # GRAY (in current path)
            for prereq in adj.get(node, []):
                # Prerequisite node might not be in current tasks list (e.g. external or deleted)
                if prereq not in adj:
                    continue

                if visited[prereq] == 1:
                    # Found a back-edge to a node currently in recursion stack!
                    cycle = [prereq, node]
                    cur = node
                    while cur in parent_map and parent_map[cur] != prereq:
                        cur = parent_map[cur]
                        cycle.append(cur)
                    cycle.append(prereq)
                    cycle.reverse()
                    cycle_found.extend(cycle)
                    return True
                elif visited[prereq] == 0:
                    parent_map[prereq] = node
                    if dfs(prereq):
                        return True

            visited[node] = 2  # BLACK (fully explored)
            return False

        # If a specific task was updated, prioritize starting search from it
        nodes_to_check = list(adj.keys())
        if norm_target and norm_target in adj:
            nodes_to_check = [norm_target] + [n for n in nodes_to_check if n != norm_target]

        for node in nodes_to_check:
            if visited[node] == 0:
                parent_map.clear()
                if dfs(node):
                    raise DAGCycleError(cycle_found or [node, node])

    @classmethod
    def get_execution_waves(cls, tasks: Any) -> List[List[Dict[str, Any]]]:
        """
        Groups tasks into parallel execution waves using level-ordered topological sort.
        Wave 0: Tasks with 0 prerequisites.
        Wave 1: Tasks that only depend on Wave 0 tasks.
        Wave N: Tasks depending on earlier waves.
        """
        adj = cls.build_adjacency_list(tasks)
        task_map = {}
        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                if tid:
                    task_map[tid] = t

        # in-degree: number of prerequisites within this graph
        in_degree: Dict[str, int] = {}
        downstream: Dict[str, List[str]] = defaultdict(list)

        for tid in adj:
            prereqs = [p for p in adj[tid] if p in adj]
            in_degree[tid] = len(prereqs)
            for p in prereqs:
                downstream[p].append(tid)

        current_queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        waves: List[List[Dict[str, Any]]] = []

        while current_queue:
            wave_nodes = []
            next_queue = deque()

            for tid in current_queue:
                t = task_map.get(tid)
                wave_nodes.append({
                    "id": str(cls._get_field(t, "id", tid)),
                    "title": cls._get_field(t, "title", "Untitled"),
                    "status": cls._get_field(t, "status", "todo"),
                    "priority": cls._get_field(t, "priority", "medium"),
                    "assigned_agent_id": str(cls._get_field(t, "assigned_agent_id", "")) if cls._get_field(t, "assigned_agent_id", None) else None,
                    "depends_on": adj.get(tid, []),
                })

                for dependent in downstream.get(tid, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)

            if wave_nodes:
                waves.append(wave_nodes)
            current_queue = next_queue

        return waves

    @classmethod
    def get_ready_tasks(cls, tasks: Any) -> List[Any]:
        """
        Returns tasks in 'todo' or 'blocked' status whose prerequisites in the task set
        are ALL in 'done' status.
        """
        adj = cls.build_adjacency_list(tasks)
        status_map = {}
        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                if tid:
                    status_map[tid] = cls._get_field(t, "status", "todo")

        ready = []
        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                current_status = cls._get_field(t, "status", "todo")

                if current_status not in ("todo", "blocked"):
                    continue

                prereqs = adj.get(tid, [])
                if not prereqs:
                    ready.append(t)
                    continue

                all_done = True
                for p in prereqs:
                    if status_map.get(p) != "done":
                        all_done = False
                        break

                if all_done:
                    ready.append(t)

        return ready

    @classmethod
    def propagate_task_completion(
        cls,
        tasks: List[Any],
        completed_task_id: str,
    ) -> List[Any]:
        """
        When `completed_task_id` is marked 'done', identifies all downstream tasks
        that are now unblocked (meaning ALL of their prerequisite tasks are now 'done').
        """
        norm_completed = cls._normalize_id(completed_task_id)
        adj = cls.build_adjacency_list(tasks)

        status_map = {}
        task_map = {}
        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                if tid:
                    task_map[tid] = t
                    if tid == norm_completed:
                        status_map[tid] = "done"
                    else:
                        status_map[tid] = cls._get_field(t, "status", "todo")

        unblocked_tasks: List[Any] = []

        for tid, prereqs in adj.items():
            if norm_completed not in prereqs:
                continue

            current_status = status_map.get(tid)
            if current_status not in ("todo", "blocked"):
                continue

            # Check if all other prerequisites are also 'done'
            all_satisfied = True
            for p in prereqs:
                if status_map.get(p) != "done":
                    all_satisfied = False
                    break

            if all_satisfied and tid in task_map:
                unblocked_tasks.append(task_map[tid])

        return unblocked_tasks

    @classmethod
    def propagate_cascade_failure(
        cls,
        tasks: Any,
        failed_task_id: Any,
        reason: str = "Dependency execution failed",
    ) -> List[Tuple[Any, str]]:
        """
        When a task fails or is cancelled, identifies all downstream dependent tasks
        recursively that must be transitioned to 'blocked'.
        Returns list of (task, cascade_reason) tuples.
        Supports both (tasks, failed_task_id) and (failed_task_id, tasks) signatures.
        """
        if isinstance(tasks, str) and isinstance(failed_task_id, (list, dict)):
            tasks, failed_task_id = failed_task_id, tasks

        norm_failed = cls._normalize_id(failed_task_id)
        adj = cls.build_adjacency_list(tasks)
        task_map = {}
        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                if tid:
                    task_map[tid] = t

        # Build downstream graph: prereq -> list of dependents
        downstream: Dict[str, List[str]] = defaultdict(list)
        for tid, prereqs in adj.items():
            for p in prereqs:
                downstream[p].append(tid)

        impacted: List[Tuple[Any, str]] = []
        visited = set()
        queue = deque([norm_failed])

        failed_obj = task_map.get(norm_failed)
        failed_title = cls._get_field(failed_obj, "title", norm_failed[:8]) if failed_obj else norm_failed[:8]

        while queue:
            curr = queue.popleft()
            for dep_id in downstream.get(curr, []):
                if dep_id not in visited:
                    visited.add(dep_id)
                    dep_task = task_map.get(dep_id)
                    if dep_task:
                        if cls._get_field(dep_task, "status", "") != "done":
                            cascade_msg = f"Blocked by upstream failure of '{failed_title}': {reason}"
                            impacted.append((dep_task, cascade_msg))
                            queue.append(dep_id)
                    else:
                        cascade_msg = f"Blocked by upstream failure of '{failed_title}': {reason}"
                        impacted.append((dep_id, cascade_msg))
                        queue.append(dep_id)

        return impacted

    @classmethod
    def build_dag_summary(cls, tasks: List[Any]) -> Dict[str, Any]:
        """
        Serializes the complete DAG structure for UI rendering and inspection.
        """
        adj = cls.build_adjacency_list(tasks)
        nodes = []
        edges = []

        is_acyclic = True
        cycle_error = None
        try:
            cls.validate_acyclic(tasks)
        except DAGCycleError as e:
            is_acyclic = False
            cycle_error = str(e)

        waves = cls.get_execution_waves(tasks) if is_acyclic else []
        ready_tasks = cls.get_ready_tasks(tasks) if is_acyclic else []
        ready_ids = {cls._normalize_id(cls._get_field(t, "id", None)) for t in ready_tasks}

        if isinstance(tasks, list):
            for t in tasks:
                tid = cls._normalize_id(cls._get_field(t, "id", None))
                nodes.append({
                    "id": str(cls._get_field(t, "id", tid)),
                    "title": cls._get_field(t, "title", "Untitled"),
                    "status": cls._get_field(t, "status", "todo"),
                    "priority": cls._get_field(t, "priority", "medium"),
                    "assigned_agent_id": str(cls._get_field(t, "assigned_agent_id", "")) if cls._get_field(t, "assigned_agent_id", None) else None,
                    "plan_status": cls._get_field(t, "plan_status", "draft"),
                    "is_ready": tid in ready_ids,
                    "depends_on": adj.get(tid, []),
                })

                for prereq_id in adj.get(tid, []):
                    edges.append({
                        "from": prereq_id,
                        "to": tid,
                    })

        return {
            "is_acyclic": is_acyclic,
            "cycle_error": cycle_error,
            "total_tasks": len(tasks),
            "waves_count": len(waves),
            "waves": waves,
            "ready_count": len(ready_tasks),
            "nodes": nodes,
            "edges": edges,
        }


# Singleton export
workflow_dag = WorkflowDAG()
