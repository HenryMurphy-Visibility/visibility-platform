# process_mgmt.py

from dataclasses import dataclass
from typing import List, Any, Callable, Optional

@dataclass
class ProcessInitResult:
    space: Any
    new_events: List[Any]
    knowledge_cutoff: Any
    earliest_td: Optional[Any]


def initialize_processing(
    *,
    knowledge_cutoff,
    events: List[Any],
    snapshots: List[Any],
    space,
    load_snapshot_fn: Callable[[Any], Any],
    delete_snapshot_fn: Callable[[Any], None]
) -> ProcessInitResult:

    # 1️⃣ Identify NEW events
    new_events = [e for e in events if e.kd > knowledge_cutoff]

    if not new_events:
        return ProcessInitResult(
            space=space,
            new_events=[],
            knowledge_cutoff=knowledge_cutoff,
            earliest_td=None
        )

    # 2️⃣ Compute earliest tradedate among new events
    earliest_td = min(e.tradedate for e in new_events)

    # 3️⃣ Find snapshots valid for earliest_td
    valid_snapshots = [s for s in snapshots if s.kd <= earliest_td]

    if valid_snapshots:
        # 4️⃣ Load best snapshot
        best = max(valid_snapshots, key=lambda s: s.kd)
        space = load_snapshot_fn(best)
    else:
        # No snapshot applies → clean start
        space.reset_all()

    # 5️⃣ Remove invalid snapshots
    invalid = [s for s in snapshots if s.kd > earliest_td]
    for s in invalid:
        delete_snapshot_fn(s)

    return ProcessInitResult(
        space=space,
        new_events=new_events,
        knowledge_cutoff=knowledge_cutoff,
        earliest_td=earliest_td
    )
