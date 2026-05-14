def build_snapshot(*, space, snapshot_date, portfolio, period_name):
    import pickle
    from pathlib import Path

    snap_dir = Path(
        f"C:/Users/hjmne/PycharmProjects/chest/"
        f"funds/{portfolio}/Snapshots"
    )
    snap_dir.mkdir(parents=True, exist_ok=True)

    snap_path = snap_dir / f"{portfolio}_{period_name}_{snapshot_date:%Y%m%d}.pkl"

    with open(snap_path, "wb") as f:
        pickle.dump(space, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"📸 Snapshot written: {snap_path}")
    return snap_path
