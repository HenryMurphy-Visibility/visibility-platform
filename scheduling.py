# verify_ingestion.py
from ingestion import ingest_events
from v_config import BASE_PATH

# 1️⃣ Path to your test portfolio events file
csv_path = "C:/Users/hjmne/PycharmProjects/chest/refdata/pooltest/Portfolio1.csv"

# 2️⃣ Ingest the file using the new modular ingestion system
events = ingest_events(csv_path)

# 3️⃣ Verification output
print(f"\n✅ Total events ingested: {len(events)}")
if events:
    print("\n🧾 Sample event (first record):")
    first_event = events[0]
    for k, v in vars(first_event).items():
        print(f"{k:<20}: {v}")
else:
    print("⚠️ No events ingested! Check the file or METHOD_EVENT_CLASS_MAP.")
